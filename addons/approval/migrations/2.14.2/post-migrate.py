from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # the hand-over moves reach and the Decider group when a delegation window
    # opens in the approver's timezone, so a daily run left the delegate locked
    # out for up to a day; a cron still at its shipped daily cadence becomes hourly
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref(
        "approval.ir_cron_hand_delegated_activities_over", raise_if_not_found=False
    )
    if cron and (cron.repeat_interval, cron.repeat_unit) == (1, "day"):
        cron.write({"repeat_unit": "hour"})
