{
    "name": "Document Barcode Reader",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Decode barcodes from rendered document pages for extraction readers",
    "description": "Registers a document barcode reader backed by zxing-cpp for supported paged document types. Reads available page images, returns distinct decoded text values and logs per-page decoding failures. Requires the declared decoder dependency; downstream extractors interpret the decoded contents.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "Other OSI approved licence",
    "depends": [
        "extract",
    ],
    "external_dependencies": {
        "python": [
            "zxing-cpp",
        ],
    },
}
