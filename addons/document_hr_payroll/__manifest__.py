{
    "name": "Payslip Document Filing",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Productivity/Documents",
    "summary": "File generated payslips and provide document-based payslip notifications",
    "description": "Adds payslip document tags, folder selection, access links and notification or resend actions. Creation checks depend on an employee user or enabled company HR document settings, together with the base document rules. Payroll generation remains in the payroll dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document_hr",
        "hr_payroll",
    ],
    "data": [
        "data/document_tag_data.xml",
        "data/mail_template_data.xml",
        "data/ir_action_server_data.xml",
        "views/res_config_settings_views.xml",
        "views/hr_payslip_views.xml",
        "views/hr_payroll_employee_declaration_views.xml",
        "data/hr_payroll_dashboard_warning_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "document_hr_payroll/static/src/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_documents_hr_payroll_post_init",
}
