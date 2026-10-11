{
    "name": "Approval Automation Configuration",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Approvals",
    "sequence": 192,
    "summary": "Configure category automation links and conditional approval resets",
    "description": "Adds category automation settings and runtime references on approval requests. Active bindings with a reset condition receive a managed automation rule whose before-and-after filters detect entry into the condition and invoke approval coverage reset. Clearing the condition or disabling the binding removes its managed reset rule.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval",
        "automation",
    ],
    "data": [
        "views/approval_automation_views.xml",
    ],
    "auto_install": True,
}
