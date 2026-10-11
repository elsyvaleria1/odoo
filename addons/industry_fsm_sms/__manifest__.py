{
    "name": "Field Service SMS Templates",
    "version": "1.0",
    "category": "Services/Field Service",
    "summary": "Provide text-message templates for field-service tasks",
    "description": "Supplies field-service SMS template data used by the project stage notification integration. Delivery requires the configured SMS service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "industry_fsm",
        "project_sms",
    ],
    "data": [
        "data/industry_fsm_sms_data.xml",
    ],
    "demo": [
        "demo/industry_fsm_sms_demo.xml",
    ],
    "auto_install": True,
}
