def post_init_hook(env) -> None:
    Tender = env["purchase.tender"]
    for tender in Tender.search([("name", "=", env._("New"))]):
        orders = tender.order_ids
        tender.write(
            {
                "name": env["ir.sequence"]
                .with_company(orders.company_id[:1] or env.company)
                .next_by_code("purchase.tender"),
                "company_id": (orders.company_id[:1] or env.company).id,
                "user_id": orders.user_id[:1].id,
                "state": (
                    "awarded"
                    if any(order.state == "done" for order in orders)
                    else "cancel"
                    if orders and all(order.state == "cancel" for order in orders)
                    else "open"
                ),
            }
        )
