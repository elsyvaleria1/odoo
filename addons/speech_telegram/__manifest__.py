{
    "name": "Telegram Bot Voice Notes",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Transcribe the voice notes a Telegram bot receives, keeping no recording",
    "description": "Adds one voice-note transcription for every Telegram bot: the note is heard through speech under the company's transcription policy and nothing of it is stored. Also ships the business terms the bots' users say, as speech vocabulary. Requires a usable speech engine; without one a bot tells its user to type instead.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "telegram",
        "speech",
    ],
    "data": [
        "data/speech_vocabulary_data.xml",
    ],
    "auto_install": True,
}
