import inspect
import logging
import os
from contextlib import contextmanager
from unittest.mock import Mock, patch

from werkzeug.wrappers import Response as WerkzeugResponse

from odoo import Command
from odoo.exceptions import AccessError
from odoo.libs import sealing
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.service.model import get_public_method
from odoo.tests.common import HttpCase, TransactionCase

from odoo.addons.telegram.tools.dispatch import TelegramCommand

_logger = logging.getLogger(__name__)

_ORM_ENTRY_POINTS = frozenset({"create", "write", "unlink"})


def telegram_family_modules(env):
    return tuple(
        f"{name}."
        for name in env["ir.module.module"]
        .search([("state", "=", "installed")])
        .mapped("name")
        if name == "telegram" or name.endswith("_telegram")
    )


def rpc_exposed_methods(records, module_prefix, allowed=frozenset()):
    prefixes = (module_prefix,) if isinstance(module_prefix, str) else module_prefix
    names = {
        name
        for klass in type(records).__mro__
        if klass.__module__.startswith(tuple(f"odoo.addons.{p}" for p in prefixes))
        for name, member in vars(klass).items()
        if inspect.isfunction(member)
        and name not in _ORM_ENTRY_POINTS
        and name not in allowed
    }
    exposed = set()
    for name in names:
        try:
            get_public_method(records, name)
        except AccessError:
            continue
        exposed.add(name)
    return exposed


# a private chat's command menu goes out through the outbox too: a test about
# what a person was sent leaves it out
NOT_A_MENU = ("api_method", "!=", "setMyCommands")


class TelegramBotTestCase(TransactionCase):
    TEST_BOT_TOKEN = "123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    @contextmanager
    def extra_command(self, command, func=None, tier="unlinked", starts_flow=False):
        """Make the general handler answer `command` with `func` for the block
        -- or, `func` omitted, redeclare an existing command's flag."""
        handler = type(self.env["telegram.handler.base"])
        original = handler._telegram_commands
        method = f"_test_{command.strip('/')}_command"

        def commands(this):
            declared = original(this)
            if func is None:
                spec = declared[command]
                return {
                    **declared,
                    command: TelegramCommand(
                        spec.method, spec.tier, starts_flow, spec.builtin
                    ),
                }
            return {**declared, command: TelegramCommand(method, tier, starts_flow)}

        with patch.object(handler, "_telegram_commands", commands):
            if func is None:
                yield
            else:
                with patch.object(handler, method, func, create=True):
                    yield

    @classmethod
    def _create_partner(cls, vals):
        cls._ensure_partner_column_defaults()
        return cls.env["res.partner"].create({"lang": "en_US", **vals})

    @classmethod
    def _ensure_partner_column_defaults(cls):
        try:
            cls.env.cr.execute("""
                DO $$
                BEGIN
                    -- Set defaults for account module field
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='res_partner' AND column_name='autopost_bills') THEN
                        ALTER TABLE res_partner ALTER COLUMN autopost_bills SET DEFAULT 'ask';
                    END IF;

                    -- Set defaults for purchase_stock module fields
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='res_partner' AND column_name='group_on') THEN
                        ALTER TABLE res_partner ALTER COLUMN group_on SET DEFAULT 'default';
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='res_partner' AND column_name='group_rfq') THEN
                        ALTER TABLE res_partner ALTER COLUMN group_rfq SET DEFAULT 'default';
                    END IF;
                END $$;
                """)
        except Exception:
            _logger.debug("Could not set partner column defaults for test setup")

    @classmethod
    def _make_bot_credential(cls, name, token):
        return cls.env["credential.credential"].create(
            {
                "name": name,
                "category_id": cls.env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": cls.env.ref("telegram.service_telegram").id,
                "bearer_token": token,
            }
        )

    @classmethod
    def _bot_of_another_company(cls, name="Other Company Bot"):
        """A bot that speaks for a company of its own, not the main one."""
        company = cls.env["res.company"].create({"name": f"{name} Company"})
        return cls.env["telegram.bot"].create(
            {
                "name": name,
                "company_id": company.id,
                "credential_id": cls._make_bot_credential(
                    f"{name} Credential", "423456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew44"
                ).id,
            }
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)

        cls.test_credential = cls._make_bot_credential(
            "Test Telegram Bot Credential", cls.TEST_BOT_TOKEN
        )

        cls.test_bot = cls.env["telegram.bot"].create(
            {
                "name": "Test Bot",
                "credential_id": cls.test_credential.id,
            }
        )

        cls.test_partner = cls._create_partner(
            {
                "name": "Test Partner",
                "phone_ids": [
                    Command.create({"number": "+52 123 456 7890", "type": "mobile"})
                ],
            }
        )

        cls.test_user = cls.env["res.users"].create(
            {
                "name": "Test User",
                "login": "testuser@example.com",
                "partner_id": cls.test_partner.id,
            },
        )

        # A private chat's id is its person's Telegram user id; the account
        # is bound to the test user as a session link would bind it.
        cls.test_account = cls.env["telegram.account"].create(
            {"tg_user_id": "12345", "username": "testuser", "first_name": "Test"}
        )
        cls.test_binding = cls.env["telegram.binding"].create(
            {
                "account_id": cls.test_account.id,
                "partner_id": cls.test_partner.id,
                "user_id": cls.test_user.id,
                "method": "session",
            }
        )
        cls.test_chat = cls.env["telegram.chat"].create(
            {
                "chat_id": "12345",
                "chat_type": "private",
                "bot_id": cls.test_bot.id,
                "account_id": cls.test_account.id,
            },
        )

        cls.unlinked_chat = cls.env["telegram.chat"].create(
            {
                "chat_id": "67890",
                "bot_id": cls.test_bot.id,
            },
        )

    @classmethod
    def _bound_account(cls, tg_user_id, partner, user=None):
        """The account of Telegram user `tg_user_id`, bound to `partner`."""
        account = cls.env["telegram.account"]._from_telegram(
            {"id": int(tg_user_id), "first_name": partner.name}
        )
        account._bind(partner, user=user, method="session" if user else "invitation")
        return account

    @staticmethod
    def _sender_of(chat_id, is_bot=False):
        """Who writes in a private chat: Telegram gives the chat its person's
        user id."""
        return {
            "id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else 123,
            "username": "testuser" if str(chat_id) == "12345" else f"user{chat_id}",
            "first_name": "Test",
            "is_bot": is_bot,
        }

    @staticmethod
    def mock_telegram_response(
        success=True, result=None, error_code=None, description=None
    ):
        response = Mock()
        response.ok = success
        response.status_code = 200 if success else error_code or 400

        response_data = {"ok": success}
        if success:
            response_data["result"] = result or {}
        else:
            response_data["error_code"] = error_code or 400
            response_data["description"] = description or "Bad Request"

        response.json.return_value = response_data
        response.content = json_dumps_bytes(response_data)

        if not success:
            response.raise_for_status.side_effect = Exception(
                description or "Bad Request",
            )

        return response

    @staticmethod
    def mock_telegram_message(
        chat_id="12345",
        text="/start",
        from_user=None,
        message_id=1,
        is_bot=False,
    ):
        if from_user is None:
            from_user = TelegramBotTestCase._sender_of(chat_id, is_bot)

        return {
            "message_id": message_id,
            "from": from_user,
            "chat": {"id": chat_id, "type": "private"},
            "date": 1234567890,
            "text": text,
        }

    @staticmethod
    def mock_telegram_callback_query(
        callback_data="action",
        chat_id="12345",
        from_user=None,
        message_id=1,
    ):
        if from_user is None:
            from_user = TelegramBotTestCase._sender_of(chat_id)

        return {
            "id": "callback_query_id",
            "from": from_user,
            "message": {
                "message_id": message_id,
                "chat": {"id": chat_id, "type": "private"},
                "text": "Original message",
            },
            "data": callback_data,
        }

    @staticmethod
    def mock_telegram_contact(phone_number, first_name="Test", user_id=123):
        return {
            "phone_number": phone_number,
            "first_name": first_name,
            "user_id": user_id,
        }

    def mock_api_gateway_post(self, response=None):
        if response is None:
            response = self.mock_telegram_response(
                success=True, result={"message_id": 1}
            )

        api_response = {"body": response.json()}
        return patch(
            "odoo.addons.integration.tools.api_client.OutboundAPIClient.post",
            return_value=api_response,
        )

    def mock_api_gateway_get(self, response=None):
        if response is None:
            response = self.mock_telegram_response(success=True, result={})

        api_response = {"body": response.json()}
        return patch(
            "odoo.addons.integration.tools.api_client.OutboundAPIClient.get",
            return_value=api_response,
        )

    def mock_webhook_request(self, data, headers=None):
        if headers is None:
            headers = {}

        mock_httprequest = Mock()
        mock_httprequest.get_data.return_value = json_dumps_bytes(data)
        mock_httprequest.headers = headers
        mock_httprequest.remote_addr = "149.154.167.220"

        mock_request = Mock()
        mock_request.httprequest = mock_httprequest
        mock_request.env = self.env

        def make_response_side_effect(data, status=200, headers=None):
            response = WerkzeugResponse(data, status=status)
            if headers:
                for key, value in headers:
                    response.headers[key] = value
            return response

        mock_request.prepare_response.side_effect = make_response_side_effect

        return patch(
            "odoo.addons.telegram.controllers.telegram_controller.request",
            mock_request,
        )

    def mock_rate_limiter(self, is_allowed=True):
        return patch(
            "odoo.addons.telegram.models.telegram_chat.EndpointRateLimiter",
            return_value=Mock(check_limit=Mock(return_value=is_allowed)),
        )


class TelegramBotHttpCase(TelegramBotTestCase, HttpCase):
    """The fixtures above, served over HTTP: what a route does before its
    handler runs -- the gate, the resolver, the refusal -- is only reachable
    through the route."""
