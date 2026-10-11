{
    "name": "Quality Wizard IoT Controls",
    "category": "Supply Chain/IoT",
    "summary": "Expose camera and measurement controls in the quality-check wizard",
    "description": "Adds device connection fields and picture or measurement widgets to the quality-check decision form. Controls are shown for the corresponding check type; device handling comes from Quality IoT and requires compatible configured hardware.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "quality_control",
        "quality_iot",
    ],
    "data": [
        "wizards/wizard_quality_check_decide_views.xml",
    ],
    "auto_install": True,
}
