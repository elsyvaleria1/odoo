{
    "name": "AI Document Field Extraction",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Extract schema-defined fields through configured text and vision models",
    "description": "Registers text and vision extraction strategies using schema-generated prompts and the machine-learning gateway. Requires a configured model available for the company and extraction purpose. Text requests use document text; vision requests send only the first rendered page and require a vision-capable model. Model failures return no result to the extraction cascade.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "LGPL-3",
    "depends": [
        "integration_machine_learning",
        "extract",
    ],
}
