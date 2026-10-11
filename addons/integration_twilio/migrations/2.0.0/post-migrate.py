import logging

from odoo import SUPERUSER_ID, api
from odoo.db import schema
from odoo.exceptions import ValidationError
from odoo.tools import SQL

from odoo.addons.integration_twilio.hooks import _update_twilio_service

_logger = logging.getLogger(__name__)

LEGACY_SID_COLUMN = "sms_twilio_account_sid"
LEGACY_TOKEN_KEY = "sms_twilio_auth_token"


def _move_account_into_vault(env, config_id, account_sid) -> bool:
    config = env["integration.twilio.config"].browse(config_id)
    company = config.company_id
    auth_token = company._get_held_secret(LEGACY_TOKEN_KEY)
    if not auth_token:
        _logger.warning(
            "%s had a Twilio Account SID (%s) but no Auth Token: its account is "
            "left unconfigured",
            company.display_name,
            account_sid,
        )
        return True
    try:
        config._set_held_secrets({"username": account_sid, "password": auth_token})
    except ValidationError as error:
        _logger.warning(
            "%s's Twilio account was not moved into the vault, and its legacy "
            "column is kept: %s",
            company.display_name,
            error,
        )
        return False
    company._set_held_secrets({LEGACY_TOKEN_KEY: False})
    return True


def _move_sms_accounts(cr, env) -> None:
    if not schema.column_exists(cr, "integration_twilio_config", LEGACY_SID_COLUMN):
        return
    column = SQL.identifier(LEGACY_SID_COLUMN)
    cr.execute(
        SQL(
            "SELECT id, %s FROM integration_twilio_config WHERE %s IS NOT NULL AND %s != ''",
            column,
            column,
            column,
        )
    )
    moved = [
        _move_account_into_vault(env, config_id, account_sid)
        for config_id, account_sid in cr.fetchall()
    ]
    for company in env["res.company"].with_context(active_test=False).search([]):
        if company._get_held_secret(LEGACY_TOKEN_KEY) and not (
            company.integration_twilio_config_id.credential_id
        ):
            company._set_held_secrets({LEGACY_TOKEN_KEY: False})
    if all(moved):
        schema.drop_columns(cr, "integration_twilio_config", [LEGACY_SID_COLUMN])


def _backfill_tracker_companies(cr) -> None:
    cr.execute(
        """
        UPDATE sms_tracker AS tracker
           SET twilio_company_id = message.record_company_id
          FROM mail_notification AS notification
          JOIN mail_message AS message ON message.id = notification.mail_message_id
         WHERE notification.id = tracker.mail_notification_id
           AND tracker.twilio_message_sid IS NOT NULL
           AND tracker.twilio_company_id IS NULL
        """
    )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["integration.twilio.config"]._for_each(
        env["res.company"].with_context(active_test=False).search([])
    )
    _update_twilio_service(env)
    _move_sms_accounts(cr, env)
    _backfill_tracker_companies(cr)
