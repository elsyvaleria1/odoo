from odoo import fields, models


class Website(models.Model):
    _inherit = "website"
    _CREDENTIAL_FIELDS = {"address_autocomplete_key": "address_autocomplete_key"}

    address_autocomplete_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        classification="secret.credential",
        groups="base.group_system",
        help="The key the address provider is called with for this website's "
        "visitors, apart from the one internal users' lookups spend.",
    )

    def has_address_autocomplete(self) -> bool:
        return bool(
            self.env["ir.http"]._address_autocomplete_provider()
            and self.sudo().address_autocomplete_key
        )
