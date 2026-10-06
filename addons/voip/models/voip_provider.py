from odoo import api, fields, models


class VoipProvider(models.Model):
    _name = "voip.provider"
    _description = "VoIP Provider"

    name = fields.Char(required=True)
    company_id = fields.Many2one(comodel_name="res.company")
    ws_server = fields.Char(
        string="WebSocket",
        default="ws://localhost",
        groups="base.group_system",
        help="The URL of your WebSocket",
    )
    pbx_ip = fields.Char(
        string="PBX Server IP",
        default="localhost",
        groups="base.group_system",
        help="The IP address of your PBX Server",
    )
    mode = fields.Selection(
        selection=[
            ("demo", "Demo"),
            ("prod", "Production"),
        ],
        string="VoIP Environment",
        default="demo",
        required=True,
    )
    recording_enabled = fields.Boolean(
        export_string_translation=False,
        default=False,
    )
    recording_policy_option = fields.Selection(
        selection=[
            ("always", "Force recording of all calls. Users can't disable it."),
            ("user", "Let users decide when to record."),
        ],
        export_string_translation=False,
        default="always",
    )
    recording_policy = fields.Selection(
        selection=[
            ("always", "Force for all users"),
            ("user", "Let users decide"),
            ("disabled", "Disabled"),
        ],
        compute="_compute_recording_policy",
        inverse="_inverse_recording_policy",
    )

    @api.depends("recording_enabled", "recording_policy_option")
    def _compute_recording_policy(self) -> None:
        for provider in self:
            if not provider.recording_enabled:
                provider.recording_policy = "disabled"
            else:
                provider.recording_policy = provider.recording_policy_option

    def _inverse_recording_policy(self) -> None:
        for provider in self:
            if provider.recording_policy == "disabled":
                provider.recording_enabled = False
            else:
                provider.recording_enabled = True
                provider.recording_policy_option = provider.recording_policy
