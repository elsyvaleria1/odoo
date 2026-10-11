{
    "name": "Campaign Attribution Deduplication",
    "version": "1.0",
    "category": "Productivity/Data Cleaning",
    "summary": "Find duplicate campaign attribution records",
    "description": "Supplies matching rules and merge-enabled model configuration for UTM records in the shared deduplication engine.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "data_cleaning",
        "utm",
    ],
    "data": [
        "data/data_merge_data.xml",
        "data/ir_model_data.xml",
    ],
    "auto_install": True,
}
