"""The own-attendance rows reach the sender's employee through hr.your_employee,
read on behalf of the chat's contact, instead of a domain that admitted every
user-less employee with a Telegram binding. The rows are noupdate, so they are
rewritten here."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

ROWS = {
    "hr_attendance_telegram.hr_employee_privilege_own_attendance": "",
    "hr_attendance_telegram.hr_attendance_privilege_own_attendance": "employee_id.",
    "hr_attendance_telegram.hr_version_privilege_own_attendance": "employee_id.",
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    predicate = env.ref("hr.access_predicate_your_employee", raise_if_not_found=False)
    if not predicate:
        _logger.warning(
            "hr.your_employee is not loaded: upgrade hr with hr_attendance_telegram; "
            "the own-attendance rows keep their domain until then"
        )
        return
    for xmlid, at in ROWS.items():
        row = env.ref(xmlid, raise_if_not_found=False)
        if not row or (row.reach == "predicate" and row.predicate_id == predicate):
            continue
        row.write(
            {
                "domain": False,
                "reach": "predicate",
                "predicate_id": predicate.id,
                "predicate_args": {"at": at},
            }
        )
        _logger.info("%s reaches through hr.your_employee", xmlid)
