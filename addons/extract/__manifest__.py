{
    "name": "Document Extraction Framework",
    "version": "19.0.1.2.0",
    "oldest_upgradable_version": "19.0.1.1.0",
    "category": "Hidden",
    "sequence": 10,
    "summary": "Combine registered extraction strategies and track field results for review",
    "description": "Provides schemas, extractor registration, a strategy cascade and an extraction mixin with result, missing-field and correction records. Supports synchronous and queued extraction and a result-review widget. Usable document formats and extraction capabilities depend on registered readers and separately installed strategies.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
        "web",
    ],
    "external_dependencies": {
        "python": [
            "pymupdf",
        ],
    },
    "data": [
        "data/ir_job_channel.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "extract/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "extract/static/tests/**/*.test.js",
        ],
    },
}
