import psycopg

from odoo.db.schema import ensure_extension


def _auto_install_ai(env) -> None:
    try:
        ensure_extension(env.cr, "vector")
    except psycopg.Error:
        return

    env["ir.module.module"].sudo().search(
        [("name", "=", "ai"), ("state", "=", "uninstalled")]
    ).button_install()
