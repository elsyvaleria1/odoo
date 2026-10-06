{
    "name": "Helpdesk Ticket Merging",
    "version": "1.0",
    "category": "Productivity/Data Cleaning",
    "summary": "Merge selected helpdesk tickets from the contextual action",
    "description": "Registers the ticket merge action and connects it to helpdesk-specific merging.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "data_cleaning",
        "helpdesk",
    ],
    "data": [
        "data/ir_model_data.xml",
    ],
    "auto_install": True,
}
