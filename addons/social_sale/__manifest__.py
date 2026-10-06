{
    "name": "Social Post Sales Attribution",
    "version": "1.0",
    "category": "Marketing/Social Marketing",
    "summary": "Show sales order counts and posted invoice amounts associated with a social post source",
    "description": "Adds social post statistics and navigation using the recorded UTM source. The order count includes matching sales orders regardless of state. The amount aggregates posted product-line balances across invoices, refunds and receipts, including vendor documents, in accessible companies; it is not a measure of sales caused by the post.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "social",
        "sale",
    ],
    "data": [
        "views/social_post_views.xml",
    ],
    "auto_install": True,
}
