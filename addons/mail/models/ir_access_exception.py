from datetime import timedelta
from typing import Literal

from odoo import api, fields, models
from odoo.api import ValuesType


class IrAccessException(models.Model):
    _name = "ir.access.exception"
    _inherit = ["ir.access.exception", "mixin.mail.thread", "mixin.mail.activity"]

    date_reminded = fields.Datetime(
        string="Reviewers Reminded",
        copy=False,
        readonly=True,
    )

    def write(self, vals: ValuesType) -> Literal[True]:
        if "date_to" in vals and "date_reminded" not in vals:
            vals = {**vals, "date_reminded": False}
        return super().write(vals)

    @api.model
    def _cron_remind_lapsing(self, days: int = 7) -> None:
        now = fields.Datetime.now()
        lapsing = self.search(
            [
                ("state", "in", ["active"]),
                ("date_to", "<=", now + timedelta(days=days)),
                ("date_reminded", "=", False),
            ]
        )
        for exception in lapsing:
            for reviewer in exception.reviewer_ids:
                exception.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=fields.Date.to_date(exception.date_to),
                    summary=self.env._(
                        "Renew or let lapse: %(user)s's exception",
                        user=exception.user_id.name,
                    ),
                    note=exception.reason,
                    user_id=reviewer.id,
                )
        lapsing.filtered("reviewer_ids").date_reminded = now
