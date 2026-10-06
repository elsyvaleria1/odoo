from odoo.libs.sql import SQL

_FLAG_SUFFIX = ".rolling_full_rebuild"


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        SQL(
            """
            INSERT INTO report_rolling_state (model, stale)
            SELECT left(key, -length(%(suffix)s)), value = '1'
              FROM ir_config_parameter
             WHERE right(key, length(%(suffix)s)) = %(suffix)s
            ON CONFLICT (model) DO NOTHING
            """,
            suffix=_FLAG_SUFFIX,
        )
    )
    cr.execute(
        SQL(
            "DELETE FROM ir_config_parameter WHERE right(key, length(%(suffix)s)) = %(suffix)s",
            suffix=_FLAG_SUFFIX,
        )
    )
