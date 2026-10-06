{
    "name": "Sales Free Shipping Rewards",
    "category": "Sales/Sales",
    "summary": "Apply eligible loyalty free-shipping rewards to sales delivery charges",
    "description": "Adds free-shipping reward calculation and shipping-aware loyalty thresholds to sales orders. Requires an applicable loyalty program and a delivery line; transport and carrier service costs are not eliminated by the reward.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale_loyalty",
        "delivery",
    ],
    "data": [
        "views/loyalty_reward_views.xml",
    ],
    "auto_install": True,
}
