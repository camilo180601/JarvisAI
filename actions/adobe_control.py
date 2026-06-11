"""
adobe_control.py — Controla Illustrator/InDesign/Photoshop con lenguaje natural.

Flujo:
  1. Usuario pide algo en NL ("creá un A4 con un círculo rojo")
  2. Gemini genera ExtendScript (.jsx) para esa app
  3. Se ejecuta vía adobe_bridge (osascript en Mac, COM en Windows)
  4. Si falla, el error vuelve a Gemini para corregir (hasta 2 reintentos)

Acciones:
  run     — NL → script → ejecuta (default)
  script  — ejecuta jsx crudo provisto en 'script'
  status  — qué apps están instaladas
  preview — NL → script SIN ejecutar (dry run)
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path

from core.adobe_bridge import run_extendscript, detect_apps, app_status_human, ADOBE_APPS
from core.adobe_templates import (
    illustrator_place_trace, preset_is_filled,
    illustrator_export, photoshop_export, indesign_export,
    illustrator_recolor, illustrator_text_logo,
    photoshop_batch, photoshop_remove_bg, indesign_data_merge,
)
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"
MAX_RETRIES = 3

# DOM tips por app — ayuda a Gemini a generar código correcto
_APP_HINTS = {
    "illustrator": (
        "Illustrator ExtendScript: app=app. Documento activo: app.activeDocument. "
        "Crear doc: app.documents.add(). Artboards: doc.artboards. "
        "Formas: doc.pathItems.ellipse(top,left,w,h) / .rectangle(). "
        "Color: var c=new RGBColor(); c.red=255. item.fillColor=c. "
        "Texto: doc.textFrames.add(); tf.contents='...'. "
        "Export PNG: var opts=new ExportOptionsPNG24(); doc.exportFile(new File(path), ExportType.PNG24, opts)."
    ),
    "photoshop": (
        "Photoshop ExtendScript: app=app. Doc activo: app.activeDocument. "
        "Crear doc: app.documents.add(width,height,resolution). "
        "Capas: doc.artLayers.add(). Texto: layer.kind=LayerKind.TEXT. "
        "Unidades: app.preferences.rulerUnits=Units.PIXELS. "
        "Export PNG: var o=new ExportOptionsSaveForWeb(); o.format=SaveDocumentType.PNG; doc.exportDocument(new File(path), ExportType.SAVEFORWEB, o)."
    ),
    "indesign": (
        "InDesign ExtendScript: app=app. Doc: app.documents.add() o app.activeDocument. "
        "Páginas: doc.pages. Marcos texto: page.textFrames.add(). tf.contents='...'. "
        "geometricBounds=[y1,x1,y2,x2] en mm. Rectángulos: page.rectangles.add(). "
        "Export PDF: doc.exportFile(ExportFormat.PDF_TYPE, new File(path))."
    ),
}

_SYSTEM = """Sos un generador de ExtendScript para apps de Adobe. Convertís un pedido
en lenguaje natural en un script .jsx ejecutable.

REGLAS ESTRICTAS:
- ExtendScript es JavaScript ES3 ANTIGUO. PROHIBIDO: let, const, arrow functions (=>),
  template literals (backticks), for...of, Array.forEach con arrow, JSON nativo moderno.
  USAR: var, function() {}, concatenación con +, for clásico.
- El script debe ser autónomo y robusto. Si necesita un documento activo y no hay, crealo.
- Para paths de archivos usar new File("/ruta/absoluta").
- La ÚLTIMA expresión del script debe ser un string útil (ej: "OK: cree A4 con circulo") —
  eso es lo que JARVIS le lee al usuario.
- NADA de UI bloqueante (sin alert(), sin confirm()) — bloquearía la ejecución.
- Manejá errores con try/catch y devolvé el mensaje.

FORMATO DE SALIDA EXACTO (sin markdown, sin JSON):
SUMMARY: <una linea de que hace>
DESTRUCTIVE: <yes|no>
===SCRIPT===
<codigo .jsx completo aca, multilinea, sin escapar nada>
===END===
"""


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

def _generate_script(app: str, request: str, prev_error: str = "") -> dict:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai no instalado.")
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Falta gemini_api_key.")

    hint = _APP_HINTS.get(app, "")
    prompt = f"App destino: {app}\nAPI tips: {hint}\n\nPedido del usuario:\n{request}"
    if prev_error:
        prompt += f"\n\n⚠️ El script anterior FALLÓ con:\n{prev_error}\nCorregilo. Mantené el formato JSON."

    client = genai.Client(api_key=api_key)
    for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
        for delay in (0, 2, 5):
            if delay:
                time.sleep(delay)
            try:
                gen_cfg = types.GenerateContentConfig(max_output_tokens=6000)
                # Desactivar thinking para no gastar el presupuesto de output
                try:
                    gen_cfg.thinking_config = types.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[
                        types.Part(text=_SYSTEM),
                        types.Part(text=prompt),
                    ])],
                    config=gen_cfg,
                )
                parsed = _parse_delimited(resp.text or "")
                if parsed.get("script"):
                    return parsed
                # script vacío → reintentar (truncado o formato raro)
                continue
            except Exception as e:
                if not any(c in str(e) for c in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    raise
    raise RuntimeError("Gemini saturado.")


def _parse_delimited(raw: str) -> dict:
    """Parsea el formato SUMMARY/DESTRUCTIVE/===SCRIPT===...===END==="""
    raw = raw.strip()
    m = re.search(r"===SCRIPT===\s*(.*?)\s*===END===", raw, re.DOTALL)
    if m:
        script = m.group(1).strip()
    else:
        # Tolerante: si falta ===END=== (output truncado), tomar todo tras ===SCRIPT===
        m2 = re.search(r"===SCRIPT===\s*(.*)", raw, re.DOTALL)
        script = m2.group(1).strip() if m2 else ""
    # Si Gemini envolvió el script en ```...```, limpiarlo
    if script.startswith("```"):
        script = re.sub(r"^```[a-z]*\s*", "", script)
        script = re.sub(r"\s*```\s*$", "", script)
    sm = re.search(r"SUMMARY:\s*(.+)", raw)
    dm = re.search(r"DESTRUCTIVE:\s*(yes|no|true|false)", raw, re.IGNORECASE)
    return {
        "script": script,
        "summary": sm.group(1).strip() if sm else "(sin resumen)",
        "destructive": bool(dm and dm.group(1).lower() in ("yes", "true")),
    }


# Apps implícitas por acción (cuando el usuario no nombra la app)
_IMPLIED_APP = {
    "recolor": "illustrator", "text_logo": "illustrator",
    "remove_bg": "photoshop", "batch": "photoshop",
    "data_merge": "indesign",
    # Illustrator
    "shape": "illustrator", "outline_text": "illustrator", "outlines": "illustrator",
    "fit_artboard": "illustrator", "export_artboards": "illustrator",
    "align": "illustrator", "grid": "illustrator", "pathfinder": "illustrator",
    "pattern": "illustrator", "radial_repeat": "illustrator", "mandala": "illustrator",
    "scatter": "illustrator", "shape_of": "illustrator", "polygon_of": "illustrator", "tile": "illustrator",
    "detect_faces": "illustrator", "caras": "illustrator", "detectar_caras": "illustrator",
    "place_in_face": "illustrator", "poner_en_cara": "illustrator", "colocar_en_cara": "illustrator",
    "gradient": "illustrator", "gradiente": "illustrator", "stroke": "illustrator", "trazo": "illustrator", "opacity": "illustrator", "opacidad": "illustrator",
    "blend": "illustrator", "reflect": "illustrator", "mirror": "illustrator", "transform": "illustrator",
    "arrange": "illustrator", "distribute": "illustrator",
    "star": "illustrator", "estrella": "illustrator",
    "spiral": "illustrator", "espiral": "illustrator", "clip_mask": "illustrator", "mask": "illustrator", "mascara": "illustrator",
    "round_rect": "illustrator", "rounded_rect": "illustrator", "text": "illustrator", "texto": "illustrator",
    "group": "illustrator", "agrupar": "illustrator", "ungroup": "illustrator", "desagrupar": "illustrator",
    "swatches": "illustrator", "muestras": "illustrator", "artboard": "illustrator", "mesa": "illustrator",
    "compound_path": "illustrator", "compound": "illustrator", "place_linked": "illustrator",
    "line": "illustrator", "linea": "illustrator", "dashed_stroke": "illustrator", "dashes": "illustrator",
    "layer": "illustrator", "capa": "illustrator",
    "wave": "illustrator", "onda": "illustrator", "color_mode": "illustrator", "join": "illustrator", "unir": "illustrator",
    "concentric": "illustrator", "concentrico": "illustrator", "sunburst": "illustrator", "rafaga": "illustrator", "arc": "illustrator", "arco": "illustrator",
    "area_text": "illustrator", "font": "illustrator", "fuente": "illustrator", "text_align": "illustrator", "alinear_texto": "illustrator",
    "canvas": "photoshop", "rotate_canvas": "photoshop", "fill": "photoshop",
    "layer_style": "photoshop", "place_image": "photoshop",
    "blend_mode": "photoshop", "layer_opacity": "photoshop",
    "duplicate_layer": "photoshop", "new_layer": "photoshop",
    "hue_saturation": "photoshop", "rasterize": "photoshop", "rasterizar": "photoshop",
    "transform_layer": "photoshop", "levels": "photoshop", "niveles": "photoshop",
    "color_balance": "photoshop", "clipping_mask": "photoshop", "flip": "photoshop", "voltear": "photoshop",
    "curves": "photoshop", "curvas": "photoshop", "smart_object": "photoshop", "objeto_inteligente": "photoshop",
    "photo_filter": "photoshop", "filtro_foto": "photoshop",
    "auto_tone": "photoshop", "auto": "photoshop", "layer_mask": "photoshop", "mascara_capa": "photoshop",
    "black_white": "photoshop", "blanco_negro": "photoshop",
    "lens_flare": "photoshop", "destello": "photoshop", "distort": "photoshop", "distorsion": "photoshop",
    "unsharp": "photoshop", "enfoque": "photoshop",
    "warp_text": "photoshop", "deformar_texto": "photoshop", "text_styled": "photoshop", "texto_estilizado": "photoshop",
    "select": "photoshop", "seleccionar": "photoshop", "select_color": "photoshop", "seleccionar_color": "photoshop",
    "content_aware_fill": "photoshop", "relleno_contenido": "photoshop", "feather_selection": "photoshop", "suavizar_seleccion": "photoshop",
    "crop_to_selection": "photoshop", "recortar_seleccion": "photoshop", "adjustment_layer": "photoshop", "capa_ajuste": "photoshop",
    "gradient_map": "photoshop", "mapa_degradado": "photoshop",
    # InDesign
    "place": "indesign", "page_numbers": "indesign",
    "find_replace": "indesign", "replace": "indesign", "step_repeat": "indesign",
    "text_frame": "indesign", "table": "indesign", "tabla": "indesign", "rectangle": "indesign", "rectangulo": "indesign",
    "corner_options": "indesign", "corners": "indesign", "esquinas": "indesign", "oval": "indesign", "elipse": "indesign",
    "polygon": "indesign", "poligono": "indesign", "drop_shadow": "indesign",
    "image_grid": "indesign", "contact_sheet": "indesign",
    "add_pages": "indesign", "agregar_paginas": "indesign",
    "guides": "indesign", "guias": "indesign", "fit": "indesign", "ajustar": "indesign",
    "paragraph_style": "indesign", "estilo_parrafo": "indesign", "text_columns": "indesign", "columnas_texto": "indesign",
    "bullets": "indesign", "vinetas": "indesign",
    "master_page": "indesign", "pagina_maestra": "indesign", "apply_master": "indesign", "aplicar_maestra": "indesign",
    "text_wrap": "indesign", "cenir_texto": "indesign", "object_style": "indesign", "estilo_objeto": "indesign",
    "place_text_file": "indesign", "colocar_texto": "indesign", "thread_frames": "indesign", "hilar_marcos": "indesign",
    "toc": "indesign", "tabla_contenido": "indesign", "id_layer": "indesign",
    # Photoshop
    "resize": "photoshop", "crop": "photoshop", "adjust": "photoshop",
    "text_layer": "photoshop", "flatten": "photoshop", "export_layers": "photoshop",
    "filter": "photoshop",
}


# Memoria del último troquel analizado (caras detectadas), para colocar arte por nombre.
# Se persiste en disco para sobrevivir entre invocaciones / reinicios de sesión.
_FACES_STATE = BASE_DIR / "config" / "last_faces.json"


def _load_faces() -> list[dict]:
    try:
        return json.loads(_FACES_STATE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_faces(faces: list[dict]) -> None:
    try:
        _FACES_STATE.parent.mkdir(parents=True, exist_ok=True)
        _FACES_STATE.write_text(json.dumps(faces), encoding="utf-8")
    except Exception:
        pass


def _detect_faces(parameters: dict, player=None) -> str:
    """Detecta caras del troquel (geométrico) y opcionalmente las nombra con IA (frente/tapa/lateral)."""
    from core import adobe_ops as ops
    min_size = float(parameters.get("min_size") or 40)
    if player:
        player.write_log("📐 Analizando el troquel (buscando caras)...")
    ok, out = run_extendscript("illustrator", ops.ai_detect_faces(min_size))
    if not ok or out.startswith("ERROR"):
        return f"✗ Illustrator: {out[:200]}"
    if out.startswith("NOFACES"):
        return ("No encontré caras rectangulares en el troquel. ¿La plantilla usa rectángulos cerrados "
                "para cada cara? Si es un PDF importado, puede venir como un solo trazado: pedime "
                "'convertí el troquel a caras' o decime las medidas a mano.")
    # parsear JSON de caras
    try:
        faces = json.loads(out[len("FACES:"):])
    except Exception as e:
        return f"Detecté caras pero no pude leerlas: {str(e)[:100]}"
    if not faces:
        return "No quedaron caras tras descartar el contorno exterior."

    # Capa IA opcional: nombrar las caras (frente/tapa/lateral/pestaña) viendo el troquel
    label_ai = parameters.get("ai_label")
    label_ai = True if label_ai is None else bool(label_ai)
    ai_note = ""
    if label_ai:
        try:
            named = _ai_name_faces(faces, player)
            if named:
                for f in faces:
                    if str(f["id"]) in named:
                        f["role"] = named[str(f["id"])]
                ai_note = " (con roles estimados por IA)"
        except Exception as e:
            ai_note = f" (IA de nombres falló: {str(e)[:60]})"

    _save_faces(faces)
    lines = [f"📦 Detecté {len(faces)} cara(s) en el troquel{ai_note}:"]
    for f in faces:
        role = f.get("role", "")
        rolestr = f" — {role}" if role else ""
        lines.append(f"  • cara {f['id']}: {f['name']}{rolestr}  ({f['w']:.0f}×{f['h']:.0f} pt)")
    lines.append("Decime, por ej.: 'poné el gato en la cara izquierda' o 'en la cara 2'.")
    return "\n".join(lines)


def _ai_name_faces(faces: list[dict], player=None) -> dict:
    """Exporta el troquel a PNG y le pide a Gemini el ROL de cada cara (frente/tapa/lateral/pestaña)."""
    api_key = _get_api_key()
    if not api_key:
        return {}
    # exportar a PNG temporal
    png = str(Path.home() / "Pictures" / "JARVIS" / "troquel_tmp")
    Path(png).parent.mkdir(parents=True, exist_ok=True)
    from core.adobe_templates import illustrator_export
    ok, _ = run_extendscript("illustrator", illustrator_export("png", png, png + ".png", 1.0))
    png_file = png + ".png"
    if not ok or not Path(png_file).exists():
        return {}
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        face_list = "; ".join(f"id {f['id']}: {f['name']} ({f['w']:.0f}x{f['h']:.0f}pt)" for f in faces)
        prompt = (
            "Esta imagen es un troquel/dieline de un empaque (caja). Te paso las caras detectadas con su "
            f"posición: {face_list}. Para CADA id, decime su ROL probable en la caja: frente, dorso, tapa, "
            "base, lateral-izquierdo, lateral-derecho, o pestaña. Respondé SOLO en formato id=rol, uno por "
            "línea, sin texto extra. Ej:\n0=frente\n1=lateral-izquierdo"
        )
        with open(png_file, "rb") as fh:
            img = fh.read()
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(parts=[
                types.Part(text=prompt),
                types.Part(inline_data=types.Blob(data=img, mime_type="image/png")),
            ])],
        )
        out = {}
        for line in (resp.text or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
        return out
    except Exception:
        return {}


def _find_face(ref: str, faces: list[dict]) -> dict | None:
    """Encuentra una cara por id, posición o rol (ej '2', 'izquierda', 'frente')."""
    if not faces:
        return None
    ref = (ref or "").strip().lower()
    if ref == "":
        return None
    if ref.isdigit():
        for f in faces:
            if f["id"] == int(ref):
                return f
    for f in faces:                                   # por rol (frente/tapa/lateral)
        if ref in (f.get("role", "") or "").lower():
            return f
    for f in faces:                                   # por nombre de posición
        if ref in f.get("name", "").lower():
            return f
    for f in faces:                                   # match parcial por palabra
        if any(ref in part for part in f.get("name", "").split("-")):
            return f
    return None


def _place_in_face(parameters: dict, player=None) -> str:
    """Coloca una imagen (ruta o query) dentro de una cara detectada del troquel."""
    from core import adobe_ops as ops
    faces = _load_faces()
    if not faces:
        return ("Todavía no analicé el troquel. Pedime primero 'detectá las caras del troquel' "
                "y después 'poné X en la cara Y'.")
    ref = (parameters.get("face") or parameters.get("cara") or "").strip()
    if not ref:
        return ("¿En qué cara? Decime el nombre o número (ej: 'cara izquierda', 'cara 2', "
                "o el rol como 'frente').")
    face = _find_face(ref, faces)
    if not face:
        opciones = ", ".join(f"{f['id']}:{f['name']}" + (f"/{f.get('role')}" if f.get('role') else "") for f in faces)
        return f"No encontré la cara '{ref}'. Caras disponibles: {opciones}."

    # imagen: ruta directa o query a descargar
    image = (parameters.get("image") or parameters.get("path") or "").strip()
    if not image:
        query = (parameters.get("query") or "").strip()
        if not query:
            return "Decime 'image' (ruta) o 'query' (qué imagen buscar) para colocar en la cara."
        try:
            from actions.image_fetch import fetch_image
            if player:
                player.write_log(f"🖼️ Buscando imagen: '{query}'...")
            image, _meta = fetch_image(query)
        except Exception as e:
            return f"No pude conseguir la imagen: {e}"
    if not Path(image).exists():
        return f"No existe la imagen en {image}."

    margin = float(parameters.get("margin") or 0.15)
    trace = bool(parameters.get("trace"))
    if player:
        player.write_log(f"📥 Colocando en cara {face['id']} ({face['name']})...")
    jsx = ops.ai_place_in_face(image, face["l"], face["t"], face["r"], face["b"], margin, trace)
    ok, out = run_extendscript("illustrator", jsx)
    flag = "✓" if ok and not out.startswith("ERROR") else "✗"
    rolestr = f"/{face.get('role')}" if face.get("role") else ""
    return f"{flag} Cara {face['id']} ({face['name']}{rolestr}): {out[:180]}"


@tool(
    name='adobe_control',
    description="Controla Adobe Illustrator, InDesign y Photoshop con plantillas curadas. Acciones generales: run (NL→ExtendScript) | preview | script | status. Documentos (cualquier app, requiere app): open | save | close | info. Imagen/vector: place_trace (AI: imagen+Calco) | export (PNG/SVG/PDF) | recolor (AI) | text_logo (AI). Illustrator: shape (crear forma) | outline_text | fit_artboard | export_artboards | align | grid | pathfinder. InDesign: new_doc | place (texto/imagen) | page_numbers | find_replace | data_merge. Photoshop: new_doc | resize | crop | adjust | text_layer | flatten | export_layers | remove_bg | batch. La app se infiere por la acción cuando es inequívoca (shape→illustrator, place→indesign, resize→photoshop); para open/save/close/info/new_doc pasá 'app'.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'run | preview | script | status | open | save | close | '
                                              'info | place_trace | export | recolor | text_logo | '
                                              'shape | outline_text | fit_artboard | export_artboards '
                                              '| align | grid | pathfinder | pattern (Illustrator: '
                                              'patrón de figuras trazadas) | radial_repeat/mandala '
                                              '(copias en círculo) | scatter (esparcir copias) | '
                                              'shape_of/polygon_of (armar un polígono —pentágono, '
                                              "etc.— hecho de una imagen 'query' o figuras) | tile "
                                              '(teselar la selección en grilla, skip_every deja '
                                              'vacíos) | gradient (relleno degradado a la selección, '
                                              'colors + type linear/radial + angle) | stroke '
                                              '(poner/quitar contorno a la selección: color + width, '
                                              'none=true quita) | opacity (opacidad 0-100 de la '
                                              'selección) | blend (transición entre 2 objetos, steps) '
                                              '| reflect/mirror (espejar, axis) | transform '
                                              '(rotate/scale por valor) | arrange (orden z: '
                                              'front/back/forward/backward) | distribute (espaciado '
                                              'parejo) | canvas (Photoshop: trim/resize lienzo) | '
                                              'rotate_canvas (Photoshop) | fill (Photoshop: rellenar '
                                              'de color) | layer_style (Photoshop: '
                                              'drop_shadow/stroke/glow) | place_image (Photoshop: '
                                              'colocar imagen, image o query) | new_doc. pathfinder '
                                              'ahora también: divide, trim, merge, crop, outline, '
                                              'exclude. | star (Illustrator: estrella de N puntas, '
                                              'points/outer/inner/fill) | spiral (Illustrator: '
                                              'espiral, turns/radius) | clip_mask (Illustrator: '
                                              'máscara de recorte con la selección) | round_rect '
                                              '(Illustrator: rectángulo redondeado, '
                                              'width/height/radius/fill) | text (Illustrator: texto en '
                                              'x/y con size/fill) | group/ungroup (Illustrator: '
                                              'agrupar/desagrupar la selección) | swatches '
                                              "(Illustrator: agregar muestras de color desde 'colors') "
                                              '| artboard (Illustrator: nueva mesa de trabajo, '
                                              'width/height) | compound_path (Illustrator: trazado '
                                              'compuesto con la selección → formas con huecos) | '
                                              'place_linked (Illustrator: colocar imagen sin '
                                              'vectorizar, image o query, embed opcional) | line '
                                              '(Illustrator: línea x1,y1→x2,y2 con color/width) | '
                                              'dashed_stroke (Illustrator: contorno discontinuo en la '
                                              'selección, dashes ej [6,3]) | layer (Illustrator: crear '
                                              "capa 'name', o renombrar la activa con rename=true) | "
                                              'curves (Photoshop: curvas, points=[[in,out],...]; '
                                              'default curva en S) | smart_object (Photoshop: '
                                              'convertir la capa en objeto inteligente) | photo_filter '
                                              '(Photoshop: filtro de foto warm/cool/hex + density) | '
                                              'polygon (InDesign: polígono/estrella de color, sides + '
                                              'star_inset%) | drop_shadow (InDesign: sombra a la '
                                              'selección o último rectángulo) | image_grid (InDesign: '
                                              "grilla/contact sheet desde 'folder', cols) | wave "
                                              '(Illustrator: onda senoidal, cycles/amplitude/width) | '
                                              'color_mode (Illustrator: convertir doc a rgb|cmyk, '
                                              "'mode') | join (Illustrator: unir trazados abiertos "
                                              'seleccionados) | auto_tone (Photoshop: auto '
                                              "niveles|contraste, 'mode') | layer_mask (Photoshop: "
                                              'agregar máscara, reveal=true blanco/false negro) | '
                                              "black_white (Photoshop: B&N con 'tint' opcional) | line "
                                              '(línea — app-aware: Illustrator x1,y1→x2,y2; InDesign '
                                              'línea gráfica) | gradient (degradado — app-aware: '
                                              'Illustrator a la selección con colors; InDesign con '
                                              'colors[0..1] o color_a/color_b + type) | add_pages '
                                              "(InDesign: agregar 'count' páginas) | concentric "
                                              '(Illustrator: anillos concéntricos, rings) | sunburst '
                                              '(Illustrator: ráfaga de líneas radiales, count) | arc '
                                              '(Illustrator: arco, start_angle/sweep/radius) | '
                                              'lens_flare (Photoshop: destello de lente, brightness) | '
                                              'distort (Photoshop: twirl|spherize|pinch|ripple + '
                                              'amount) | unsharp (Photoshop: enfoque, '
                                              'amount/radius/threshold) | guides (InDesign: guías de '
                                              'regla, horizontals/verticals en mm) | outline_text '
                                              '(texto→curvas — app-aware: Illustrator o InDesign) | '
                                              'fit (InDesign: '
                                              'content_to_frame|frame_to_content|proportional|fill|center) '
                                              '| detect_faces (Illustrator: detecta las CARAS de un '
                                              'troquel/dieline importado —rectángulos cerrados— y las '
                                              'nombra por posición y rol con IA: frente/tapa/lateral; '
                                              'úsalo ANTES de colocar arte por cara) | place_in_face '
                                              "(Illustrator: coloca una imagen —'image' o 'query'— "
                                              "DENTRO de una cara detectada, indicada en 'face' por "
                                              'número/posición/rol; opcional trace=true para calcar) | '
                                              'area_text (Illustrator: caja de texto, '
                                              'text/width/height/size) | font (tipografía — app-aware: '
                                              'font/size/tracking/leading sobre texto seleccionado o '
                                              'capa activa) | text_align (alineación de párrafo — '
                                              "app-aware: left|center|right|justify, en 'align') | "
                                              'text_styled (Photoshop: capa de texto completa — '
                                              'text/size/fill/font/align/box) | warp_text (Photoshop: '
                                              'deformar texto, '
                                              'style=arc|flag|wave|fish|rise|bulge|arch + bend -1..1) '
                                              '| paragraph_style (InDesign: crear+aplicar estilo de '
                                              'párrafo, name/font/size/leading/align/color) | '
                                              'text_columns (InDesign: columnas en el marco, count + '
                                              'gutter) | bullets (InDesign: viñetas/numeración, '
                                              'mode=bullet|number|none) | select (Photoshop: selección '
                                              'all|none|invert|rect|ellipse, box=[l,t,r,b], feather) | '
                                              'select_color (Photoshop: rango de color, color + '
                                              'tolerance) | content_aware_fill (Photoshop: rellena la '
                                              'selección según contenido) | feather_selection '
                                              '(Photoshop: suaviza la selección, radius) | '
                                              'crop_to_selection (Photoshop: recorta al área '
                                              'seleccionada) | adjustment_layer (Photoshop: capa de '
                                              'ajuste no destructiva, '
                                              'kind=brightness|vibrance|blackwhite|levels, '
                                              'value/value2) | gradient_map (Photoshop: mapa de '
                                              'degradado entre 2 colores) | master_page (InDesign: '
                                              "crear página maestra 'name') | apply_master (InDesign: "
                                              'aplicar maestra, master_name + page_index -1=todas) | '
                                              'text_wrap (InDesign: ceñir texto '
                                              'bounding|object|jump|none + offset) | object_style '
                                              '(InDesign: crear+aplicar estilo de objeto, '
                                              'name/fill/stroke/stroke_weight) | place_text_file '
                                              "(InDesign: colocar .txt/.rtf/.docx desde 'path') | "
                                              'thread_frames (InDesign: hilar marcos de la página) | '
                                              "id_layer (InDesign: crear capa 'name' con 'color') | "
                                              "toc (InDesign: tabla de contenido desde 'style') | "
                                              'blend_mode (modo de fusión de la selección/capa — '
                                              'app-aware: Illustrator usa la selección, Photoshop la '
                                              "capa; 'mode') | layer_opacity (Photoshop: opacidad de "
                                              "la capa, 'value') | duplicate_layer (Photoshop) | "
                                              "new_layer (Photoshop: capa vacía, 'name') | "
                                              'hue_saturation (Photoshop: ajustar '
                                              'hue/saturation/lightness de la capa) | rasterize '
                                              '(Photoshop: rasterizar la capa activa) | '
                                              'transform_layer (Photoshop: rotate/scale/dx/dy de la '
                                              'capa) | levels (Photoshop: niveles, black/white/gamma) '
                                              '| color_balance (Photoshop: balance por '
                                              'shadows/midtones/highlights, cada uno [c-r,m-g,y-b]) | '
                                              'clipping_mask (Photoshop: recorta la capa activa con la '
                                              'de abajo) | flip (Photoshop: voltear '
                                              'target=layer|canvas, axis=horizontal|vertical) | '
                                              'text_frame (InDesign: marco de texto, '
                                              'text/x/y/width/height/size) | table (InDesign: tabla '
                                              'rows×cols) | rectangle (InDesign: rectángulo de color, '
                                              'x/y/width/height/fill) | corner_options (InDesign: '
                                              'esquinas rounded/beveled/inverse/inset/fancy + radius, '
                                              'a la selección o último rectángulo) | oval (InDesign: '
                                              'elipse de color, x/y/width/height/fill) | place | '
                                              'page_numbers | find_replace | step_repeat (InDesign: '
                                              'grilla de copias) | data_merge | resize | crop | adjust '
                                              '| filter (Photoshop: '
                                              'blur/motion/sharpen/noise/pixelate) | text_layer | '
                                              'flatten | export_layers | remove_bg | batch'},
                    'app': {'type': 'STRING', 'description': 'illustrator | photoshop | indesign'},
                    'path': {'type': 'STRING',
                             'description': 'open: ruta del archivo a abrir. place(imagen): ruta de la '
                                            'imagen.'},
                    'kind': {'type': 'STRING',
                             'description': 'shape: rectangle | ellipse | polygon | star'},
                    'width': {'type': 'NUMBER', 'description': 'stroke: grosor del trazo (pt)'},
                    'height': {'type': 'NUMBER', 'description': 'shape/new_doc/resize: alto'},
                    'how': {'type': 'STRING',
                            'description': 'align: left | right | center | top | bottom | middle'},
                    'cols': {'type': 'INTEGER', 'description': 'pattern/step_repeat: columnas'},
                    'gap': {'type': 'NUMBER', 'description': 'grid: separación entre objetos'},
                    'op': {'type': 'STRING', 'description': 'pathfinder: unite | minus | intersect'},
                    'pages': {'type': 'INTEGER',
                              'description': 'new_doc (InDesign): número de páginas'},
                    'margin': {'type': 'NUMBER', 'description': 'new_doc (InDesign): margen en mm'},
                    'columns': {'type': 'INTEGER', 'description': 'new_doc (InDesign): columnas'},
                    'find': {'type': 'STRING', 'description': 'find_replace: texto a buscar'},
                    'replace': {'type': 'STRING', 'description': 'find_replace: texto de reemplazo'},
                    'box': {'type': 'BOOLEAN',
                            'description': 'text_styled: true = texto de párrafo (caja box_w x box_h)'},
                    'kind_adjust': {'type': 'STRING',
                                    'description': 'adjust: bw | brightness | contrast | blur | '
                                                   "sharpen (alias de 'kind')"},
                    'value': {'type': 'NUMBER',
                              'description': 'opacity: 0-100; adjust posterize/threshold: nivel'},
                    'resolution': {'type': 'INTEGER', 'description': 'new_doc (Photoshop): ppi'},
                    'shapes': {'type': 'ARRAY',
                               'items': {'type': 'STRING'},
                               'description': 'pattern: figuras a mezclar (ellipse, rect, triangle, '
                                              'star, hexagon)'},
                    'rows': {'type': 'INTEGER', 'description': 'pattern/step_repeat: filas'},
                    'layout': {'type': 'STRING', 'description': 'pattern: grid | brick | scatter'},
                    'colors': {'type': 'ARRAY',
                               'items': {'type': 'STRING'},
                               'description': 'recolor: paleta de colores hex, ej '
                                              "['#1e90ff','#ffffff']. Se aplican cíclicamente a las "
                                              'formas.'},
                    'rotate': {'type': 'BOOLEAN',
                               'description': 'pattern/scatter: rotar las figuras al azar'},
                    'vary': {'type': 'BOOLEAN', 'description': 'pattern: variar el tamaño al azar'},
                    'count': {'type': 'INTEGER', 'description': 'add_pages: cuántas páginas agregar'},
                    'around': {'type': 'STRING',
                               'description': 'radial_repeat: artboard (centro de la mesa) | '
                                              'selection'},
                    'amount': {'type': 'NUMBER', 'description': 'filter: intensidad (radio/cantidad)'},
                    'angle': {'type': 'NUMBER', 'description': 'filter motion: ángulo del desenfoque'},
                    'sides': {'type': 'INTEGER',
                              'description': 'shape_of/polygon: lados del polígono (5=pentágono, '
                                             '6=hexágono)'},
                    'per_side': {'type': 'INTEGER',
                                 'description': 'shape_of: elementos por lado del polígono'},
                    'radius': {'type': 'NUMBER',
                               'description': 'shape_of: radio del polígono; round_rect: radio de '
                                              'esquinas; star/spiral: radio'},
                    'size': {'type': 'NUMBER', 'description': 'shape_of: tamaño de cada elemento'},
                    'query': {'type': 'STRING',
                              'description': 'place_trace: qué imagen buscar/descargar. Se ignora si '
                                             "se pasa 'image'."},
                    'skip_every': {'type': 'INTEGER',
                                   'description': 'tile: deja vacía cada N posición (5 = 4 llenos y 1 '
                                                  'vacío)'},
                    'tilt': {'type': 'NUMBER',
                             'description': 'shape_of/tile/pattern: inclinación en GRADOS de cada '
                                            'elemento/copia (ej 30)'},
                    'spin': {'type': 'NUMBER',
                             'description': 'shape_of: grados que se rota el polígono entero'},
                    'type': {'type': 'STRING', 'description': 'gradient: linear | radial'},
                    'none': {'type': 'BOOLEAN', 'description': 'stroke: true = quitar el trazo'},
                    'steps': {'type': 'INTEGER', 'description': 'blend: nº de pasos intermedios'},
                    'axis': {'type': 'STRING',
                             'description': 'reflect: horizontal | vertical; distribute: dirección'},
                    'order': {'type': 'STRING',
                              'description': 'arrange: front | back | forward | backward'},
                    'degrees': {'type': 'NUMBER', 'description': 'rotate_canvas: grados'},
                    'mode': {'type': 'STRING',
                             'description': 'canvas: trim | resize; blend_mode: '
                                            'multiply/screen/overlay/softlight/darken/lighten/difference/color/luminosity...'},
                    'points': {'type': 'ARRAY',
                               'items': {'type': 'ARRAY', 'items': {'type': 'NUMBER'}},
                               'description': 'curves: lista de pares [entrada, salida] 0-255'},
                    'outer': {'type': 'NUMBER', 'description': 'star: radio externo de la estrella'},
                    'inner': {'type': 'NUMBER', 'description': 'star: radio interno de la estrella'},
                    'turns': {'type': 'NUMBER', 'description': 'spiral: nº de vueltas de la espiral'},
                    'name': {'type': 'STRING', 'description': 'new_layer: nombre de la capa nueva'},
                    'x': {'type': 'NUMBER',
                          'description': 'text_frame/table/rectangle (InDesign): X en mm; text '
                                         '(Illustrator): X en pt'},
                    'y': {'type': 'NUMBER',
                          'description': 'text_frame/table/rectangle (InDesign): Y en mm; text '
                                         '(Illustrator): Y en pt'},
                    'hue': {'type': 'NUMBER',
                            'description': 'hue_saturation: desplazamiento de tono (-180..180)'},
                    'saturation': {'type': 'NUMBER',
                                   'description': 'hue_saturation: saturación (-100..100)'},
                    'lightness': {'type': 'NUMBER',
                                  'description': 'hue_saturation: luminosidad (-100..100)'},
                    'dx': {'type': 'NUMBER', 'description': 'transform_layer: mover X en px'},
                    'dy': {'type': 'NUMBER', 'description': 'transform_layer: mover Y en px'},
                    'black': {'type': 'INTEGER',
                              'description': 'levels: punto negro de entrada (0-253)'},
                    'white': {'type': 'INTEGER',
                              'description': 'levels: punto blanco de entrada (2-255)'},
                    'gamma': {'type': 'NUMBER',
                              'description': 'levels: gamma de medios tonos (0.1-9.99, 1=neutro)'},
                    'shadows': {'type': 'ARRAY',
                                'items': {'type': 'NUMBER'},
                                'description': 'color_balance: sombras [cian-rojo, magenta-verde, '
                                               'amarillo-azul] (-100..100)'},
                    'midtones': {'type': 'ARRAY',
                                 'items': {'type': 'NUMBER'},
                                 'description': 'color_balance: medios tonos [c-r, m-g, y-b]'},
                    'highlights': {'type': 'ARRAY',
                                   'items': {'type': 'NUMBER'},
                                   'description': 'color_balance: luces [c-r, m-g, y-b]'},
                    'target': {'type': 'STRING', 'description': 'flip: layer | canvas'},
                    'style': {'type': 'STRING',
                              'description': 'corner_options: rounded | beveled | inverse | inset | '
                                             'fancy'},
                    'x1': {'type': 'NUMBER', 'description': 'line: X inicial (pt)'},
                    'y1': {'type': 'NUMBER', 'description': 'line: Y inicial (pt)'},
                    'x2': {'type': 'NUMBER', 'description': 'line: X final (pt)'},
                    'y2': {'type': 'NUMBER', 'description': 'line: Y final (pt)'},
                    'dashes': {'type': 'ARRAY',
                               'items': {'type': 'NUMBER'},
                               'description': 'dashed_stroke: patrón de guiones, ej [6,3] (guion 6, '
                                              'hueco 3)'},
                    'rename': {'type': 'BOOLEAN',
                               'description': 'layer: true = renombrar la capa activa en vez de crear '
                                              'una'},
                    'filter': {'type': 'STRING', 'description': 'photo_filter: warm | cool | hex'},
                    'density': {'type': 'NUMBER', 'description': 'photo_filter: intensidad % (1-100)'},
                    'star_inset': {'type': 'NUMBER',
                                   'description': 'polygon (InDesign): % de inserción de puntas (>0 = '
                                                  'estrella)'},
                    'offset': {'type': 'NUMBER',
                               'description': 'drop_shadow (InDesign): desplazamiento de la sombra '
                                              '(mm)'},
                    'folder': {'type': 'STRING', 'description': 'image_grid: carpeta con las imágenes'},
                    'cycles': {'type': 'NUMBER', 'description': 'wave: nº de ciclos de la onda'},
                    'amplitude': {'type': 'NUMBER', 'description': 'wave: altura de la onda (pt)'},
                    'reveal': {'type': 'BOOLEAN',
                               'description': 'layer_mask: true = máscara blanca (muestra todo), false '
                                              '= negra (oculta)'},
                    'tint': {'type': 'STRING',
                             'description': 'black_white: color hex para teñir el B&N (look duotono), '
                                            'opcional'},
                    'color_a': {'type': 'STRING',
                                'description': 'gradient (InDesign): color inicial hex'},
                    'color_b': {'type': 'STRING',
                                'description': 'gradient (InDesign): color final hex'},
                    'rings': {'type': 'INTEGER', 'description': 'concentric: nº de anillos'},
                    'max_radius': {'type': 'NUMBER',
                                   'description': 'concentric: radio externo (0 = auto al artboard)'},
                    'sweep': {'type': 'NUMBER', 'description': 'arc: grados de barrido del arco'},
                    'start_angle': {'type': 'NUMBER', 'description': 'arc: ángulo inicial en grados'},
                    'brightness': {'type': 'NUMBER', 'description': 'lens_flare: intensidad (10-300)'},
                    'threshold': {'type': 'INTEGER', 'description': 'unsharp: umbral (0-255)'},
                    'horizontals': {'type': 'ARRAY',
                                    'items': {'type': 'NUMBER'},
                                    'description': 'guides: posiciones Y de guías horizontales (mm)'},
                    'verticals': {'type': 'ARRAY',
                                  'items': {'type': 'NUMBER'},
                                  'description': 'guides: posiciones X de guías verticales (mm)'},
                    'align': {'type': 'STRING',
                              'description': 'text_align/font/text_styled/paragraph_style: left | '
                                             'center | right | justify'},
                    'tracking': {'type': 'NUMBER',
                                 'description': 'font/text_styled: espaciado entre letras (tracking)'},
                    'leading': {'type': 'NUMBER',
                                'description': 'font/text_styled/paragraph_style: interlineado (pt); 0 '
                                               '= auto'},
                    'bend': {'type': 'NUMBER', 'description': 'warp_text: curvatura -1..1'},
                    'gutter': {'type': 'NUMBER',
                               'description': 'text_columns: medianil entre columnas (mm)'},
                    'feather': {'type': 'NUMBER', 'description': 'select: suavizado del borde (px)'},
                    'tolerance': {'type': 'INTEGER',
                                  'description': 'select_color: tolerancia/fuzziness (0-200)'},
                    'value2': {'type': 'NUMBER',
                               'description': 'adjustment_layer: segundo valor (ej contraste en '
                                              'brightness)'},
                    'master_name': {'type': 'STRING',
                                    'description': 'apply_master: nombre de la página maestra a '
                                                   'aplicar'},
                    'page_index': {'type': 'INTEGER',
                                   'description': 'apply_master: índice de página (0-based); -1 = '
                                                  'todas'},
                    'title': {'type': 'STRING', 'description': 'toc: título de la tabla de contenido'},
                    'stroke_weight': {'type': 'NUMBER',
                                      'description': 'object_style: grosor del contorno (pt)'},
                    'request': {'type': 'STRING',
                                'description': 'Para run: qué hacer en lenguaje natural'},
                    'script': {'type': 'STRING',
                               'description': 'Para action=script: código ExtendScript .jsx crudo'},
                    'dry_run': {'type': 'BOOLEAN', 'description': 'Generar script sin ejecutar'},
                    'image': {'type': 'STRING',
                              'description': 'place_trace: ruta local de una imagen ya descargada.'},
                    'outline': {'type': 'BOOLEAN',
                                'description': 'place_trace: true = trazo b/n sin relleno; false = '
                                               'conserva rellenos. Si se omite se infiere del preset.'},
                    'new_doc': {'type': 'BOOLEAN',
                                'description': 'place_trace/text_logo: true (default) = documento '
                                               'nuevo; false = usar el abierto.'},
                    'keep_image': {'type': 'BOOLEAN',
                                   'description': 'place_trace: true (default) = conserva la imagen y '
                                                  'deja el calco encima; false = reemplaza por el '
                                                  'vector.'},
                    'preset': {'type': 'STRING',
                               'description': 'place_trace: preset de Calco. default, '
                                              'high_fidelity_photo, low_fidelity_photo, 3_colors, '
                                              '6_colors, 16_colors, shades_of_gray, black_and_white, '
                                              'sketched_art, silhouettes, line_art, '
                                              'technical_drawing.'},
                    'embed': {'type': 'BOOLEAN',
                              'description': 'place_trace/place_linked: true = incrusta la imagen en '
                                             'el documento.'},
                    'face': {'type': 'STRING',
                             'description': "place_in_face: qué cara del troquel (número '2', posición "
                                            "'izquierda', o rol 'frente'/'tapa'/'lateral')"},
                    'min_size': {'type': 'NUMBER',
                                 'description': 'detect_faces: lado mínimo en pt para que un '
                                                'rectángulo cuente como cara (default 40)'},
                    'ai_label': {'type': 'BOOLEAN',
                                 'description': 'detect_faces: true (default) = nombrar las caras con '
                                                'IA (frente/tapa/lateral); false = solo posición'},
                    'trace': {'type': 'BOOLEAN',
                              'description': 'place_in_face: true = aplicar Image Trace al arte '
                                             'colocado'},
                    'format': {'type': 'STRING',
                               'description': 'export: png|svg|pdf|jpg. batch: png|jpg.'},
                    'dest': {'type': 'STRING',
                             'description': 'export: ruta de salida (default '
                                            '~/Desktop/jarvis_export.<fmt>).'},
                    'scale': {'type': 'NUMBER',
                              'description': 'export (Illustrator png/jpg): factor de escala, ej 2 = '
                                             '200%.'},
                    'use_selection': {'type': 'BOOLEAN',
                                      'description': 'recolor: true = solo lo seleccionado; false '
                                                     '(default) = todo el documento.'},
                    'text': {'type': 'STRING', 'description': 'text_logo: el texto del logo.'},
                    'font_size': {'type': 'NUMBER',
                                  'description': 'text_logo: tamaño en pt (default 120).'},
                    'fill': {'type': 'STRING',
                             'description': 'text_logo: color de relleno hex (default #000000).'},
                    'stroke': {'type': 'STRING',
                               'description': 'text_logo: color de contorno hex (opcional).'},
                    'font': {'type': 'STRING',
                             'description': 'text_logo: nombre PostScript de la fuente (opcional).'},
                    'in_dir': {'type': 'STRING',
                               'description': 'batch: carpeta de entrada con imágenes.'},
                    'out_dir': {'type': 'STRING',
                                'description': 'batch: carpeta de salida (default '
                                               '<in_dir>/jarvis_out).'},
                    'max_side': {'type': 'INTEGER',
                                 'description': 'batch: lado máximo en px (default 1080). Solo '
                                                'achica.'},
                    'quality': {'type': 'INTEGER',
                                'description': 'export/batch JPG: calidad 0-100 (default 80).'},
                    'csv': {'type': 'STRING',
                            'description': 'data_merge: ruta del CSV (primera fila = encabezados).'},
                    'limit': {'type': 'INTEGER',
                              'description': 'data_merge: máximo de registros a maquetar.'}},
     'required': []},
)
def adobe_control(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "run").lower()
    app = (parameters.get("app") or "").lower().strip()

    if action == "status":
        return app_status_human()

    # Inferir app cuando la acción la determina
    if not app and action in _IMPLIED_APP:
        app = _IMPLIED_APP[action]

    # Validar app
    if app not in ADOBE_APPS:
        return f"Especificá 'app': {', '.join(ADOBE_APPS)}. ({app or 'vacío'})"
    apps = detect_apps()
    if apps.get(app, {}).get("installed") is False:
        return f"{ADOBE_APPS[app]['label']} no está instalado."

    # Colocar imagen + Image Trace (plantilla curada, solo Illustrator)
    # ── Troquel/dieline: detectar caras + colocar arte en una cara ──
    if action in ("detect_faces", "caras", "detectar_caras"):
        if app != "illustrator":
            return "Detección de caras solo en Illustrator por ahora."
        return _detect_faces(parameters, player)

    if action in ("place_in_face", "poner_en_cara", "colocar_en_cara"):
        if app != "illustrator":
            return "Colocar en cara solo en Illustrator por ahora."
        return _place_in_face(parameters, player)

    if action == "place_trace":
        if app != "illustrator":
            return "place_trace solo está soportado en Illustrator por ahora."
        image = (parameters.get("image") or "").strip()
        if not image:
            query = (parameters.get("query") or parameters.get("request") or "").strip()
            if not query:
                return "Error: dame 'image' (ruta) o 'query' (qué imagen buscar)."
            try:
                from actions.image_fetch import fetch_image
                if player:
                    player.write_log(f"🖼️ Buscando imagen: '{query}'...")
                image, meta = fetch_image(query)
                if player:
                    player.write_log(f"  ✓ {image} ({meta})")
            except Exception as e:
                return f"No pude conseguir la imagen: {e}"
        if not Path(image).exists():
            return f"Error: no existe la imagen en {image}."
        preset = (parameters.get("preset") or "").strip().lower() or None
        outline = parameters.get("outline")
        if outline is None:
            # Un preset de color/foto conserva rellenos; si no hay preset, default = trazo.
            outline = False if preset_is_filled(preset) else True
        else:
            outline = bool(outline)
        new_doc = parameters.get("new_doc")
        new_doc = True if new_doc is None else bool(new_doc)
        keep_image = parameters.get("keep_image")
        keep_image = True if keep_image is None else bool(keep_image)
        embed = bool(parameters.get("embed"))
        jsx = illustrator_place_trace(image, outline=outline, new_doc=new_doc,
                                      keep_image=keep_image, preset=preset, embed=embed)
        if player:
            player.write_log(f"  ▶️ Calco{' ' + preset if preset else ''} en Illustrator...")
        ok, out = run_extendscript("illustrator", jsx)
        if ok and not out.startswith("ERROR"):
            return f"✓ Illustrator: {out[:200]}"
        return f"✗ Illustrator: {out[:300]}"

    # ── Exportar (cross-app) ──
    if action == "export":
        fmt = (parameters.get("format") or parameters.get("fmt") or "png").lower().lstrip(".")
        dest = (parameters.get("dest") or parameters.get("path") or "").strip()
        if not dest:
            dest = str(Path.home() / "Desktop" / f"jarvis_export.{fmt}")
        dest_full = dest if dest.lower().endswith(f".{fmt}") else f"{dest}.{fmt}"
        dest_base = re.sub(r"\.[^.]+$", "", dest_full)
        scale = float(parameters.get("scale") or 1)
        if app == "illustrator":
            jsx = illustrator_export(fmt, dest_base, dest_full, scale)
        elif app == "photoshop":
            jsx = photoshop_export(fmt, dest_full, int(parameters.get("quality") or 80))
        else:
            jsx = indesign_export(fmt, dest_full)
        if player:
            player.write_log(f"  ▶️ Exportando {app} a {fmt.upper()}...")
        ok, out = run_extendscript(app, jsx)
        return f"{'✓' if ok and not out.startswith('ERROR') else '✗'} {ADOBE_APPS[app]['label']}: {out[:250]}"

    # ── Recolorear (Illustrator) ──
    if action == "recolor":
        colors = parameters.get("colors") or []
        if isinstance(colors, str):
            colors = [c.strip() for c in re.split(r"[,\s]+", colors) if c.strip()]
        if not colors:
            return "Error: dame 'colors' (lista de hex, ej ['#1e90ff','#ffffff'])."
        use_sel = bool(parameters.get("use_selection"))
        jsx = illustrator_recolor(colors, use_selection=use_sel)
        if player:
            player.write_log(f"  ▶️ Recoloreando con {len(colors)} colores...")
        ok, out = run_extendscript("illustrator", jsx)
        return f"{'✓' if ok and not out.startswith('ERROR') else '✗'} Illustrator: {out[:250]}"

    # ── Texto → logo (Illustrator) ──
    if action == "text_logo":
        text = (parameters.get("text") or parameters.get("request") or "").strip()
        if not text:
            return "Error: dame 'text' (el texto del logo)."
        new_doc = parameters.get("new_doc")
        new_doc = True if new_doc is None else bool(new_doc)
        jsx = illustrator_text_logo(
            text,
            font_size=float(parameters.get("font_size") or 120),
            fill_hex=parameters.get("fill") or parameters.get("color") or "#000000",
            stroke_hex=parameters.get("stroke") or parameters.get("stroke_color"),
            stroke_width=float(parameters.get("stroke_width") or 1),
            font=parameters.get("font"),
            new_doc=new_doc,
        )
        if player:
            player.write_log(f"  ▶️ Creando logo '{text[:30]}'...")
        ok, out = run_extendscript("illustrator", jsx)
        return f"{'✓' if ok and not out.startswith('ERROR') else '✗'} Illustrator: {out[:250]}"

    # ── Quitar fondo (Photoshop) ──
    if action == "remove_bg":
        jsx = photoshop_remove_bg()
        if player:
            player.write_log("  ▶️ Quitando fondo (Select Subject)...")
        ok, out = run_extendscript("photoshop", jsx)
        return f"{'✓' if ok and not out.startswith('ERROR') else '✗'} Photoshop: {out[:250]}"

    # ── Procesar carpeta en lote (Photoshop) ──
    if action == "batch":
        in_dir = (parameters.get("in_dir") or parameters.get("folder") or "").strip()
        if not in_dir or not Path(in_dir).exists():
            return f"Error: 'in_dir' inválido o inexistente ({in_dir or 'vacío'})."
        out_dir = (parameters.get("out_dir") or "").strip() or str(Path(in_dir) / "jarvis_out")
        jsx = photoshop_batch(
            in_dir, out_dir,
            max_side=int(parameters.get("max_side") or 1080),
            fmt=(parameters.get("format") or "jpg").lower().lstrip("."),
            quality=int(parameters.get("quality") or 80),
        )
        if player:
            player.write_log(f"  ▶️ Procesando carpeta en lote → {out_dir}...")
        ok, out = run_extendscript("photoshop", jsx, timeout=600)
        return f"{'✓' if ok and not out.startswith('ERROR') else '✗'} Photoshop: {out[:250]}"

    # ── Data merge (InDesign) ──
    if action == "data_merge":
        csv_path = (parameters.get("csv") or parameters.get("data") or "").strip()
        if not csv_path or not Path(csv_path).exists():
            return f"Error: 'csv' inválido o inexistente ({csv_path or 'vacío'})."
        try:
            import csv as _csv
            with open(csv_path, newline="", encoding="utf-8-sig") as fh:
                records = list(_csv.DictReader(fh))
        except Exception as e:
            return f"Error leyendo CSV: {e}"
        limit = parameters.get("limit")
        if limit:
            records = records[:int(limit)]
        if not records:
            return "Error: el CSV no tiene filas de datos."
        jsx = indesign_data_merge(records, margin=float(parameters.get("margin") or 36))
        if player:
            player.write_log(f"  ▶️ Maquetando {len(records)} registros en InDesign...")
        ok, out = run_extendscript("indesign", jsx, timeout=300)
        return f"{'✓' if ok and not out.startswith('ERROR') else '✗'} InDesign: {out[:250]}"

    # ── Operaciones básicas/intermedias (adobe_ops) ──
    from core import adobe_ops as ops

    def _run(jsx):
        ok, out = run_extendscript(app, jsx)
        flag = "✓" if ok and not out.startswith("ERROR") else "✗"
        return f"{flag} {ADOBE_APPS[app]['label']}: {out[:220]}"

    def _intify(v):
        try:
            return int(v) if v is not None and str(v) != "" else None
        except Exception:
            return None

    # Documentos (cualquier app)
    if action == "open":
        p = parameters.get("path") or parameters.get("file")
        return _run(ops.doc_open(p)) if p else "Decime la ruta del archivo a abrir."
    if action == "save":
        return _run(ops.doc_save())
    if action == "close":
        return _run(ops.doc_close(app))
    if action in ("info", "doc_info"):
        return _run(ops.doc_info(app))

    # Illustrator
    if action == "shape":
        return _run(ops.ai_shape(parameters.get("kind", "rectangle"),
                                 float(parameters.get("width", 200)), float(parameters.get("height", 200)),
                                 parameters.get("fill") or parameters.get("color") or "#000000",
                                 parameters.get("x"), parameters.get("y")))
    if action in ("outline_text", "outlines"):
        if app == "indesign":
            return _run(ops.id_outline_text())
        return _run(ops.ai_outline_text())
    if action == "fit_artboard":
        return _run(ops.ai_fit_artboard())
    if action == "export_artboards":
        dest = parameters.get("dest") or str(Path.home() / "Desktop")
        return _run(ops.ai_export_artboards(parameters.get("format", "png"), dest, float(parameters.get("scale") or 1)))
    if action == "align":
        return _run(ops.ai_align(parameters.get("how") or parameters.get("mode") or "center"))
    if action == "grid":
        return _run(ops.ai_grid(int(parameters.get("cols", 3)), float(parameters.get("gap", 20))))
    if action == "pathfinder":
        return _run(ops.ai_pathfinder(parameters.get("op") or parameters.get("mode") or "unite"))
    if action == "pattern":
        shapes = parameters.get("shapes")
        if isinstance(shapes, str):
            shapes = [s.strip() for s in re.split(r"[,\s]+", shapes) if s.strip()]
        colors = parameters.get("colors")
        if isinstance(colors, str):
            colors = [c.strip() for c in re.split(r"[,\s]+", colors) if c.strip()]
        return _run(ops.ai_pattern(shapes, int(parameters.get("cols", 6)), int(parameters.get("rows", 6)),
                                   float(parameters.get("gap", 0.25)), colors,
                                   parameters.get("layout", "grid"),
                                   bool(parameters.get("rotate")), bool(parameters.get("vary")),
                                   float(parameters.get("angle") or parameters.get("tilt") or 0)))
    if action in ("radial_repeat", "mandala"):
        return _run(ops.ai_radial_repeat(int(parameters.get("count", 8)),
                                         parameters.get("around", "artboard")))
    if action == "scatter":
        return _run(ops.ai_scatter(int(parameters.get("count", 20)),
                                   bool(parameters.get("rotate", True)), bool(parameters.get("vary", True))))
    if action in ("shape_of", "polygon_of"):
        # ¿elemento = imagen? (query la baja, o image=ruta)
        img = (parameters.get("image") or "").strip()
        q = (parameters.get("query") or "").strip()
        if not img and q:
            try:
                from actions.image_fetch import fetch_image
                if player:
                    player.write_log(f"🖼️ Bajando '{q}'...")
                img, _meta = fetch_image(q)
            except Exception as e:
                return f"No pude conseguir la imagen: {e}"
        return _run(ops.ai_polygon_of_elements(
            int(parameters.get("sides", 5)), int(parameters.get("per_side", 3)),
            float(parameters.get("radius", 200)), img or None,
            parameters.get("kind", "ellipse"), float(parameters.get("size", 60)),
            parameters.get("fill") or parameters.get("color") or "#c8821e",
            float(parameters.get("tilt") or parameters.get("angle") or 0),
            float(parameters.get("spin", 0))))
    if action == "tile":
        return _run(ops.ai_tile(int(parameters.get("rows", 4)), int(parameters.get("cols", 5)),
                                float(parameters.get("gap", 20)), int(parameters.get("skip_every", 5)),
                                float(parameters.get("tilt") or parameters.get("angle") or 0)))
    if action in ("gradient", "gradiente"):
        cols = parameters.get("colors")
        if isinstance(cols, str):
            cols = [c.strip() for c in re.split(r"[,\s]+", cols) if c.strip()]
        gtype = parameters.get("type") or parameters.get("gtype") or "linear"
        if app == "indesign":
            ca = (cols[0] if cols else None) or parameters.get("color_a") or "#1e90ff"
            cb = (cols[1] if cols and len(cols) > 1 else None) or parameters.get("color_b") or "#ffffff"
            return _run(ops.id_gradient(ca, cb, gtype))
        return _run(ops.ai_gradient(cols, gtype, float(parameters.get("angle", 0))))
    if action in ("stroke", "trazo"):
        return _run(ops.ai_stroke(parameters.get("color") or parameters.get("stroke") or "#000000",
                                  float(parameters.get("width", 1)), bool(parameters.get("none"))))
    if action in ("opacity", "opacidad"):
        return _run(ops.ai_opacity(float(parameters.get("value") or parameters.get("level") or 100)))
    if action == "blend":
        return _run(ops.ai_blend(int(parameters.get("steps", 6))))
    if action in ("reflect", "mirror"):
        return _run(ops.ai_reflect(parameters.get("axis") or "horizontal"))
    if action == "transform":
        return _run(ops.ai_transform(float(parameters.get("rotate", 0)), float(parameters.get("scale", 100))))
    if action == "arrange":
        return _run(ops.ai_arrange(parameters.get("order") or "front"))
    if action == "distribute":
        return _run(ops.ai_distribute(parameters.get("direction") or parameters.get("axis") or "horizontal"))
    if action == "text_on_path":
        return ("El texto en trazo headless es inestable en esta versión de Illustrator. "
                "Pedímelo con action=run (genero el ExtendScript) o hacelo a mano.")
    if action in ("effect", "efecto"):
        return ("Los efectos vivos (esquinas redondeadas, sombra, zigzag…) fallan headless "
                "si la figura se creó en otro paso (error MRAP de Illustrator). Pedímelo con "
                "action=run y lo genero todo en un solo script (crear figura + efecto), que sí funciona.")
    if action in ("star", "estrella"):
        return _run(ops.ai_star(int(parameters.get("points") or parameters.get("sides") or 5),
                                float(parameters.get("outer") or parameters.get("radius") or 120),
                                float(parameters.get("inner") or 55),
                                parameters.get("fill") or parameters.get("color") or "#f5b301"))
    if action in ("spiral", "espiral"):
        return _run(ops.ai_spiral(float(parameters.get("turns", 3)),
                                  float(parameters.get("radius", 150)),
                                  parameters.get("fill") or parameters.get("color") or "#1e90ff",
                                  float(parameters.get("width", 2))))
    if action in ("clip_mask", "mask", "mascara"):
        return _run(ops.ai_clip_mask())
    if action in ("round_rect", "rounded_rect"):
        return _run(ops.ai_round_rect(float(parameters.get("width", 200)), float(parameters.get("height", 140)),
                                      float(parameters.get("radius", 25)),
                                      parameters.get("fill") or parameters.get("color") or "#1e90ff"))
    if action in ("text", "texto"):
        return _run(ops.ai_text(parameters.get("text", ""), parameters.get("x"), parameters.get("y"),
                                float(parameters.get("size") or parameters.get("font_size") or 36),
                                parameters.get("fill") or parameters.get("color") or "#000000"))
    if action in ("group", "agrupar"):
        return _run(ops.ai_group(False))
    if action in ("ungroup", "desagrupar"):
        return _run(ops.ai_group(True))
    if action in ("swatches", "muestras"):
        cols = parameters.get("colors")
        if isinstance(cols, str):
            cols = [c.strip() for c in re.split(r"[,\s]+", cols) if c.strip()]
        return _run(ops.ai_swatches(cols))
    if action in ("artboard", "mesa"):
        return _run(ops.ai_artboard(float(parameters.get("width", 800)), float(parameters.get("height", 600))))
    if action in ("compound_path", "compound"):
        return _run(ops.ai_compound_path())
    if action == "place_linked":
        img = (parameters.get("image") or parameters.get("path") or "").strip()
        q = (parameters.get("query") or "").strip()
        if not img and q:
            try:
                from actions.image_fetch import fetch_image
                if player:
                    player.write_log(f"🖼️ Bajando '{q}'...")
                img, _m = fetch_image(q)
            except Exception as e:
                return f"No pude conseguir la imagen: {e}"
        if not img:
            return "Decime 'image' (ruta) o 'query' (qué imagen buscar)."
        return _run(ops.ai_place_linked(img, bool(parameters.get("embed"))))
    if action in ("line", "linea"):
        if app == "indesign":
            return _run(ops.id_line(float(parameters.get("x1", 20)), float(parameters.get("y1", 20)),
                                    float(parameters.get("x2", 120)), float(parameters.get("y2", 80)),
                                    parameters.get("color") or parameters.get("fill") or "#000000",
                                    float(parameters.get("width", 1))))
        return _run(ops.ai_line(float(parameters.get("x1", 100)), float(parameters.get("y1", 100)),
                                float(parameters.get("x2", 400)), float(parameters.get("y2", 400)),
                                parameters.get("color") or parameters.get("fill") or "#000000",
                                float(parameters.get("width", 2))))
    if action in ("wave", "onda"):
        return _run(ops.ai_wave(float(parameters.get("cycles", 3)), float(parameters.get("width", 400)),
                                float(parameters.get("amplitude") or parameters.get("amp") or 60),
                                parameters.get("color") or parameters.get("fill") or "#9b59b6",
                                float(parameters.get("stroke_width") or parameters.get("weight") or 2)))
    if action == "color_mode":
        return _run(ops.ai_color_mode(parameters.get("mode") or parameters.get("space") or "cmyk"))
    if action in ("join", "unir"):
        return _run(ops.ai_join())
    if action in ("concentric", "concentrico"):
        return _run(ops.ai_concentric(int(parameters.get("rings", 6)), float(parameters.get("max_radius") or parameters.get("radius") or 0),
                                      parameters.get("color") or parameters.get("fill") or "#2c3e50",
                                      float(parameters.get("width", 2))))
    if action in ("sunburst", "rafaga"):
        return _run(ops.ai_sunburst(int(parameters.get("count", 24)), float(parameters.get("radius", 0)),
                                    parameters.get("color") or parameters.get("fill") or "#e67e22",
                                    float(parameters.get("width", 2))))
    if action in ("arc", "arco"):
        return _run(ops.ai_arc(float(parameters.get("start_angle") or parameters.get("start") or 0),
                               float(parameters.get("sweep", 180)), float(parameters.get("radius", 150)),
                               parameters.get("color") or parameters.get("fill") or "#16a085",
                               float(parameters.get("width", 3))))
    if action == "area_text":
        return _run(ops.ai_area_text(parameters.get("text", ""), float(parameters.get("width", 300)),
                                     float(parameters.get("height", 200)), float(parameters.get("size", 18)),
                                     parameters.get("fill") or parameters.get("color") or "#000000"))
    if action in ("font", "fuente"):
        _f = parameters.get("font")
        _sz = float(parameters.get("size") or parameters.get("font_size") or 0)
        _tr = parameters.get("tracking")
        _tr = None if _tr in (None, "") else float(_tr)
        _ld = float(parameters.get("leading") or 0)
        if app == "photoshop":
            return _run(ops.ps_font(_f, _sz, _tr, _ld))
        if app == "indesign":
            return _run(ops.id_font(_f, _sz, _tr, _ld))
        return _run(ops.ai_font(_f, _sz, _tr, _ld))
    if action in ("text_align", "alinear_texto"):
        al = parameters.get("align") or parameters.get("alignment") or parameters.get("how") or "left"
        if app == "photoshop":
            return _run(ops.ps_text_align(al))
        if app == "indesign":
            return _run(ops.id_text_align(al))
        return _run(ops.ai_text_align(al))
    if action in ("dashed_stroke", "dashes"):
        dl = parameters.get("dashes")
        if isinstance(dl, str):
            dl = [d for d in re.split(r"[,\s]+", dl) if d]
        return _run(ops.ai_dashed_stroke(dl, parameters.get("color") or parameters.get("fill"),
                                         float(parameters.get("width", 2))))
    if action in ("layer", "capa"):
        return _run(ops.ai_layer(parameters.get("name") or "Capa", bool(parameters.get("rename"))))

    # InDesign
    if action == "new_doc" and app == "indesign":
        return _run(ops.id_new_doc(int(parameters.get("pages", 1)), float(parameters.get("margin", 12.7)),
                                   int(parameters.get("columns", 1)), float(parameters.get("width", 210)),
                                   float(parameters.get("height", 297))))
    if action == "place":
        content = parameters.get("text") or parameters.get("image") or parameters.get("path") or ""
        is_img = bool(parameters.get("image")) or bool(parameters.get("is_image"))
        return _run(ops.id_place(content, is_img)) if content else "Decime 'text' o 'image' (ruta)."
    if action == "page_numbers":
        return _run(ops.id_page_numbers())
    if action in ("find_replace", "replace"):
        return _run(ops.id_find_replace(parameters.get("find", ""), parameters.get("replace", "")))
    if action == "step_repeat":
        return _run(ops.id_step_repeat(int(parameters.get("rows", 3)), int(parameters.get("cols", 3)),
                                       float(parameters.get("gap", 5))))
    if action == "text_frame":
        return _run(ops.id_text_frame(parameters.get("text", ""), float(parameters.get("x", 20)),
                                      float(parameters.get("y", 20)), float(parameters.get("width", 170)),
                                      float(parameters.get("height", 60)), float(parameters.get("size", 18))))
    if action in ("table", "tabla"):
        return _run(ops.id_table(int(parameters.get("rows", 3)), int(parameters.get("cols", 3)),
                                 float(parameters.get("x", 20)), float(parameters.get("y", 20)),
                                 float(parameters.get("width", 170)), float(parameters.get("height", 80))))
    if action in ("rectangle", "rectangulo"):
        return _run(ops.id_rectangle(float(parameters.get("x", 20)), float(parameters.get("y", 20)),
                                     float(parameters.get("width", 80)), float(parameters.get("height", 50)),
                                     parameters.get("fill") or parameters.get("color") or "#1e90ff"))
    if action in ("corner_options", "corners", "esquinas"):
        return _run(ops.id_corner_options(float(parameters.get("radius", 5)),
                                          parameters.get("style") or parameters.get("kind") or "rounded"))
    if action in ("oval", "elipse"):
        return _run(ops.id_oval(float(parameters.get("x", 20)), float(parameters.get("y", 20)),
                                float(parameters.get("width", 60)), float(parameters.get("height", 60)),
                                parameters.get("fill") or parameters.get("color") or "#1e90ff"))
    if action in ("polygon", "poligono"):
        return _run(ops.id_polygon(float(parameters.get("x", 20)), float(parameters.get("y", 20)),
                                   float(parameters.get("width", 60)), float(parameters.get("height", 60)),
                                   int(parameters.get("sides", 6)), float(parameters.get("star_inset") or parameters.get("inset") or 0),
                                   parameters.get("fill") or parameters.get("color") or "#1e90ff"))
    if action == "drop_shadow":
        return _run(ops.id_drop_shadow(float(parameters.get("opacity", 60)), float(parameters.get("offset", 2)),
                                       float(parameters.get("size", 2))))
    if action in ("image_grid", "contact_sheet"):
        folder = (parameters.get("folder") or parameters.get("in_dir") or parameters.get("dir") or "").strip()
        if not folder or not Path(folder).exists():
            return f"Error: 'folder' inválido o inexistente ({folder or 'vacío'})."
        return _run(ops.id_image_grid(folder, int(parameters.get("cols", 3)), float(parameters.get("margin", 12)),
                                      float(parameters.get("gap", 4)), int(parameters.get("limit", 30))))
    if action in ("add_pages", "agregar_paginas"):
        return _run(ops.id_add_pages(int(parameters.get("count") or parameters.get("pages") or 1)))
    if action in ("guides", "guias"):
        def _nums(v):
            if isinstance(v, str):
                v = [n for n in re.split(r"[,\s]+", v) if n]
            return [float(n) for n in v] if isinstance(v, (list, tuple)) else []
        return _run(ops.id_guides(_nums(parameters.get("horizontals") or parameters.get("h")),
                                  _nums(parameters.get("verticals") or parameters.get("v"))))
    if action in ("fit", "ajustar"):
        return _run(ops.id_fit(parameters.get("mode") or parameters.get("kind") or "content_to_frame"))
    if action in ("paragraph_style", "estilo_parrafo"):
        return _run(ops.id_paragraph_style(parameters.get("name") or "Cuerpo", parameters.get("font"),
                                           float(parameters.get("size") or 0), float(parameters.get("leading") or 0),
                                           parameters.get("align") or parameters.get("alignment") or "left",
                                           parameters.get("color") or parameters.get("fill")))
    if action in ("text_columns", "columnas_texto"):
        return _run(ops.id_text_columns(int(parameters.get("count") or parameters.get("cols") or 2),
                                        float(parameters.get("gutter") or parameters.get("gap") or 4)))
    if action in ("bullets", "vinetas"):
        return _run(ops.id_bullets(parameters.get("mode") or parameters.get("kind") or "bullet"))
    if action in ("master_page", "pagina_maestra"):
        return _run(ops.id_master_page(parameters.get("name") or "B-Master", float(parameters.get("margin", 12.7))))
    if action in ("apply_master", "aplicar_maestra"):
        pidx = parameters.get("page_index")
        pidx = -1 if pidx in (None, "") else int(pidx)
        return _run(ops.id_apply_master(parameters.get("master_name") or parameters.get("name"), pidx))
    if action in ("text_wrap", "cenir_texto"):
        return _run(ops.id_text_wrap(parameters.get("mode") or parameters.get("kind") or "bounding",
                                     float(parameters.get("offset", 3))))
    if action in ("object_style", "estilo_objeto"):
        return _run(ops.id_object_style(parameters.get("name") or "Caja",
                                        parameters.get("fill") or parameters.get("color"),
                                        parameters.get("stroke") or parameters.get("stroke_color"),
                                        float(parameters.get("stroke_weight") or parameters.get("width") or 0)))
    if action in ("place_text_file", "colocar_texto"):
        p = (parameters.get("path") or parameters.get("file") or "").strip()
        if not p or not Path(p).exists():
            return f"Error: 'path' inválido o inexistente ({p or 'vacío'})."
        return _run(ops.id_place_text_file(p, float(parameters.get("x", 20)), float(parameters.get("y", 20)),
                                           float(parameters.get("width", 170)), float(parameters.get("height", 200))))
    if action in ("thread_frames", "hilar_marcos"):
        return _run(ops.id_thread_frames())
    if action in ("id_layer",):
        return _run(ops.id_layer(parameters.get("name") or "Capa", parameters.get("color") or parameters.get("fill")))
    if action in ("toc", "tabla_contenido"):
        return _run(ops.id_toc(parameters.get("style") or parameters.get("style_name") or "Cuerpo",
                               parameters.get("title") or "Contenido"))

    # Photoshop
    if action == "new_doc" and app == "photoshop":
        return _run(ops.ps_new_doc(int(parameters.get("width", 1920)), int(parameters.get("height", 1080)),
                                   int(parameters.get("resolution", 72))))
    if action == "resize":
        return _run(ops.ps_resize(_intify(parameters.get("max_side")), _intify(parameters.get("width")),
                                  _intify(parameters.get("height"))))
    if action == "crop":
        box = parameters.get("box")
        if not (isinstance(box, (list, tuple)) and len(box) == 4):
            return "box = [left, top, right, bottom]."
        return _run(ops.ps_crop(box))
    if action == "adjust":
        k = (parameters.get("kind") or parameters.get("type") or "bw").lower()
        val = float(parameters.get("value", 0))
        if k in ("invert", "invertir", "posterize", "posterizar", "threshold", "umbral"):
            return _run(ops.ps_adjust2(k, val))
        return _run(ops.ps_adjust(k, val))
    if action == "canvas":
        return _run(ops.ps_canvas(parameters.get("mode") or "trim",
                                  parameters.get("width"), parameters.get("height")))
    if action == "rotate_canvas":
        return _run(ops.ps_rotate_canvas(float(parameters.get("degrees", 90))))
    if action == "fill":
        return _run(ops.ps_fill(parameters.get("color") or parameters.get("fill") or "#ffffff"))
    if action == "layer_style":
        return _run(ops.ps_layer_style(parameters.get("kind") or parameters.get("style") or "drop_shadow",
                                       parameters.get("color") or "#000000",
                                       float(parameters.get("size", 10)), float(parameters.get("opacity", 75)),
                                       float(parameters.get("angle", 120)), float(parameters.get("distance", 8))))
    if action == "blend_mode":
        mode = parameters.get("mode") or parameters.get("kind") or "multiply"
        if app == "illustrator":
            return _run(ops.ai_blend_mode(mode))
        return _run(ops.ps_blend_mode(mode))
    if action == "layer_opacity":
        return _run(ops.ps_layer_opacity(float(parameters.get("value") or parameters.get("opacity") or 100)))
    if action == "duplicate_layer":
        return _run(ops.ps_duplicate_layer())
    if action == "new_layer":
        return _run(ops.ps_new_layer(parameters.get("name") or "Capa"))
    if action == "hue_saturation":
        return _run(ops.ps_hue_saturation(float(parameters.get("hue", 0)),
                                          float(parameters.get("saturation") or parameters.get("sat") or 0),
                                          float(parameters.get("lightness") or parameters.get("light") or 0)))
    if action in ("rasterize", "rasterizar"):
        return _run(ops.ps_rasterize())
    if action == "transform_layer":
        return _run(ops.ps_transform_layer(float(parameters.get("rotate", 0)), float(parameters.get("scale", 100)),
                                           float(parameters.get("dx", 0)), float(parameters.get("dy", 0))))
    if action in ("levels", "niveles"):
        return _run(ops.ps_levels(int(parameters.get("black", 0)), int(parameters.get("white", 255)),
                                  float(parameters.get("gamma", 1.0))))
    if action == "color_balance":
        def _triple(v):
            if isinstance(v, str):
                v = [t for t in re.split(r"[,\s]+", v) if t]
            return v if isinstance(v, (list, tuple)) else None
        return _run(ops.ps_color_balance(_triple(parameters.get("shadows")),
                                         _triple(parameters.get("midtones")),
                                         _triple(parameters.get("highlights"))))
    if action == "clipping_mask":
        return _run(ops.ps_clipping_mask())
    if action in ("flip", "voltear"):
        return _run(ops.ps_flip(parameters.get("target") or "layer",
                                parameters.get("axis") or parameters.get("direction") or "horizontal"))
    if action in ("curves", "curvas"):
        pts = parameters.get("points")
        if isinstance(pts, str):
            nums = [float(n) for n in re.split(r"[,\s]+", pts) if n]
            pts = [nums[i:i + 2] for i in range(0, len(nums) - 1, 2)]
        return _run(ops.ps_curves(pts))
    if action in ("smart_object", "objeto_inteligente"):
        return _run(ops.ps_smart_object())
    if action in ("photo_filter", "filtro_foto"):
        return _run(ops.ps_photo_filter(parameters.get("color") or parameters.get("filter") or "warm",
                                        float(parameters.get("density", 25))))
    if action in ("auto_tone", "auto"):
        return _run(ops.ps_auto(parameters.get("mode") or parameters.get("kind") or "contrast"))
    if action in ("layer_mask", "mascara_capa"):
        rev = parameters.get("reveal")
        rev = True if rev is None else bool(rev)
        return _run(ops.ps_layer_mask(rev))
    if action in ("black_white", "blanco_negro"):
        return _run(ops.ps_black_white(parameters.get("tint") or parameters.get("color")))
    if action in ("lens_flare", "destello"):
        return _run(ops.ps_lens_flare(float(parameters.get("brightness") or parameters.get("amount") or 120)))
    if action in ("distort", "distorsion"):
        return _run(ops.ps_distort(parameters.get("kind") or parameters.get("type") or "twirl",
                                   float(parameters.get("amount") or parameters.get("value") or 50)))
    if action in ("unsharp", "enfoque"):
        return _run(ops.ps_unsharp(float(parameters.get("amount", 100)), float(parameters.get("radius", 1.5)),
                                   int(parameters.get("threshold", 2))))
    if action in ("warp_text", "deformar_texto"):
        return _run(ops.ps_warp_text(parameters.get("style") or parameters.get("kind") or "arc",
                                     float(parameters.get("bend", 0.5))))
    if action in ("text_styled", "texto_estilizado"):
        _tr = parameters.get("tracking")
        return _run(ops.ps_text_styled(parameters.get("text", ""), float(parameters.get("size") or parameters.get("font_size") or 72),
                                       parameters.get("fill") or parameters.get("color") or "#000000",
                                       parameters.get("font"), (None if _tr in (None, "") else float(_tr)),
                                       float(parameters.get("leading") or 0),
                                       parameters.get("align") or parameters.get("alignment") or "left",
                                       parameters.get("x"), parameters.get("y"),
                                       bool(parameters.get("box")), float(parameters.get("box_w", 600)),
                                       float(parameters.get("box_h", 200))))
    if action in ("select", "seleccionar"):
        return _run(ops.ps_select(parameters.get("kind") or parameters.get("type") or "all",
                                  parameters.get("box"), float(parameters.get("feather", 0))))
    if action in ("select_color", "seleccionar_color"):
        return _run(ops.ps_select_color(parameters.get("color") or parameters.get("hex") or "#ffffff",
                                        int(parameters.get("tolerance") or parameters.get("fuzziness") or 32)))
    if action in ("content_aware_fill", "relleno_contenido"):
        return _run(ops.ps_content_aware_fill())
    if action in ("feather_selection", "suavizar_seleccion"):
        return _run(ops.ps_feather_selection(float(parameters.get("radius") or parameters.get("value") or 5)))
    if action in ("crop_to_selection", "recortar_seleccion"):
        return _run(ops.ps_crop_to_selection())
    if action in ("adjustment_layer", "capa_ajuste"):
        return _run(ops.ps_adjustment_layer(parameters.get("kind") or parameters.get("type") or "brightness",
                                            float(parameters.get("value", 0)), float(parameters.get("value2") or parameters.get("contrast") or 0)))
    if action in ("gradient_map", "mapa_degradado"):
        cols = parameters.get("colors")
        if isinstance(cols, str):
            cols = [c.strip() for c in re.split(r"[,\s]+", cols) if c.strip()]
        ca = (cols[0] if cols else None) or parameters.get("color_a") or "#000000"
        cb = (cols[1] if cols and len(cols) > 1 else None) or parameters.get("color_b") or "#ffffff"
        return _run(ops.ps_gradient_map(ca, cb))
    if action == "place_image":
        img = (parameters.get("image") or parameters.get("path") or "").strip()
        q = (parameters.get("query") or "").strip()
        if not img and q:
            try:
                from actions.image_fetch import fetch_image
                img, _m = fetch_image(q)
            except Exception as e:
                return f"No pude conseguir la imagen: {e}"
        if not img:
            return "Decime 'image' (ruta) o 'query' (qué imagen buscar)."
        return _run(ops.ps_place(img))
    if action == "filter":
        return _run(ops.ps_filter(parameters.get("kind") or parameters.get("type") or "blur",
                                  float(parameters.get("value", 0) or parameters.get("amount", 0) or 0),
                                  float(parameters.get("angle", 0))))
    if action == "text_layer":
        return _run(ops.ps_text_layer(parameters.get("text", ""), float(parameters.get("font_size", 72)),
                                      parameters.get("fill") or "#000000"))
    if action == "flatten":
        return _run(ops.ps_flatten())
    if action == "export_layers":
        dest = parameters.get("dest") or str(Path.home() / "Desktop" / "layers")
        return _run(ops.ps_export_layers(dest))

    # Ejecutar script crudo provisto
    if action == "script":
        jsx = parameters.get("script", "")
        if not jsx:
            return "Error: falta 'script' (código .jsx)."
        if player:
            player.write_log(f"🎨 Ejecutando script en {app}...")
        ok, out = run_extendscript(app, jsx)
        return f"{'✓' if ok else '✗'} {app}: {out[:300]}"

    # NL → script
    request = (parameters.get("request") or "").strip()
    if not request:
        return "Error: falta 'request' (qué querés hacer)."

    dry_run = action == "preview" or parameters.get("dry_run")

    if player:
        player.write_log(f"🎨 {app}: generando script para '{request[:60]}'...")

    prev_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            spec = _generate_script(app, request, prev_error)
        except Exception as e:
            return f"Error generando script: {e}"

        jsx = spec.get("script", "")
        summary = spec.get("summary", "")
        if not jsx:
            return "Gemini no devolvió script."

        if dry_run:
            return (
                f"📋 (PREVIEW, no ejecutado) {app} — {summary}\n"
                f"destructivo: {spec.get('destructive')}\n\n"
                f"--- script ---\n{jsx[:1200]}"
            )

        if player:
            player.write_log(f"  ▶️ Ejecutando (intento {attempt}): {summary[:60]}")
        ok, out = run_extendscript(app, jsx)
        if ok:
            return f"✓ {ADOBE_APPS[app]['label']}: {summary}. Resultado: {out[:200]}"

        prev_error = out
        if player:
            player.write_log(f"  ❌ Falló: {out[:100]}")

    return (
        f"No pude completar '{request[:50]}' en {app} tras {MAX_RETRIES} intentos.\n"
        f"Último error: {prev_error[:300]}"
    )
