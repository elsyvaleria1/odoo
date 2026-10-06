{
    "name": "Telegram Voice Replies for Discuss and Chatter",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "A voice note replying to an Odoo notification in Telegram is posted as its transcript",
    "description": "Replying to a delivered Odoo message with a Telegram voice note posts what it says, transcribed through speech under the company's transcription policy; the recording is kept nowhere. Requires a usable speech engine; without one the user is asked to type.",
    "author": "AgroMarin",
    "license": "OPL-1",
    "depends": [
        "mail_telegram",
        "speech_telegram",
    ],
    "auto_install": True,
}
