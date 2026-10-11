{
    "name": "Local Speech Transcription",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Transcribe recordings on the server using provisioned speech models",
    "description": "Registers a CPU transcription reader using sherpa-onnx with Whisper and voice-activity models supplied in the configured model directory. Missing required models make the engine unavailable; optional speaker models add speaker labels. Shared models normally defer to peer engines, while complete purpose-specific model sets select local processing first.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "speech",
    ],
    "external_dependencies": {
        "python": [
            "av",
            "numpy",
            "sherpa_onnx",
        ],
    },
}
