{
    "name": "Rental Quotation Templates",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Use rental products in quotation templates",
    "description": "Extend quotation-template product selection for rental orders. Adds the rental template views and menu entries.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_renting",
        "sale",
    ],
    "data": [
        "views/sale_order_template_views.xml",
        "views/sale_renting_menus.xml",
    ],
    "demo": [
        "demo/rental_management_demo.xml",
    ],
    "auto_install": True,
}
