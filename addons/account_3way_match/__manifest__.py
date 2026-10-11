{
    "name": "Vendor Bill Payment Matching Status",
    "category": "Supply Chain/Purchase",
    "summary": "Compare vendor bill lines with purchase quantities and prices for payment review",
    "description": "Adds Yes, No and Exception payment-review statuses, a manual override and accounting dashboard filters. Matching follows the product billing policy: ordered-quantity billing compares ordered and invoiced quantities, while received-quantity billing considers receipts. Missing purchase links or price differences produce exceptions; the status is not an unconditional receipt-based payment lock.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "purchase",
    ],
    "data": [
        "views/account_invoice_view.xml",
        "views/account_journal_dashboard_view.xml",
    ],
    "uninstall_hook": "uninstall_hook",
}
