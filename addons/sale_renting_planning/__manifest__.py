{
    "name": "Rental Shift Planning",
    "category": "Sales/Sales",
    "summary": "Link rental order periods with planned resource shifts",
    "description": "Adds role settings for rental synchronization and creates or updates planning slots from rental sales lines. Planning slots can create or reuse rental orders.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_planning",
        "sale_renting",
    ],
    "data": [
        "views/planning_role_views.xml",
        "views/planning_slot_views.xml",
        "views/sale_order_views.xml",
    ],
    "auto_install": True,
    "uninstall_hook": "uninstall_hook",
}
