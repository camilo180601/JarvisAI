"""
brain.py — Adaptadores de tool-calling por proveedor (Claude/OpenAI/MiniMax/Gemini).

Cada proveedor maneja tool-calling distinto; cada clase Conversation mantiene su
historial nativo y expone una interfaz uniforme para el loop:

  conv.add_user(text)
  r = conv.step()             -> {"text": str|None, "tool_calls": [{id,name,input}]}
  conv.add_tool_results([{id, content, is_error}])
"""
from __future__ import annotations
import json
import time


def _cfg(key, default=""):
    try:
        from memory.config_manager import cfg
        return cfg(key, default)
    except Exception:
        return default


_RATE = ("429", "503", "RESOURCE_EXHAUSTED", "overloaded", "rate_limit",
         "rate limit", "unavailable", "UNAVAILABLE", "RESOURCE")


def _retry(fn, tries: int = 4):
    """Reintenta con backoff ante rate-limit / saturación (429/503/overloaded)."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if i == tries - 1 or not any(k in str(e) for k in _RATE):
                raise
            time.sleep(2 * (i + 1))
    raise last


def _stub_old(items, is_result, set_stub, keep: int):
    """Reemplaza el contenido de los tool_results viejos por un stub (microcompact)."""
    idxs = [i for i, m in enumerate(items) if is_result(m)]
    for i in idxs[:-keep] if len(idxs) > keep else []:
        set_stub(items[i])


# ───────────────────────── Anthropic / Claude ─────────────────────────

class ClaudeConversation:
    def __init__(self, system, tool_specs, model, max_tokens=8000):
        import anthropic
        self.client = anthropic.Anthropic(api_key=_cfg("anthropic_api_key"))
        self.model = model
        self.system = system
        self.max_tokens = max_tokens
        self.messages = []
        self.tools = [{"name": t["name"], "description": t["description"],
                       "input_schema": t["parameters"]} for t in tool_specs]

    def add_user(self, text):
        self.messages.append({"role": "user", "content": text})

    def step(self):
        r = _retry(lambda: self.client.messages.create(
            model=self.model, system=self.system, messages=self.messages,
            tools=self.tools, max_tokens=self.max_tokens))
        self.messages.append({"role": "assistant", "content": r.content})
        text, calls = None, []
        for b in r.content:
            if getattr(b, "type", "") == "text":
                text = (text or "") + b.text
            elif getattr(b, "type", "") == "tool_use":
                calls.append({"id": b.id, "name": b.name, "input": b.input or {}})
        return {"text": text, "tool_calls": calls}

    def add_tool_results(self, results):
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r["id"],
             "content": r["content"], "is_error": r.get("is_error", False)}
            for r in results]})

    def compact(self, keep: int = 8):
        def is_res(m):
            return isinstance(m.get("content"), list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
        def stub(m):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    b["content"] = "[resultado omitido para ahorrar contexto]"
        _stub_old(self.messages, is_res, stub, keep)

    def size(self):
        return len(str(self.messages))


# ───────────────────────── OpenAI / MiniMax (compatible) ─────────────────────────

class OpenAIConversation:
    def __init__(self, system, tool_specs, model, base_url=None, key_name="openai_api_key", max_tokens=8000):
        from openai import OpenAI
        kw = {"api_key": _cfg(key_name)}
        if base_url:
            kw["base_url"] = base_url
        self.client = OpenAI(**kw)
        self.model = model
        self.max_tokens = max_tokens
        self.messages = [{"role": "system", "content": system}]
        self.tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
            for t in tool_specs]

    def add_user(self, text):
        self.messages.append({"role": "user", "content": text})

    def step(self):
        def _call():
            try:
                return self.client.chat.completions.create(
                    model=self.model, messages=self.messages, tools=self.tools,
                    max_completion_tokens=self.max_tokens)
            except TypeError:
                return self.client.chat.completions.create(
                    model=self.model, messages=self.messages, tools=self.tools,
                    max_tokens=self.max_tokens)
        r = _retry(_call)
        msg = r.choices[0].message
        self.messages.append(msg.model_dump(exclude_none=True))
        calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            calls.append({"id": tc.id, "name": tc.function.name, "input": args})
        return {"text": msg.content, "tool_calls": calls}

    def add_tool_results(self, results):
        for r in results:
            self.messages.append({"role": "tool", "tool_call_id": r["id"],
                                  "content": str(r["content"])})

    def compact(self, keep: int = 8):
        _stub_old(self.messages, lambda m: m.get("role") == "tool",
                  lambda m: m.__setitem__("content", "[resultado omitido para ahorrar contexto]"), keep)

    def size(self):
        return len(str(self.messages))


# ───────────────────────── Gemini ─────────────────────────

class GeminiConversation:
    def __init__(self, system, tool_specs, model, max_tokens=8000):
        from google import genai
        from google.genai import types
        self._types = types
        self.client = genai.Client(api_key=_cfg("gemini_api_key"))
        self.model = model
        fns = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                         parameters=_to_gemini_schema(t["parameters"]))
               for t in tool_specs]
        self.config = types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=fns)],
            system_instruction=system, max_output_tokens=max_tokens)
        self.contents = []

    def add_user(self, text):
        t = self._types
        self.contents.append(t.Content(role="user", parts=[t.Part(text=text)]))

    def step(self):
        r = _retry(lambda: self.client.models.generate_content(
            model=self.model, contents=self.contents, config=self.config))
        cand = r.candidates[0]
        self.contents.append(cand.content)
        text, calls = None, []
        for i, part in enumerate(cand.content.parts or []):
            if getattr(part, "text", None):
                text = (text or "") + part.text
            fc = getattr(part, "function_call", None)
            if fc:
                calls.append({"id": f"{fc.name}_{i}", "name": fc.name,
                              "input": dict(fc.args) if fc.args else {}})
        return {"text": text, "tool_calls": calls}

    def add_tool_results(self, results):
        t = self._types
        parts = [t.Part.from_function_response(
            name=r["name"], response={"result": str(r["content"])}) for r in results]
        self.contents.append(t.Content(role="user", parts=parts))

    def compact(self, keep: int = 10):
        # Gemini: ventana — conservar el goal inicial + las últimas `keep` interacciones
        # (evita romper el emparejamiento function_call/function_response cortando de a pares)
        if len(self.contents) > keep + 1:
            self.contents = self.contents[:1] + self.contents[-keep:]

    def size(self):
        return sum(len(str(getattr(p, "text", "") or "")) for c in self.contents
                   for p in (c.parts or [])) + len(self.contents) * 50


def _to_gemini_schema(json_schema: dict):
    """Convierte JSON Schema simple a tipos de Gemini."""
    from google.genai import types
    tmap = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER",
            "boolean": "BOOLEAN", "object": "OBJECT", "array": "ARRAY"}
    def conv(s):
        t = tmap.get(s.get("type", "string"), "STRING")
        kw = {"type": t}
        if s.get("description"):
            kw["description"] = s["description"]
        if t == "OBJECT" and s.get("properties"):
            kw["properties"] = {k: conv(v) for k, v in s["properties"].items()}
            if s.get("required"):
                kw["required"] = s["required"]
        if t == "ARRAY" and s.get("items"):
            kw["items"] = conv(s["items"])
        return types.Schema(**kw)
    return conv(json_schema)


# ───────────────────────── factory ─────────────────────────

def make_conversation(provider: str, model: str, system: str, tool_specs: list):
    provider = (provider or "").lower()
    if provider == "claude":
        return ClaudeConversation(system, tool_specs, model)
    if provider == "openai":
        return OpenAIConversation(system, tool_specs, model)
    if provider == "minimax":
        from core.llm_router import MINIMAX_BASE_URL
        return OpenAIConversation(system, tool_specs, model,
                                  base_url=MINIMAX_BASE_URL, key_name="minimax_api_key")
    return GeminiConversation(system, tool_specs, model)
