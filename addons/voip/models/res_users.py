from odoo import api, fields, models

from odoo.addons.mail.tools.discuss import Store


class ResUsers(models.Model):
    _inherit = "res.users"

    last_seen_phone_call = fields.Many2one(comodel_name="phone.call")
    external_device_number = fields.Char(
        compute="_compute_external_device_number",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )
    how_to_call_on_mobile = fields.Selection(
        selection=[
            ("voip", "Call with Odoo Phone"),
            ("phone", "Call with phone's default app"),
            ("ask", "Always ask before calling"),
        ],
        compute="_compute_how_to_call_on_mobile",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )
    should_call_from_another_device = fields.Boolean(
        compute="_compute_should_call_from_another_device",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )
    voip_provider_id = fields.Many2one(
        comodel_name="voip.provider",
        compute="_compute_voip_provider_id",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )
    voip_secret = fields.Char(
        compute="_compute_voip_secret",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )
    voip_username = fields.Char(
        compute="_compute_voip_username",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + self._get_fields_voip_user_configuration()

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return (
            super().SELF_WRITEABLE_FIELDS + self._get_fields_voip_user_configuration()
        )

    @api.depends("res_users_settings_id.external_device_number")
    def _compute_external_device_number(self) -> None:
        for user in self:
            user.external_device_number = (
                user.res_users_settings_id.external_device_number
            )

    @api.depends("res_users_settings_id.how_to_call_on_mobile")
    def _compute_how_to_call_on_mobile(self) -> None:
        for user in self:
            user.how_to_call_on_mobile = (
                user.res_users_settings_id.how_to_call_on_mobile
            )

    @api.depends("res_users_settings_id.should_call_from_another_device")
    def _compute_should_call_from_another_device(self) -> None:
        for user in self:
            user.should_call_from_another_device = (
                user.res_users_settings_id.should_call_from_another_device
            )

    @api.depends("res_users_settings_id.voip_provider_id")
    def _compute_voip_provider_id(self) -> None:
        for user in self:
            user.voip_provider_id = user.res_users_settings_id.voip_provider_id

    @api.depends("res_users_settings_id.voip_secret")
    def _compute_voip_secret(self) -> None:
        self.voip_secret = False
        for user in self:
            if user._filtered_access("write") or user == self.env.user:
                user.voip_secret = user.res_users_settings_id.voip_secret

    @api.depends("res_users_settings_id.voip_username")
    def _compute_voip_username(self) -> None:
        for user in self:
            user.voip_username = user.res_users_settings_id.voip_username

    @api.model
    def _get_fields_voip_user_configuration(self) -> list[str]:
        return [
            "external_device_number",
            "how_to_call_on_mobile",
            "should_call_from_another_device",
            "voip_secret",
            "voip_username",
            "voip_provider_id",
        ]

    @api.model
    def reset_last_seen_phone_call(self) -> None:
        domain = [("user_id", "=", self.env.user.id)]
        last_call = self.env["phone.call"].search(domain, order="id desc", limit=1)
        self.env.user.last_seen_phone_call = last_call.id

    def _get_voip_config(self) -> dict:
        provider = self.env.user.voip_provider_id
        return {
            "callActivityTypeId": self.env["mail.activity.type"]
            .search([("category", "=", "phonecall")], limit=1)
            .id,
            "mode": provider.mode or "demo",
            "missedCalls": self.env["phone.call"]._get_number_of_missed_calls(),
            "pbxAddress": provider.pbx_ip or "localhost",
            "recordingPolicy": provider.recording_policy or "disabled",
            "webSocketUrl": provider.ws_server or "ws://localhost",
        }

    def _init_store_data(self, store: Store) -> None:
        super()._init_store_data(store)
        if not self.env.user._is_internal():
            return
        store.add_global_values(voipConfig=self._get_voip_config())

    def _inverse_voip_settings(self) -> None:
        for user in self:
            settings = (
                self.env["res.users.settings"]
                .with_privilege(
                    "base.privilege_write_user_settings",
                    reason="a preference written with its user",
                )
                ._get_or_create_for_user(user)
            )
            configuration = {
                field: user[field]
                for field in self._get_fields_voip_user_configuration()
            }
            configuration["how_to_call_on_mobile"] = (
                user.how_to_call_on_mobile or settings.how_to_call_on_mobile
            )
            settings.update(configuration)
