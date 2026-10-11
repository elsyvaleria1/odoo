{
    "name": "Local Document OCR Reader",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Recognize text from document page images using RapidOCR",
    "description": "Registers an OCR text reader using RapidOCR and the declared ONNX Runtime dependency. Runs when the document reader cost ceiling permits it and cheaper readers have not supplied text. Produces page-separated text for downstream strategies; recognition and line structure depend on the source image and OCR model.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "Other OSI approved licence",
    "depends": [
        "extract",
    ],
    "external_dependencies": {
        "python": [
            "rapidocr",
            "onnxruntime",
        ],
    },
}
