from odoo import api, models
from odoo.exceptions import UserError


class MixinHrPayrollCountryRestricted(models.AbstractModel):
    _name = "mixin.hr.payroll.country.restricted"
    _description = "Payroll Country Restriction Mixin"

    def _country_restriction(self) -> str | None:
        return None

    @api.model_create_multi
    def create(self, vals_list):
        country_restriction = self._country_restriction()
        if (
            vals_list
            and country_restriction
            and self.env.company.country_id.code != country_restriction
        ):
            raise UserError(
                self.env._(
                    "You must be logged in a %s company to use this feature",
                    country_restriction,
                )
            )
        return super().create(vals_list)
