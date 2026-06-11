---
name: traductor
description: Activa/desactiva/ajusta el MODO TRADUCTOR. Cuando el usuario dice "convertite en traductor de X a Y", "modo traductor español a inglés/alemán/...", "traducime de X a Y", "cambiá idiomas de X a Y", "invertí los idiomas", "pará el modo traductor". Mientras está activo, JARVIS deja de conversar y SOLO traduce en voz lo que el usuario dice, del idioma origen al destino.
requires:
  packages: []
  bins: []
  env: []
parameters:
  action:
    type: STRING
    description: "on (activar o cambiar el par) | off (apagar: 'pará/salí del traductor', 'modo normal') | invert (invertir el par actual). Default on."
  source:
    type: STRING
    description: "Idioma de ORIGEN (lo que habla el usuario), ej español, inglés, alemán, francés, portugués..."
  target:
    type: STRING
    description: "Idioma DESTINO (a lo que se traduce), ej inglés, alemán, francés..."
---

# traductor

Modo traductor de voz. JARVIS deja de ser asistente y actúa como intérprete:
el usuario habla en el idioma ORIGEN y JARVIS dice en voz alta SOLO la traducción
al idioma DESTINO — sin comentarios, sin responder, sin agregar nada.

La traducción la hace el propio modelo de voz (Gemini, multilingüe nativo); esta
skill solo ACTIVA/DESACTIVA el modo y fija el par de idiomas. El comportamiento
persistente turno a turno lo refuerza la regla en SOUL.md.

## Ejemplos

- "convertite en traductor de español a inglés" → traductor(action="on", source="español", target="inglés")
- "modo traductor español alemán" → traductor(action="on", source="español", target="alemán")
- "ahora traducime de inglés a alemán" → traductor(action="on", source="inglés", target="alemán")
- "cambiá idiomas de francés a portugués" → traductor(action="on", source="francés", target="portugués")
- "invertí los idiomas" / "al revés" → traductor(action="invert")
- "pará el modo traductor" / "salí del traductor" / "modo normal" → traductor(action="off")
