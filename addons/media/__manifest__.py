{
    "name": "Media Recording Timelines",
    "version": "19.0.1.1.0",
    "category": "Hidden",
    "summary": "Store attachment-backed media segments and play them as a timeline",
    "description": "Provides segment records, a timeline mixin and a browser playback widget for adopting business models. Segments carry time intervals and owner links, with overlap checks and retention hooks that stamp attachment expiry. Transcription and speech analysis are separate extensions; this addon manages the media structure and playback.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "views/media_segment_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "media/static/src/**/*",
        ],
    },
}
