---
name: web_search
description: Búsqueda web vía DuckDuckGo (sin API key)
requires:
  packages: [duckduckgo_search]
parameters:
  query:
    type: STRING
    description: Texto a buscar
    required: true
  mode:
    type: STRING
    description: search (default) o compare para comparar items
  aspect:
    type: STRING
    description: Para mode=compare; price | specs | reviews
---

# web_search

Devuelve los mejores 3-5 resultados de DuckDuckGo formateados como texto.

## Ejemplos

- `web_search(query="precios PS5 Argentina")` → ranking de tiendas
- `web_search(query="RTX 4070 vs 4080", mode="compare", aspect="specs")` → comparación
