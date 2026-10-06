import psycopg

from odoo.exceptions import UserError

from odoo.addons.ai import pgvector_is_available


def _auto_install_ai(env) -> None:
    try:
        pgvector_is_available(env)
    except UserError, psycopg.Error:
        return

    env["ir.module.module"].sudo().search(
        [("name", "=", "ai"), ("state", "=", "uninstalled")]
    ).button_install()
