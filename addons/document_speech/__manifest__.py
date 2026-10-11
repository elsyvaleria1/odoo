{
    "name": "Document Recording Transcription",
    "version": "19.0.1.1.0",
    "category": "Hidden",
    "summary": "Request transcription of document attachments and expose transcript details",
    "description": "Adds a Transcribe action and related transcript text, state and availability fields to documents. Delegates transcription to the speech attachment implementation and exposes its subtitle helper; supported recordings and speech-provider configuration are determined by that dependency.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "speech",
    ],
    "data": [
        "views/document_document_views.xml",
    ],
    "auto_install": True,
}
