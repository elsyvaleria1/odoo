{
    "name": "Speech - Model Gateway Engines",
    "version": "19.0.1.3.0",
    "category": "Hidden",
    "sequence": 10,
    "summary": "Route transcription and synthesis through configured model-gateway services",
    "description": "Registers speech readers and writers that select eligible gateway models and invoke supported transcription or synthesis operations. Model availability depends on company policy, credentials, capabilities and request limits. Requires usable service connections; adding a catalog record alone does not implement a new provider protocol.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "speech",
        "integration_machine_learning",
    ],
    "data": [
        "data/ai_models_data.xml",
        "data/integration_ml_purpose_data.xml",
    ],
    "auto_install": True,
}
