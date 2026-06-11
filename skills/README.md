# JARVIS Skills

Sistema de skills modulares estilo OpenClaw. Cada skill es una carpeta auto-contenida.

## Estructura de una skill

```
skills/
├── tu_skill/
│   ├── SKILL.md       # Metadata + descripción (frontmatter YAML)
│   └── skill.py       # Implementación con `def run(parameters, player=None, speak=None) -> str`
```

## SKILL.md — formato

```markdown
---
name: nombre_skill
description: Una línea clara de qué hace
requires:
  packages: [requests, beautifulsoup4]   # paquetes Python que necesita
  bins: [git]                            # binarios en PATH (opcional)
  env: [API_KEY]                         # variables de entorno (opcional)
parameters:
  param1:
    type: STRING
    description: Qué es param1
    required: true
  param2:
    type: INTEGER
    description: Default 5
---

# tu_skill

Markdown libre. Notas, ejemplos, cómo se invoca.
```

## skill.py — formato

```python
def run(parameters: dict, player=None, speak=None) -> str:
    """Entry point. Debe llamarse exactamente `run`."""
    arg1 = parameters.get("param1", "")
    return f"Hice algo con {arg1}"
```

## Cómo agregás una skill nueva

### Manual (vos editando)
1. Crear `skills/mi_skill/SKILL.md` con frontmatter
2. Crear `skills/mi_skill/skill.py` con `def run(...)`
3. Reiniciar JARVIS (o esperar a hot-reload si está habilitado)
4. La skill aparece sola en el tool list de Gemini

### Por voz (vía `skill_teach`)
> "JARVIS, aprendete una skill nueva: cuando diga 'modo concentración', cerrá Slack y bajá volumen"

JARVIS genera la carpeta, escribe SKILL.md + skill.py, los testea en sandbox y los activa.

## Disponibilidad (availability signals)

Si `requires` tiene paquetes/binarios/env vars faltantes, la skill se **omite del tool list** automáticamente. JARVIS no la propone si no puede ejecutarla. Esto evita errores de runtime y mensajes "tool no instalado".

Para ver qué hay disponible:

```python
from core.skill_loader import list_skills_human
print(list_skills_human())
```

## Diferencia con `actions/`

- **`actions/`** — tools "core" de JARVIS (whatsapp, terminal, openrouter, etc.). Fijas, declaradas en `core/tool_declarations.py`. No tocar salvo refactor.
- **`skills/`** — tools dinámicas, agregadas por el usuario o por la IA. El usuario tiene control directo. Las creadas por voz viven acá.
