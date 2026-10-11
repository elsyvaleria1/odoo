from odoo import api, fields, models


class ResUsersSettings(models.Model):
    _name = "res.users.settings"
    _inherit = ["res.users.settings", "mixin.credential.holder"]
    _credential_holder_field = "voip_credential_id"
    _credential_purpose = "voip:settings"
    _CREDENTIAL_FIELDS = {
        "voip_secret": "voip_secret",
    }

    def _get_default_voip_provider(self):
        return (
            self.env["voip.provider"]
            .sudo()
            .search([("company_id", "in", [self.env.company.id, False])], limit=1)
            .sudo(False)
        )

    voip_provider_id = fields.Many2one(
        comodel_name="voip.provider",
        string="VoIP Provider",
        default=lambda self: self._get_default_voip_provider(),
    )

    voip_username = fields.Char(
        string="VoIP username / Extension number",
        help="The username (typically the extension number) that will be used to register with the PBX server.",
    )
    _voip_username_unique = models.UniqueIndex(
        "(voip_provider_id, voip_username) WHERE voip_username IS NOT NULL "
        "AND voip_username != ''",
        "This extension already belongs to another user of the same provider.",
    )
    voip_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="VoIP Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this user's VoIP secret.",
    )
    voip_secret = fields.Char(
        string="VoIP secret",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        help="The password that will be used to register with the PBX server.",
    )

    should_call_from_another_device = fields.Boolean(
        string="Call from another device",
        help="""Specify a phone number so that placing a call in Odoo Phone will ring your preferred device (your desk phone or cell phone) and then connect you to the recipient.""",
    )
    external_device_number = fields.Char(
        string="External device number",
        help="""Specify a phone number so that placing a call in Odoo Phone will ring your preferred device (your desk phone or cell phone) and then connect you to the recipient.""",
    )

    how_to_call_on_mobile = fields.Selection(
        selection=[
            ("ask", "Always Ask"),
            ("voip", "Odoo Phone"),
            ("phone", "Phone's Default App"),
        ],
        string="Default phone app",
        default="ask",
        required=True,
        help="""Choose which app to open when clicking on a phone number in the Odoo Mobile app.""",
    )

    do_not_disturb_until_dt = fields.Datetime(
        string="Do Not Disturb until",
        help="If set, Odoo Phone will be in Do Not Disturb mode until this time.",
    )

    @api.model
    def _format_settings(self, fields_to_format):
        res = super()._format_settings(fields_to_format)
        if "do_not_disturb_until_dt" in fields_to_format:
            res["do_not_disturb_until_dt"] = fields.Datetime.to_string(
                self.do_not_disturb_until_dt
            )
        return res
