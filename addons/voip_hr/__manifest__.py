{
    "name": "Employee Call Company Matching",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Identify calls between employees of the same company",
    "description": "Extends call participant company matching using employee records and supplies the required access entries.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "voip",
        "hr",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
