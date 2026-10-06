{
    "name": "Checkout Newsletter Subscription",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Subscribe shoppers to the configured newsletter when they opt in at checkout",
    "description": "Adds newsletter settings and a checkout subscription option. When the submitted form includes newsletter consent and an email address, it calls the mailing subscription flow for the website list; it does not send a campaign as part of checkout.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_sale",
        "website_mass_mailing",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/templates.xml",
    ],
    "auto_install": True,
}
