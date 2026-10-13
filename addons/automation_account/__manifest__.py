{
    "name": "Accounting Automation Steps",
    "version": "19.0.1.8.0",
    "oldest_upgradable_version": "19.0.1.5.0",
    "category": "Accounting",
    "summary": "Add accounting document and reconciliation helpers to automation workflows",
    "description": "Extends automation runs with bank statement context and with workflow step types that create a document from a template, register and reconcile the run's statement line and apply a credit note to open invoices; each document step names its template, company, partner, date and taxes on its own form, and a step that works on an earlier document names the step that made it. The same operations stay available as helpers for Python steps. A collection banked by another company is settled through an intercompany journal each company sets. A run reports what its remaining declared steps are missing, and the wizard that starts a workflow from a statement line previews what each declared step will create. Requires suitable templates; this addon supplies accounting operations to the shared automation runtime.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "account_move_template",
        "automation",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_bank_statement_line_views.xml",
        "views/automation_runtime_views.xml",
        "views/res_company_views.xml",
        "wizards/wizard_account_bank_statement_line_start_automation_views.xml",
        "views/automation_account_menus.xml",
    ],
    "demo": [
        "demo/account_journal_demo.xml",
        "demo/account_move_template_demo.xml",
        "demo/automation_workflows_demo.xml",
        "demo/automation_runtime_demo.xml",
        "demo/automation_runtime_demo_realistic.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "automation_account/static/src/components/**/*",
        ],
    },
}
