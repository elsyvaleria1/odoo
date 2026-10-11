from odoo import SUPERUSER_ID, api
from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    for table, model, name in (
        ("ir_ui_menu", "ir.ui.menu", "menu_device_data_log_gps_report_main"),
        ("ir_act_window", "ir.actions.act_window", "action_device_data_log_gps_report"),
    ):
        cr.execute(
            SQL(
                """UPDATE %(table)s r
                   SET name = jsonb_build_object('en_US', r.name->>'en_US')
                  FROM ir_model_data d
                 WHERE d.module = 'device_gps' AND d.model = %(model)s
                   AND d.name = %(name)s AND d.res_id = r.id""",
                table=SQL.identifier(table),
                model=model,
                name=name,
            )
        )
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["device.data.log.gps.report"]._rolling_mark_stale()
