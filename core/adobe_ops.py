# -*- coding: utf-8 -*-
"""
adobe_ops.py — Fachada de compatibilidad (Fase 5).

Las operaciones se movieron a core/adobe/{common,illustrator,photoshop,indesign}.py.
Este módulo reexporta todo para que `from core import adobe_ops as ops; ops.ai_star(...)`
siga funcionando. Para agregar ops nuevas, editá el módulo de la app correspondiente.
"""
from core.adobe.common import *        # noqa: F401,F403
from core.adobe.illustrator import *   # noqa: F401,F403
from core.adobe.photoshop import *     # noqa: F401,F403
from core.adobe.indesign import *      # noqa: F401,F403
