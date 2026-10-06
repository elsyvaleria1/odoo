{
    "name": "Sustainability Workforce Report Data",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Populate sustainability report templates with workforce metrics",
    "description": "Adds report variables for employee demographics, employment types, turnover, tenure and pay gaps using the available HR records.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr",
        "esg_csrd",
    ],
    "data": [
        "data/esg_csrd_hr_report_template_data.xml",
    ],
    "auto_install": True,
}
