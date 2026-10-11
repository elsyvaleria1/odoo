from odoo import models

from ..models.mail_message import bypass_token


class WizardResPartnerMerge(models.TransientModel):
    _inherit = "wizard.res.partner.merge"

    def _get_unalterable_sources(self, src_partners):
        refused = super()._get_unalterable_sources(src_partners)
        groups = (
            self.env["account.move.line"]
            .sudo()
            ._read_group(
                [
                    ("move_id.inalterable_hash", "!=", False),
                    ("partner_id", "in", src_partners.ids),
                ],
                ["partner_id"],
            )
        )
        if groups:
            refused[
                self.env._("Partners that are used in hashed entries cannot be merged.")
            ] = src_partners.browse([partner.id for [partner] in groups])
        return refused

    def _update_reference_fields(self, src_partners, dst_partner):
        return super(
            WizardResPartnerMerge,
            self.with_context(bypass_audit=bypass_token),
        )._update_reference_fields(src_partners, dst_partner)

    def _get_fields_summable(self):
        return super()._get_fields_summable() + ["customer_rank", "supplier_rank"]
