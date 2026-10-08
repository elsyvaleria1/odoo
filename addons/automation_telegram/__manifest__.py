{
    "name": "Automation Telegram",
    "version": "1.1",
    "category": "Hidden",
    "summary": "Ask a question on Telegram from a workflow step and resume the run with the answer",
    "description": "Lets a workflow step send a message through a Telegram bot and wait for the person's answer: a text, a photo, a file, a voice note, a contact or a location. The answer is the event its On Event edge waits for, so a Without Event edge is the reminder or the timeout. Files are kept on the run and the answer becomes the asking step's output. Requires a private chat between the person and the bot.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "automation",
        "telegram",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/automation_telegram_wait_views.xml",
        "views/automation_telegram_menus.xml",
    ],
    "auto_install": True,
}
