{
    "name": "Telegram Bot Model-Routed Assistants",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Give Telegram bot assistants a chat model routed through the machine-learning gateway, and voice-note hearing",
    "description": "Provides the assistant base the Telegram bots' AI features build on: it reads which provider and model a bot's settings name, under the route privilege, asks the machine-learning gateway for an eligible chat model for the assistant's purpose and the bot's acting company, and hears a voice note only when that model is available and a speech engine may transcribe it. It adds no model, view or setting of its own; the bots that use it declare their settings.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "speech_telegram",
        "integration_machine_learning",
    ],
    "auto_install": True,
}
