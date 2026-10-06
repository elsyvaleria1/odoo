{
    "name": "Encrypted Field Mixin",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "sequence": 5,
    "summary": "Provide encryption helpers and key-version handling for adopting models",
    "description": "Supplies text and binary encryption/decryption helpers, key-version tracking and reencryption support using configured environment keys. Consumers must implement the field mappings and compute/inverse or write hooks that use these helpers. Installing the mixin does not automatically encrypt existing fields or unrelated models.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
}
