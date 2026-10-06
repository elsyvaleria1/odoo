{
    "name": "Employee Document Requirements",
    "version": "19.0.1.1.0",
    "category": "Productivity/Documents",
    "summary": "Include employees in document requirement reports",
    "description": "Adds the employee entity mapping and access rules used by document compliance reporting. Document types and requirements remain configured in the document framework.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "document_compliance",
        "hr",
    ],
    "data": [
        "security/ir.access.csv",
        "security/ir_access.xml",
    ],
    "auto_install": True,
}
