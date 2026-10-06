{
    "name": "AI Gateway and Credential Integration",
    "version": "19.0.1.3.0",
    "category": "Hidden",
    "sequence": 10,
    "summary": "Connect AI requests to gateway policy checks and credential lookup",
    "description": "Adds company-purpose policy checks, credential-vault lookup, gateway transport selection and Anthropic model integration to AI services. Missing usable vault keys fall back to inherited credential lookup. File or raw-data requests and requests without a transport service retain inherited transport after the policy check; configured models and provider access are required.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "integration",
        "ai",
        "integration_machine_learning",
    ],
    "data": [
        "data/integration_ml_purpose_data.xml",
    ],
}
