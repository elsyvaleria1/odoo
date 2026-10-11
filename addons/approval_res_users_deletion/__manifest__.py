{
    "name": "Account Deletion Approvals",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Route portal account deletion requests through configured approval rules",
    "description": "Adds approval requests to the account deletion queue and excludes pending or refused approvals from the deletion scheduler. The supplied self-service rule automatically approves requests; disable it and configure review steps to require human review. Queue rows without an approval state remain eligible under the inherited deletion conditions.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval",
    ],
    "data": [
        "data/approval_category_data.xml",
    ],
    "auto_install": True,
}
