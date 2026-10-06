{
    "name": "Security Change Set Approval Configuration",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Configure approval before activating security change sets",
    "description": "Installs an approval category and activation binding for security change sets, with self-approval disabled and the security-change approver group assigned. The binding requests approval and resumes activation after approval through the engine; this addon supplies configuration data rather than a separate activation implementation.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "approval",
    ],
    "data": [
        "data/approval_category_data.xml",
    ],
    "auto_install": True,
}
