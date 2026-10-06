{
    "name": "Conditional AI Installation",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Schedule AI installation at setup when the pgvector availability check succeeds",
    "description": "Runs a post-install hook that checks pgvector availability and requests installation of an uninstalled AI module. Availability errors stop this hook without installing AI; the addon does not continuously monitor PostgreSQL or provide AI features itself.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "mail",
    ],
    "auto_install": True,
    "post_init_hook": "_auto_install_ai",
}
