import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.integration.tools import CommError

_logger = logging.getLogger(__name__)


class WizardIntegrationTwilioConfigUpdate(models.TransientModel):
    _name = "wizard.integration.twilio.config.update"
    _description = "Update a company's Twilio account"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )
    sms_provider = fields.Selection(
        related="company_id.integration_twilio_config_id.sms_provider",
        readonly=False,
    )
    twilio_account_sid = fields.Char(
        related="company_id.integration_twilio_config_id.twilio_account_sid",
        readonly=False,
    )
    twilio_auth_token = fields.Char(
        related="company_id.integration_twilio_config_id.twilio_auth_token",
        readonly=False,
    )
    twilio_account_status = fields.Selection(
        related="company_id.integration_twilio_config_id.twilio_account_status",
    )
    twilio_account_type = fields.Selection(
        related="company_id.integration_twilio_config_id.twilio_account_type",
    )
    twilio_currency_id = fields.Many2one(
        related="company_id.integration_twilio_config_id.twilio_currency_id",
    )
    amount_twilio_balance = fields.Monetary(
        related="company_id.integration_twilio_config_id.amount_twilio_balance",
        currency_field="twilio_currency_id",
    )
    amount_twilio_balance_alert = fields.Monetary(
        related="company_id.integration_twilio_config_id.amount_twilio_balance_alert",
        currency_field="twilio_currency_id",
        readonly=False,
    )
    twilio_alert_user_id = fields.Many2one(
        related="company_id.integration_twilio_config_id.twilio_alert_user_id",
        readonly=False,
    )
    date_twilio_checked = fields.Datetime(
        related="company_id.integration_twilio_config_id.date_twilio_checked",
    )
    twilio_number_ids = fields.One2many(
        related="company_id.twilio_number_ids",
        readonly=False,
    )
    test_number = fields.Char()
    is_automated_sms_blocked = fields.Boolean(
        compute="_compute_is_automated_sms_blocked",
    )

    @api.depends(
        "sms_provider",
        "twilio_number_ids.is_sms_capable",
        "twilio_number_ids.is_conversation_only",
    )
    def _compute_is_automated_sms_blocked(self) -> None:
        for wizard in self:
            wizard.is_automated_sms_blocked = (
                wizard.sms_provider == "twilio"
                and not any(
                    number.is_sms_capable and not number.is_conversation_only
                    for number in wizard.twilio_number_ids
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        accounts = [self._pop_account_vals(vals) for vals in vals_list]
        wizards = super().create(vals_list)
        for wizard, account in zip(wizards, accounts, strict=True):
            if account:
                wizard.company_id.integration_twilio_config_id.write(account)
        return wizards

    def write(self, vals):
        vals = dict(vals)
        account = self._pop_account_vals(vals)
        result = super().write(vals)
        if account:
            self.company_id.integration_twilio_config_id.write(account)
        return result

    @api.model
    def _pop_account_vals(self, vals) -> dict:
        return {
            name: vals.pop(name)
            for name in ("twilio_account_sid", "twilio_auth_token")
            if name in vals
        }

    def action_check_account(self) -> dict:
        self.company_id.integration_twilio_config_id.action_check_account()
        return self._action_reopen()

    def action_sync_numbers(self) -> dict:
        try:
            self.company_id.twilio_number_ids._sync_from_account(self.company_id)
        except CommError as error:
            _logger.warning("Twilio: syncing numbers failed: %s", error)
            return self._prepare_notification(
                "danger",
                self.env._("The numbers could not be synced: %s", error.message),
            )
        return self._action_reopen()

    def action_route_sms(self) -> dict:
        try:
            routed = self.company_id.twilio_number_ids._route_sms_to_odoo()
        except CommError as error:
            _logger.warning("Twilio: routing SMS failed: %s", error)
            return self._prepare_notification(
                "danger",
                self.env._("The numbers could not be updated: %s", error.message),
            )
        if not routed:
            return self._prepare_notification(
                "warning",
                self.env._("No synced SMS number to route: sync the numbers first."),
            )
        return self._action_reopen()

    def action_send_test(self) -> dict:
        if not self.test_number:
            raise UserError(
                self.env._(
                    "Please set the number to which you want to send a test SMS."
                )
            )
        composer = self.env["wizard.sms.sms.send"].create(
            {
                "body": self.env._("This is a test SMS from Odoo"),
                "composition_mode": "numbers",
                "numbers": self.test_number,
            }
        )
        sms_sudo = composer._action_send_sms()[0]
        if not sms_sudo.failure_type:
            sender = self.company_id._get_twilio_sender(self.test_number)
            return self._prepare_notification(
                "success",
                self.env._("The SMS has been sent from %s", sender.display_name),
            )
        if sms_sudo.failure_type == "unknown":
            return self._prepare_notification(
                "danger", self.env._("Error: %s", sms_sudo.failure_type)
            )
        sms_api = self.company_id._get_sms_api_class()(self.env)
        failure_label = dict(
            self.env["sms.sms"]
            ._fields["failure_type"]
            .get_description(self.env)["selection"]
        ).get(sms_sudo.failure_type, sms_sudo.failure_type)
        return self._prepare_notification(
            "danger",
            self.env._(
                "%(failure_type)s: %(failure_reason)s",
                failure_type=failure_label,
                failure_reason=sms_api._get_sms_api_error_messages().get(
                    sms_sudo.failure_type, failure_label
                ),
            ),
        )

    def action_save(self) -> dict:
        return {"type": "ir.actions.act_window_close"}

    def _action_reopen(self) -> dict:
        return {
            "name": self.env._("Manage Twilio Account"),
            "res_model": self._name,
            "res_id": self.id,
            "context": self.env.context,
            "type": "ir.actions.act_window",
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "new",
        }

    def _prepare_notification(self, notification_type, message) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Twilio"),
                "message": message,
                "type": notification_type,
                "sticky": False,
            },
        }
