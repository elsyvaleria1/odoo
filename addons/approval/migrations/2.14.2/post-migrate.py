from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref(
        "approval.ir_cron_hand_delegated_activities_over", raise_if_not_found=False
    )
    if cron and (cron.repeat_interval, cron.repeat_unit) == (1, "day"):
        cron.write({"repeat_unit": "hour"})
