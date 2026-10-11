import logging

from odoo import Command, models
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _compute_input_line_ids(self):
        res = super()._compute_input_line_ids()
        payroll_commission_plan = self.env["sale.commission.plan"].search(
            [("commission_payroll_input", "!=", "False")]
        )
        _debug.pipeline(
            "payslip_commission_plans",
            payslips=self,
            plans=payroll_commission_plan,
        )

        for (date_from, date_to, company_id), slips_sudo in (
            self.sudo()
            .grouped(lambda slip: (slip.date_from, slip.date_to, slip.company_id.id))
            .items()
        ):
            commissions = (
                self.env["sale.commission.report"]
                .sudo()
                .search_fetch(
                    [
                        ("user_id", "in", slips_sudo.employee_id.user_id.ids),
                        ("payment_date", ">=", date_from),
                        ("payment_date", "<=", date_to),
                        ("company_id", "=", company_id),
                        ("plan_id", "in", payroll_commission_plan.ids),
                    ],
                    ["commission", "user_id", "currency_id"],
                )
            )
            commission_per_user = commissions.grouped("user_id")
            _debug.perf.count(
                "payslip_commissions_read",
                payslips=slips_sudo,
                date_from=date_from,
                date_to=date_to,
                commissions=commissions,
                users=len(commission_per_user),
            )
            for slip_sudo in slips_sudo:
                user_commissions = commission_per_user.get(
                    slip_sudo.employee_id.user_id, self.env["sale.commission.report"]
                )
                for input, coms in user_commissions.grouped(
                    lambda com: com.plan_id.commission_payroll_input
                ).items():
                    if not input:
                        _debug.logic(
                            "payslip_commission_input_missing",
                            reason="plan_has_no_payslip_input",
                            payslip=slip_sudo,
                            commissions=coms,
                        )
                        continue
                    total = 0
                    for commission in coms:
                        total += commission.currency_id._convert(
                            commission.commission,
                            to_currency=slip_sudo.currency_id,
                            date=slip_sudo.date_to,
                            company=slip_sudo.company_id,
                        )
                    _debug.logic(
                        "payslip_commission_total",
                        payslip=slip_sudo,
                        input_type=input,
                        commissions=coms,
                        total=total,
                    )
                    if total:
                        slip_sudo.input_line_ids = [
                            Command.create({"amount": total, "input_type_id": input.id})
                        ]
        return res
