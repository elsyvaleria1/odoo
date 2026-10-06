{
    "name": "Customer Tiers on CRM Leads",
    "version": "19.0.1.0.0",
    "category": "Sales/CRM",
    "summary": "Expose customer commercial tiers on leads and as a predictive-scoring option",
    "description": "Adds a related customer tier field, lead view integration and a registered scoring-frequency field. The tier follows the commercial partner; predictive scoring uses the existing CRM mechanism and its configured fields.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "partner_scoring",
        "crm",
    ],
    "data": [
        "data/crm_lead_scoring_frequency_field_data.xml",
        "views/crm_lead_views.xml",
    ],
    "auto_install": True,
}
