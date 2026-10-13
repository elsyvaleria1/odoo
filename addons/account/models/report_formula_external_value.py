from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

from odoo.addons.account.models.account_move import BYPASS_LOCK_CHECK

_debug = DebugLog(__name__)


class AccountReportExternalValue(models.Model):
    _inherit = "report.formula.external.value"

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        records = super().create(vals_list)
        self._check_lock_date_violation(
            set(self._prepare_vals_to_check_for_lock_date(records))
        )
        return records

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", records=self, fields=sorted(vals))
        vals_to_check = set(self._prepare_vals_to_check_for_lock_date(self))
        res = super().write(vals)
        vals_to_check.update(self._prepare_vals_to_check_for_lock_date(self))
        self._check_lock_date_violation(vals_to_check)
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_lock_date(self) -> None:
        self._check_lock_date_violation(
            set(self._prepare_vals_to_check_for_lock_date(self))
        )

    @api.model
    def _prepare_vals_to_check_for_lock_date(self, records):
        generic_tax_report = self.env.ref("account.generic_tax_report")
        bypass_tax_lock = (
            self.env.context.get("bypass_tax_lock_check") is BYPASS_LOCK_CHECK
        )
        for external_value in records:
            report = external_value.target_report_expression_id.report_line_id.report_id
            yield (
                not bypass_tax_lock
                and generic_tax_report
                in (
                    report
                    + report.root_report_id
                    + report.section_main_report_ids.root_report_id
                ),
                external_value.date,
                external_value.company_id,
            )

    @_debug.perf.timed
    def _check_lock_date_violation(self, vals_to_check) -> None:
        for is_tax, date, company_id in vals_to_check:
            violated_lock_dates = company_id._get_violated_lock_dates(
                date, is_tax, self.env["account.journal"]
            )
            if violated_lock_dates:
                _debug.logic(
                    "external_value_lock_date_violated",
                    company=company_id,
                    date=date,
                    is_tax=is_tax,
                    violations=violated_lock_dates,
                )
                raise ValidationError(
                    self.env._(
                        "You cannot update this value as it's locked by: %(lock_date_info)s.",
                        lock_date_info=self.env["res.company"]._format_lock_dates(
                            violated_lock_dates
                        ),
                    )
                )
