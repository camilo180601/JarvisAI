---
name: nivel_idioma
description: Activa/apaga el MODO EXAMEN DE NIVEL. JARVIS te hace preguntas en el idioma para estimar tu nivel MCER (A1–C2), subiendo o bajando la dificultad según cómo respondés, y al final te dice tu nivel aproximado. Cuando el usuario dice "evaluá mi nivel de inglés", "qué nivel tengo en alemán", "tomame un test de francés", "examen de nivel de portugués". Para salir: "terminá el examen", "ya está", "modo normal".
requires:
  packages: []
  bins: []
  env: []
parameters:
  action:
    type: STRING
    description: "on (empezar el examen de nivel) | off (terminar y dar el resultado). Default on."
  language:
    type: STRING
    description: "Idioma a evaluar: inglés, alemán, francés, portugués, italiano, japonés..."
---

# nivel_idioma

Modo examinador adaptativo. JARVIS te entrevista en el idioma, empezando por algo
simple y ajustando la dificultad pregunta a pregunta según tus respuestas (comprensión,
vocabulario, gramática, fluidez). Cuando termina (o le decís que pares), estima tu
nivel MCER (A1–C2) y lo justifica brevemente.

La evaluación la conduce el modelo de voz (Gemini, multilingüe); esta skill activa el
modo y la regla de SOUL.md lo mantiene turno a turno. Se enlaza con `practica_idioma`:
al terminar el examen, JARVIS puede ofrecer practicar en el nivel detectado.

## Ejemplos

- "evaluá mi nivel de inglés" → nivel_idioma(action="on", language="inglés")
- "qué nivel tengo en alemán" → nivel_idioma(action="on", language="alemán")
- "tomame un test de francés" → nivel_idioma(action="on", language="francés")
- "terminá el examen" / "ya está" → nivel_idioma(action="off")
