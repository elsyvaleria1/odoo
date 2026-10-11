{
    "name": "Telegram Sale Order Confirmation",
    "version": "19.0.1.1.0",
    "category": "Sales/Sales",
    "summary": "Confirm approved sale orders from Telegram",
    "description": "Once a sale order's approval request is approved and the company does not confirm it automatically, the users named on the approval category receive the order summary in Telegram and a button that confirms it as them. Requires an approval bot with notifications enabled and linked user chats.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval_telegram",
        "approval_sale",
    ],
    "data": [
        "views/approval_category_views.xml",
    ],
}
