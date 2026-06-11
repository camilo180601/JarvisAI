# MEMORY — Hechos persistentes

> Hechos del mundo, decisiones tomadas, contexto cross-session.
> JARVIS escribe aquí lo importante. El usuario puede editar.

## Decisiones arquitecturales del proyecto

- **Modelo principal**: `gemini-2.5-flash-native-audio-preview-12-2025` (Live API, voz)
- **Modelo secundario** (delegación): `gemini-2.5-flash` (texto, via `openrouter_agent`)
- **OpenRouter eliminado**: ahora todo va a Gemini directo con la key del free tier.
- **Cross-platform**: Mac, Windows, Linux. Helpers en `core/platform_utils.py`.
- **Single API key**: solo `gemini_api_key` en `config/api_keys.json`.

## Skills system (Fase 1 — implementado)

- `skills/` con SKILL.md frontmatter + skill.py
- Loader: `core/skill_loader.py`
- Availability signals: si faltan paquetes/bins/env, la skill se omite automáticamente
- Las skills creadas por voz vivirán acá (Fase 2 pendiente)

## Convenciones de código

- Cross-platform por defecto: usar `core.platform_utils` en lugar de `sys.platform` directo
- Cero deps de Windows en imports top-level — siempre `try/except ImportError`
- Logs con prefijos `[JARVIS]` / `[Scheduler]` / `[SkillLoader]` para grep fácil
