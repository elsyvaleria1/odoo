import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # the record is noupdate: the data file no longer switching it off reaches
    # an existing database only through this write
    rule = env.ref(
        "hr_timesheet.timesheet_line_rule_portal_user", raise_if_not_found=False
    )
    if rule and not rule.active:
        rule.active = True
        _logger.info("hr_timesheet: portal timesheet rule activated")
