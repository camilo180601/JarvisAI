---
name: git_control
description: Operaciones git (status, log, diff, commit, push, pull, branch, clone)
requires:
  bins: [git]
parameters:
  action:
    type: STRING
    description: status (default) | log | diff | add | commit | push | pull | branch | clone
  path:
    type: STRING
    description: Ruta al repo (default '.')
  message:
    type: STRING
    description: Mensaje para commit
  url:
    type: STRING
    description: URL para clone
  files:
    type: STRING
    description: Archivos para add (default '.')
  count:
    type: INTEGER
    description: Cantidad de commits a mostrar en log (default 10)
---

# git_control

Wrapper sobre el CLI `git` del sistema. Falla elegante si git no está instalado.

## Acciones soportadas

- `status` — `git status --short --branch`
- `log` — últimos N commits one-line
- `diff` — `git diff --stat`
- `add` — stage files
- `commit` — necesita `message`
- `push`, `pull` — operaciones de red (timeout 60s)
- `branch` — rama actual
- `clone` — necesita `url`

## Notas

- Requiere `git` en PATH (availability signal lo verifica).
- Cross-platform (Mac/Linux/Windows).
