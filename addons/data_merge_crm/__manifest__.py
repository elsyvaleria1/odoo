{
    "name": "CRM Duplicate Merging",
    "version": "1.0",
    "category": "Productivity/Data Cleaning",
    "summary": "Find and merge duplicate leads using CRM merge handling",
    "description": "Adds lead matching rules and connects the deduplication engine with CRM master-record selection and merge methods.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "data_cleaning",
        "crm",
    ],
    "data": [
        "data/data_merge_data.xml",
        "data/ir_model_data.xml",
    ],
    "auto_install": True,
}
