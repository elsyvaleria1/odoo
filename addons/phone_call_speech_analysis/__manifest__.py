{
    "name": "Phone Call Transcript Analysis",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Analyse the transcript of a recorded phone call once the call has ended",
    "description": "Adds the speech-analysis mixin to phone calls, whatever line carried them: once the recordings filed on an ended call are transcribed, the call gets a summary, topics, commitments, questions and moments. Requires a configured analysis model; a recording a business layer files on another record is analysed there instead.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "phone_call",
        "speech_analysis",
    ],
    "data": [
        "views/phone_call_views.xml",
    ],
    "auto_install": True,
}
