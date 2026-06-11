---
name: practica_idioma
description: Activa/ajusta/apaga el MODO PRÁCTICA DE IDIOMA. JARVIS conversa con vos en el idioma y NIVEL (MCER A1–C2) que pidas, para que practiques. Cuando el usuario dice "practiquemos inglés, soy B1", "conversemos en alemán nivel A2", "hablemos francés C1", "subí/bajá el nivel", "cambiá a portugués", "salí de práctica". Mientras está activo, JARVIS sostiene una conversación adaptada a tu nivel (vocabulario, velocidad y gramática) y te corrige con suavidad.
requires:
  packages: []
  bins: []
  env: []
parameters:
  action:
    type: STRING
    description: "on (activar o cambiar idioma/nivel) | off (salir de práctica) | level_up (subir un nivel) | level_down (bajar un nivel). Default on."
  language:
    type: STRING
    description: "Idioma a practicar: inglés, alemán, francés, portugués, italiano, japonés..."
  level:
    type: STRING
    description: "Nivel MCER: A1, A2, B1, B2, C1, C2 (también 'principiante', 'intermedio', 'avanzado')."
  topic:
    type: STRING
    description: "Tema opcional para la conversación (viajes, trabajo, comida, una entrevista, etc.)."
---

# practica_idioma

Modo de práctica conversacional por niveles. JARVIS habla con vos en el idioma y
nivel MCER que elijas, manteniendo el vocabulario y la complejidad acordes, te corrige
errores con tacto y te lleva la conversación. La conversación la sostiene el modelo
de voz (Gemini, multilingüe); esta skill fija idioma + nivel + tema y la regla de
SOUL.md mantiene el modo turno a turno.

## Niveles MCER
- A1/A2 (principiante): frases cortas y simples, presente, vocabulario básico, habla lento.
- B1/B2 (intermedio): conversación fluida cotidiana, varios tiempos verbales, vocabulario amplio.
- C1/C2 (avanzado): matices, expresiones idiomáticas, temas abstractos, ritmo nativo.

## Ejemplos

- "practiquemos inglés, soy B1" → practica_idioma(action="on", language="inglés", level="B1")
- "conversemos en alemán nivel A2 sobre viajes" → practica_idioma(action="on", language="alemán", level="A2", topic="viajes")
- "subí el nivel" → practica_idioma(action="level_up")
- "cambiá a francés" → practica_idioma(action="on", language="francés")
- "salí de práctica" / "modo normal" → practica_idioma(action="off")
