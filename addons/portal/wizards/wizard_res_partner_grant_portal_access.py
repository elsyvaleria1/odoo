from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardResPartnerGrantPortalAccess(models.TransientModel):
    _name = "wizard.res.partner.grant.portal.access"
    _description = "Grant Portal Access"

    def _default_partner_ids(self):
        partner_ids = self.env.context.get(
            "default_partner_ids", []
        ) or self.env.context.get("active_ids", [])
        contact_ids = {}
        for partner in self.env["res.partner"].sudo().browse(partner_ids):
            contact_partners = (
                partner.child_ids.filtered(lambda p: p.type in ("contact", "other"))
                | partner
            )
            for contact_id in contact_partners.ids:
                contact_ids.setdefault(contact_id)

        return [Command.link(contact_id) for contact_id in contact_ids]

    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Partners",
        default=lambda self: self._default_partner_ids(),
    )
    user_ids = fields.One2many(
        comodel_name="wizard.res.partner.grant.portal.access.line",
        inverse_name="wizard_id",
        string="Users",
        compute="_compute_user_ids",
        store=True,
        readonly=False,
    )
    welcome_message = fields.Text(
        string="Invitation Message",
        help="This text is included in the email sent to new users of the portal.",
    )

    @api.depends("partner_ids")
    def _compute_user_ids(self) -> None:
        for portal_wizard in self:
            portal_wizard.user_ids = [
                Command.create(
                    {
                        "partner_id": partner.id,
                        "email": partner.email,
                    }
                )
                for partner in portal_wizard.partner_ids
            ]

    @api.model
    def action_view_wizard(self):
        portal_wizard = self.create({})
        return portal_wizard._action_view_modal()

    def _action_view_modal(self) -> dict:
        return {
            "name": self.env._("Portal Access Management"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.res.partner.grant.portal.access",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
