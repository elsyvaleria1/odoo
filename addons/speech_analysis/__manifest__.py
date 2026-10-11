{
    "name": "Speech Transcript Analysis",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Extract summaries, commitments, questions and moments from transcripts",
    "description": "Provides an analysis mixin and finding records linked to a recording owner, plus speaker-level analysis fields. Uses the extraction and model dependencies when a completed transcript is ready or analysis is requested. Requires configured analysis services and company policy; generated findings are model interpretations for review.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "speech",
        "extract_ai",
    ],
    "data": [
        "security/ir.access.csv",
        "data/integration_ml_purpose_data.xml",
        "views/speech_commitment_views.xml",
        "views/speech_question_views.xml",
        "views/speech_moment_views.xml",
        "views/speech_analysis_menus.xml",
    ],
}
