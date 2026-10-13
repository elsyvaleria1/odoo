from datetime import timedelta

from odoo import fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import date_utils

_debug = DebugLog(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    def compute_fiscalyear_dates(self, current_date) -> dict:
        self.check_singleton()
        return self._compute_fiscalyear_dates_by_company(current_date)[self.id]

    @_debug.perf.timed
    def _compute_fiscalyear_dates_by_company(self, current_date) -> dict[int, dict]:
        window = timedelta(days=366)
        day = fields.Date.to_date(current_date)
        fiscal_years_by_company = (
            self.env["account.fiscal.year"]
            .search_fetch(
                [
                    ("company_id", "in", self.root_id.ids),
                    ("date_from", "<=", day + window),
                    ("date_to", ">=", day - window),
                ],
                ["company_id", "date_from", "date_to"],
            )
            .grouped("company_id")
        )
        return {
            company.id: company._compute_fiscalyear_dates(
                current_date,
                fiscal_years_by_company.get(
                    company.root_id, self.env["account.fiscal.year"]
                ),
            )
            for company in self
        }

    def _compute_fiscalyear_dates(self, current_date, fiscal_years) -> dict:
        def fiscal_year_at(moment):
            day = fields.Date.to_date(moment)
            return next(
                (fy for fy in fiscal_years if fy.date_from <= day <= fy.date_to),
                fiscal_years.browse(),
            )

        fiscalyear = fiscal_year_at(current_date)
        _debug.logic(
            "fiscalyear_record_lookup",
            company=self,
            date=current_date,
            fiscalyear=fiscalyear,
            found=bool(fiscalyear),
        )
        if fiscalyear:
            return {
                "date_from": fiscalyear.date_from,
                "date_to": fiscalyear.date_to,
                "record": fiscalyear,
            }

        date_from, date_to = date_utils.get_fiscal_year(
            current_date,
            day=self.account_config_id.fiscalyear_last_day,
            month=int(self.account_config_id.fiscalyear_last_month),
        )

        if fiscalyear_from := fiscal_year_at(date_from):
            date_from = fiscalyear_from.date_to + timedelta(days=1)

        if fiscalyear_to := fiscal_year_at(date_to):
            date_to = fiscalyear_to.date_from - timedelta(days=1)

        _debug.logic(
            "fiscalyear_dates_computed",
            company=self,
            date_from=date_from,
            date_to=date_to,
            clipped_from=bool(fiscalyear_from),
            clipped_to=bool(fiscalyear_to),
        )
        return {"date_from": date_from, "date_to": date_to}
