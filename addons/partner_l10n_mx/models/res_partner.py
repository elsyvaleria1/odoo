from odoo import api, fields, models
from odoo.tools import SQL


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_mx_municipality_id = fields.Many2one(
        comodel_name="l10n_mx.municipality",
        domain="[('state_id', '=', state_id)]",
        help="Mexican municipality where this partner is located",
    )

    l10n_mx_postal_code_id = fields.Many2one(
        comodel_name="l10n_mx.postal_code",
        domain="[('state_id', '=', state_id)]",
        help="Mexican postal code (código postal) for this partner",
    )

    @api.onchange("l10n_mx_postal_code_id")
    def _onchange_l10n_mx_postal_code_id(self) -> None:
        postal_code = self.l10n_mx_postal_code_id
        if not postal_code:
            return

        if postal_code.state_id:
            self.state_id = postal_code.state_id
            self.country_id = postal_code.state_id.country_id

        if postal_code.municipality_id:
            self.l10n_mx_municipality_id = postal_code.municipality_id

        if postal_code.city:
            self.city = postal_code.city

        if postal_code.code:
            self.zip = postal_code.code

    @api.model
    def _get_l10n_mx_municipality_sql(self, partner: SQL) -> SQL:
        return SQL(
            """
            COALESCE(
                %(partner)s.l10n_mx_municipality_id,
                (SELECT postal.municipality_id
                   FROM l10n_mx_postal_code postal
                  WHERE postal.id = %(partner)s.l10n_mx_postal_code_id),
                (SELECT postal.municipality_id
                   FROM l10n_mx_postal_code postal
                  WHERE postal.active
                    AND postal.municipality_id IS NOT NULL
                    AND postal.code = NULLIF(TRIM(%(partner)s.zip), '')
                  LIMIT 1)
            )
            """,
            partner=partner,
        )
