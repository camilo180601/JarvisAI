"""Skill: web_search — delega en actions/web_search.py (única fuente de verdad).

La action tiene el motor actualizado (lib `ddgs` + fallbacks); esta skill la
pisa por override, así que simplemente la reusa.
"""


def run(parameters: dict, player=None, speak=None) -> str:
    from actions.web_search import web_search
    return web_search(parameters, player=player)
