import contextlib
import hashlib
import logging
import re
import secrets
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.libs.json import loads as json_loads
from odoo.libs.secret import Secret
from odoo.tools import consteq, hash_sign, register_signed_scope, resolve_hash_signed

from ..tools.authority import keeping
from ..tools.web_app import resolve_init_data
from odoo.addons.integration.tools.admission import Resolution

_logger = logging.getLogger(__name__)

MINI_APP_INIT_DATA_HEADER = "X-Telegram-Init-Data"

SECRET_TOKEN_HEADER = "X-Telegram-Bot-Api-Secret-Token"
MINI_APP_SESSION_SCOPE = register_signed_scope(
    "telegram.miniapp_session",
    purpose="a Telegram Mini App session: the bot and the Telegram user whose "
    "verified init data opened it",
    lifetime="dated: MINI_APP_SESSION_TTL_HOURS",
)
MINI_APP_SESSION_TTL_HOURS = 1
_MINI_APP_REFUSAL_CODES = {401: "auth", 404: "not_found", 413: "too_large", 429: "busy"}
_TOKEN_HASH = re.compile(r"[0-9a-f]{64}")
WEBHOOK_SECRET_PURPOSE = "telegram_bot:webhook_secret"
_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class IntegrationReceiver(models.Model):
    _inherit = "integration.receiver"

    auth_type = fields.Selection(
        selection_add=[
            ("telegram_secret_token", "Telegram webhook secret"),
            ("telegram_init_data", "Telegram Mini App initData"),
        ],
        ondelete={
            "telegram_secret_token": "set default",
            "telegram_init_data": "set default",
        },
    )

    def _get_display_name_visible_ids(self) -> set[int]:
        bots = self.env["telegram.bot"]
        visible = super()._get_display_name_visible_ids()
        if not bots.has_access("read"):
            return visible
        bots = bots.search(
            [
                "|",
                ("webhook_receiver_id", "in", self.ids),
                ("mini_app_receiver_id", "in", self.ids),
            ]
        )
        return visible | set(
            (bots.webhook_receiver_id | bots.mini_app_receiver_id)._ids
        )

    def _get_served_telegram_bot(self):
        self.check_singleton()
        if self.res_model != "telegram.bot" or not self.res_id:
            raise ValidationError(
                self.env._("Receiver %s serves no Telegram bot.", self.display_name)
            )
        bot = self.env["telegram.bot"].browse(self.res_id).exists()
        if not bot:
            raise ValidationError(
                self.env._("The bot receiver %s served is gone.", self.display_name)
            )
        return bot

    def _inbound_event_id(self, admission, event_type):
        if self.auth_type == "telegram_secret_token":
            payload = admission.payload
            update_id = payload.get("update_id") if isinstance(payload, dict) else None
            return str(update_id) if update_id else None
        return super()._inbound_event_id(admission, event_type)

    def _inbound_payload_logged(self, event_type):
        if self.auth_type in ("telegram_secret_token", "telegram_init_data"):
            return False
        return super()._inbound_payload_logged(event_type)

    def _inbound_auth_mode(self, parameter_key=None):
        if parameter_key is None and self.auth_type == "telegram_secret_token":
            return self._get_served_telegram_bot()._webhook_auth_mode()
        return super()._inbound_auth_mode(parameter_key)

    def _authenticate_scheme_telegram_secret_token(
        self, headers: dict[str, Any], body: Any
    ) -> bool:
        bot = self._get_served_telegram_bot()
        secret = bot._webhook_secret()
        if not secret:
            if bot.legacy_secretless_webhook:
                return False
            raise ValidationError(
                self.env._(
                    "Bot %s has no webhook secret. Register Webhook on the bot to "
                    "give it one.",
                    bot.name,
                )
            )
        return consteq(headers.get(SECRET_TOKEN_HEADER), secret)


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    webhook_receiver_id = fields.Many2one(
        comodel_name="integration.receiver",
        copy=False,
        readonly=True,
        ondelete="set null",
        help="Admits the updates Telegram posts to this bot's webhook: its caller "
        "limits, its refusals and its traffic in the "
        "exchange log.",
    )
    mini_app_receiver_id = fields.Many2one(
        comodel_name="integration.receiver",
        copy=False,
        readonly=True,
        ondelete="set null",
        help="Admits calls from this bot's Mini Apps, which authenticate with the "
        "initData Telegram signs with the bot token.",
    )

    _RECEIVER_KINDS = {
        "webhook_receiver_id": (
            "telegram_secret_token",
            "webhook",
            1024 * 1024,
            1200,
        ),
        "mini_app_receiver_id": (
            "telegram_init_data",
            "Mini App",
            25 * 1024 * 1024,
            600,
        ),
    }

    @api.model_create_multi
    def create(self, vals_list):
        bots = super().create(vals_list)
        bots._create_missing_receivers()
        bots._update_webhook_secret_if_inactive()
        return bots

    def write(self, vals):
        result = super().write(vals)
        if "name" in vals or "company_id" in vals:
            for bot in keeping(self):
                for field_name, kind in self._RECEIVER_KINDS.items():
                    if bot[field_name]:
                        bot[field_name].write(
                            {
                                "name": f"{bot.name} {kind[1]}",
                                "company_id": bot.company_id.id,
                            }
                        )
                secret = bot.webhook_receiver_id.credential_id
                if secret and secret.company_id != bot.company_id:
                    secret.company_id = bot.company_id
        return result

    def unlink(self):
        bots = keeping(self)
        receivers = bots.webhook_receiver_id | bots.mini_app_receiver_id
        secret_credentials = bots.webhook_receiver_id.credential_id
        result = super().unlink()
        receivers.unlink()
        secret_credentials.unlink()
        return result

    def _create_missing_receivers(self) -> None:
        bots = keeping(self)
        receivers = bots.env["integration.receiver"]
        for bot in bots:
            for field_name, (scheme, label, size, rate) in self._RECEIVER_KINDS.items():
                if bot[field_name]:
                    continue
                bot[field_name] = receivers.create(
                    {
                        "name": f"{bot.name} {label}",
                        "code": f"telegram_{scheme}_{bot.id}",
                        "res_model": bot._name,
                        "res_id": bot.id,
                        "auth_type": scheme,
                        "company_id": bot.company_id.id,
                        "max_payload_size": size,
                        "rate_limit_enabled": True,
                        "rate_limit_requests": rate,
                        "rate_limit_window_seconds": 60,
                    }
                )

    @api.model
    def _receiver_for_webhook(self, token, **path_args):
        bot, by_hash = self._find_by_webhook_key(token)
        if not bot:
            fingerprint = hashlib.sha256(token.encode()).hexdigest()[:12]
            return Resolution(self.browse(), claimed=f"token sha256:{fingerprint}")
        if by_hash and bot._webhook_auth_mode() != "enforce":
            return Resolution(
                self.browse(), claimed=f"hash-addressed bot {bot.id} without a secret"
            )
        return Resolution(bot, gate=bot._get_or_create_webhook_receiver())

    @api.model
    def _find_by_webhook_key(self, key) -> tuple:
        bots = self
        if _TOKEN_HASH.fullmatch(key):
            bot = bots.search([("token_hash", "=", key)], limit=1)
            if bot:
                return bot, True
        return bots.find_by_token(key), False

    @api.model
    def _prepare_webhook_refusal_response(self, refused):
        return request.prepare_response("OK", status=200)

    def _get_or_create_webhook_receiver(self):
        self.check_singleton()
        if not self.webhook_receiver_id:
            self._create_missing_receivers()
        return keeping(self).webhook_receiver_id

    def _get_or_create_mini_app_receiver(self):
        self.check_singleton()
        if not self.mini_app_receiver_id:
            self._create_missing_receivers()
        return keeping(self).mini_app_receiver_id

    def _webhook_auth_mode(self) -> str:
        self.check_singleton()
        if not self._webhook_secret() and self.legacy_secretless_webhook:
            return "audit"
        return "enforce"

    def _webhook_secret(self) -> Secret | None:
        self.check_singleton()
        credential = self._get_or_create_webhook_receiver().credential_id
        if not credential.active:
            return None
        return credential._use_secret(WEBHOOK_SECRET_PURPOSE)

    def _update_webhook_secret_if_inactive(self) -> None:
        if not self.env["credential.credential"]._is_encryption_key_configured():
            return
        for bot in self:
            if not bot._get_or_create_webhook_receiver().credential_id.active:
                bot._update_webhook_secret(secrets.token_urlsafe(32))

    def _update_webhook_secret(self, value) -> None:
        self.check_singleton()
        receiver = self._get_or_create_webhook_receiver()
        credential = receiver.credential_id
        if not value:
            receiver.credential_id = False
            credential.unlink()
            return
        if not _SECRET_RE.match(value):
            raise ValidationError(
                self.env._(
                    "A webhook secret is 1 to 256 characters of A-Z, a-z, 0-9, _ and -."
                )
            )
        if credential:
            credential.write({"credential_value": value, "active": True})
            return
        receiver.credential_id = receiver.env["credential.credential"].create(
            {
                "name": f"Telegram webhook secret: {self.name} "
                f"({secrets.token_hex(4)})",
                "category_id": self.env.ref("credential.credential_category_custom").id,
                "company_id": self.company_id.id,
                "credential_value": value,
            }
        )

    @api.model
    def _mini_app_call(self, path_args):
        params = dict(request.get_http_params())
        if request.httprequest.mimetype in ("application/json", "application/json-rpc"):
            with contextlib.suppress(ValueError, AttributeError):
                params.update(request.get_json_data().get("params") or {})
        params.update(path_args)
        if not params.get("init_data"):
            params["init_data"] = request.httprequest.headers.get(
                MINI_APP_INIT_DATA_HEADER, ""
            )
        return params

    @api.model
    def _receiver_for_mini_app(self, **path_args):
        call = self._mini_app_call(path_args)
        try:
            bot_id = int(call.get("bot_id") or 0)
        except TypeError, ValueError:
            bot_id = 0
        bot = self.browse(bot_id).exists() if bot_id else self.browse()
        if not bot:
            return Resolution(self.browse(), claimed=f"bot {call.get('bot_id')!r}"[:64])
        session = call.get("s") or ""
        init_data = call.get("init_data") or ""
        gate = bot._get_or_create_mini_app_receiver()
        if session:
            telegram_user_id = bot._resolve_mini_app_session(session)
            return Resolution(
                bot,
                {"telegram_user_id": telegram_user_id, "session": session},
                gate=gate,
                verify=lambda headers, body: bool(telegram_user_id),
            )
        parsed = bot._resolve_init_data(init_data)
        telegram_user_id = bot._mini_app_user_id(parsed)
        return Resolution(
            bot,
            {"telegram_user_id": telegram_user_id, "init_data": init_data},
            gate=gate,
            verify=lambda headers, body: parsed is not None,
        )

    def _resolve_init_data(self, init_data):
        self.check_singleton()
        if not init_data:
            return None
        try:
            token = self._get_bot_token()
        except Exception:
            _logger.exception("Could not read bot token for Mini App validation")
            return None
        return resolve_init_data(token, init_data)

    @staticmethod
    def _mini_app_user_id(parsed):
        if not parsed:
            return None
        try:
            telegram_user = json_loads(parsed.get("user") or "{}")
        except ValueError:
            return None
        return str(telegram_user.get("id") or "") or None

    def _mint_mini_app_session(self, telegram_user_id):
        self.check_singleton()
        return hash_sign(
            self.env(su=True),
            MINI_APP_SESSION_SCOPE,
            [self.id, str(telegram_user_id)],
            expiration_hours=MINI_APP_SESSION_TTL_HOURS,
        )

    def _resolve_mini_app_session(self, session):
        self.check_singleton()
        if not session:
            return None
        payload = resolve_hash_signed(
            self.env(su=True), MINI_APP_SESSION_SCOPE, session
        )
        if not payload or len(payload) != 2:
            return None
        signed_bot_id, telegram_user_id = payload
        if signed_bot_id != self.id:
            return None
        return telegram_user_id

    def _mini_app_user(self, telegram_user_id, tier="internal"):
        self.check_singleton()
        if not telegram_user_id:
            return self.env["res.users"]
        account = self.env["telegram.account"].search(
            [("tg_user_id", "=", str(telegram_user_id))], limit=1
        )
        if not account:
            return self.env["res.users"]
        user = account._acting_user(tier)
        if not user or not self._admits_user(user):
            return self.env["res.users"]
        if user.share:
            return user
        in_company = {"allowed_company_ids": self._served_companies(user).ids}
        admission = getattr(request, "admission", None) if request else None
        if admission and admission.subject == self:
            request.update_env(
                user=user.id, context={**request.env.context, **in_company}
            )
        return user.with_env(
            self.env(user=user.id, su=False, context={**self.env.context, **in_company})
        )

    @api.model
    def _prepare_mini_app_refusal_response(self, refused):
        return request.prepare_json_response(
            {"ok": False, "error": _MINI_APP_REFUSAL_CODES.get(refused.status, "auth")}
        )

    @api.model
    def _prepare_mini_app_rpc_refusal_response(self, refused):
        try:
            request_id = request.get_json_data().get("id")
        except ValueError, AttributeError:
            request_id = None
        return request.prepare_json_response(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": refused.status,
                    "message": _MINI_APP_REFUSAL_CODES.get(refused.status, "auth"),
                    "data": {"name": "Refused", "message": refused.reason},
                },
            }
        )
