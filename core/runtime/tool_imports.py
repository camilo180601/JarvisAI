# -*- coding: utf-8 -*-
"""
tool_imports.py — Imports de todos los handlers de tools + memoria/episodic.

Extraído de main.py: el bloque de ~245 líneas de `try: from actions.X import Y`.
main.py hace `from core.runtime.tool_imports import *` para tener todos los nombres
que registra en STANDARD_TOOL_HANDLERS. Importar este módulo también dispara los
@tool de las actions (se registran en el registry).
"""
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

try:
    from actions.open_app          import open_app
except ImportError:
    open_app = None
try:
    from actions.weather_report    import weather_action
except ImportError:
    weather_action = None
try:
    from actions.reminder          import reminder
except ImportError:
    reminder = None
try:
    from actions.computer_settings import computer_settings
except ImportError:
    computer_settings = None
try:
    from actions.screen_vision import screen_vision
except ImportError:
    screen_vision = None
try:
    from actions.youtube_video     import youtube_video
except ImportError:
    youtube_video = None
try:
    from actions.desktop           import desktop_control
except ImportError:
    desktop_control = None
try:
    from actions.browser_control   import browser_control
except ImportError:
    browser_control = None
try:
    from actions.visual_click import visual_click
except ImportError:
    visual_click = None
try:
    from actions.file_controller   import file_controller
except ImportError:
    file_controller = None
try:
    from actions.web_search        import web_search as web_search_action
except ImportError:
    web_search_action = None
try:
    from actions.image_fetch        import image_fetch
except ImportError:
    image_fetch = None
try:
    from actions.mac_control         import mac_control
except ImportError:
    mac_control = None
try:
    from actions.media_edit          import media_edit
except ImportError:
    media_edit = None
try:
    from actions.browser_agent       import browser_agent
except ImportError:
    browser_agent = None
try:
    from actions.media_download      import media_download
except ImportError:
    media_download = None
try:
    from actions.smart_home          import smart_home
except ImportError:
    smart_home = None
try:
    from actions.model_manager        import consult_model, model_config
except ImportError:
    consult_model = model_config = None
try:
    from actions.manage_keys          import manage_keys
except ImportError:
    manage_keys = None
try:
    from actions.system_control       import system_control
except ImportError:
    system_control = None
try:
    from actions.realtime_info        import realtime_info
except ImportError:
    realtime_info = None
try:
    from actions.figma_control        import figma_control
except ImportError:
    figma_control = None
try:
    from actions.camera_vision        import camera_vision
except ImportError:
    camera_vision = None
try:
    from actions.set_theme            import set_theme
except ImportError:
    set_theme = None
try:
    from actions.code_agent           import code_agent
except ImportError:
    code_agent = None
try:
    from actions.claude_code          import claude_code
except ImportError:
    claude_code = None
try:
    from actions.antigravity          import antigravity
except ImportError:
    antigravity = None
try:
    from actions.trading_bot          import trading_bot
except ImportError:
    trading_bot = None
try:
    from actions.computer_control  import computer_control
except ImportError:
    computer_control = None
try:
    from actions.google_calendar   import google_calendar
except ImportError:
    google_calendar = None
try:
    from actions.spotify_control   import spotify_control
except ImportError:
    spotify_control = None
try:
    from actions.scheduler         import scheduler, start_runner
except ImportError:
    scheduler = None; start_runner = None
try:
    from actions.google_drive      import google_drive
except ImportError:
    google_drive = None
try:
    from actions.gmail_control     import gmail_control
except ImportError:
    gmail_control = None
try:
    from actions.google_maps       import google_maps
except ImportError:
    google_maps = None
try:
    from actions.rules_engine      import rules_engine, start_rules_runner, check_phrase_triggers, _run_action as _rules_run_action
except ImportError:
    rules_engine = None; start_rules_runner = None; check_phrase_triggers = None; _rules_run_action = None
try:
    from actions.whatsapp          import whatsapp
except ImportError:
    whatsapp = None
try:
    from actions.user_profile      import user_profile, record_action
except ImportError:
    user_profile = None; record_action = None
try:
    from actions.goals             import goals
except ImportError:
    goals = None
try:
    from actions.git_control       import git_control
except ImportError:
    git_control = None
try:
    from actions.knowledge_base    import knowledge_base
except ImportError:
    knowledge_base = None
try:
    from actions.document_creator  import document_creator
except ImportError:
    document_creator = None
try:
    from actions.document_manager  import document_manager
except ImportError:
    document_manager = None
try:
    from actions.web_navigation    import web_navigation
except ImportError:
    web_navigation = None
try:
    from actions.system_monitor    import system_monitor
except ImportError:
    system_monitor = None
try:
    from actions.terminal_agent    import terminal_agent
except ImportError:
    terminal_agent = None
try:
    from actions.native_ui         import native_ui
except ImportError:
    native_ui = None
try:
    from actions.morning_brief     import morning_brief, already_briefed_today, mark_briefed
except ImportError:
    morning_brief = None; already_briefed_today = None; mark_briefed = None
try:
    from actions.openrouter_agent  import openrouter_agent
except ImportError:
    openrouter_agent = None
try:
    from actions.skill_teach       import skill_teach
except ImportError:
    skill_teach = None
try:
    from actions.recall            import run as recall_run
except ImportError:
    recall_run = None
try:
    from actions.compact_sessions  import run as compact_sessions_run
except ImportError:
    compact_sessions_run = None
try:
    from actions.planner           import planner
except ImportError:
    planner = None
try:
    from actions.skill_workshop    import run as skill_workshop_run
except ImportError:
    skill_workshop_run = None
try:
    from actions.mcp_explorer      import (
        run as mcp_explorer_run,
        start_background_runner as start_mcp_explorer,
    )
except ImportError:
    mcp_explorer_run = None
    start_mcp_explorer = None
try:
    from actions.notifications     import run as notifications_run
    from core.notification_engine  import get_engine as get_notif_engine
except ImportError:
    notifications_run = None
    get_notif_engine = None
try:
    from actions.whatsapp_connect  import whatsapp_connect
except ImportError:
    whatsapp_connect = None
try:
    from actions.adobe_control     import adobe_control
except ImportError:
    adobe_control = None
try:
    from core.episodic             import EpisodicLogger
except ImportError:
    EpisodicLogger = None
