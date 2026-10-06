import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ADDRESS_FIELDS = ("street", "street2", "city", "state_id", "zip", "country_id")


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "mixin.account.avatax.unique.code"]

    avalara_partner_code = fields.Char(
        help="Customer Code set in Avalara for this partner."
    )
    avalara_exemption_id = fields.Many2one(
        comodel_name="avatax.exemption",
        company_dependent=True,
        domain="['|', ('valid_country_ids', 'in', country_id), ('valid_country_ids', '=', False)]",
    )
    # field used to hide the address validation button when the partner is not in the US or Canada
    avalara_show_address_validation = fields.Boolean(
        compute="_compute_avalara_show_address_validation",
        store=False,
    )

    @api.depends("country_id")
    def _compute_avalara_show_address_validation(self) -> None:
        for partner in self:
            company = partner.company_id or self.env.company
            partner.avalara_show_address_validation = (
                company.avalara_address_validation
                and partner.street
                and (
                    not partner.country_id
                    or partner.fiscal_country_codes in ("US", "CA")
                )
            )

    def action_view_validation_wizard(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Validate address of %s", self.display_name),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.res.partner.update.address",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
