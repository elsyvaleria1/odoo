{
    "name": "CRM Business Card Extraction",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Read business cards through the extraction framework for CRM lead creation",
    "description": "Sets the attachment extraction type to business_card and maps returned card fields to CRM lead values. Uses the configured extraction strategies and falls back to the inherited business-card reader when no cards are returned; provider access and any fallback service requirements come from the dependencies.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "crm_enterprise",
        "extract_ml",
    ],
    "auto_install": True,
}
