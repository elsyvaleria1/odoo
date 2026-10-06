import psycopg

from odoo.exceptions import UserError

from . import controllers, models, wizards


def _pre_init_postgis(env) -> None:
    cr = env.cr
    cr.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
    if cr.fetchone():
        return
    try:
        with cr.savepoint():
            cr.execute("CREATE EXTENSION postgis")
    except psycopg.Error as exc:
        raise UserError(
            env._(
                "Error, can not automatically initialize spatial postgis"
                " support. Database user may have to be superuser and"
                " postgres/postgis extensions with their devel header have"
                " to be installed. If you do not want Odoo to connect with a"
                " super user you can manually prepare your database. To do"
                " this, open a client to your database using a super user and"
                " run:\n"
                "CREATE EXTENSION postgis;\n"
            ),
        ) from exc
