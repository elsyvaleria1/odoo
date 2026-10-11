{
    "name": "Subscription Timesheet Billing",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Calculate subscription service delivery from timesheets in the billing period",
    "description": "Adapts delivered quantities and invoice timesheet date ranges for subscription lines billed from timesheets. Uses the subscription period boundaries and suppresses remaining-hours display on subscription lines; it does not record employee time itself.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project_sale_subscription",
        "sale_timesheet",
    ],
    "auto_install": True,
}
