from unittest.mock import patch

from odoo import fields as odoo_fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.telegram.tests.common import TelegramBotTestCase
from odoo.addons.telegram.tools import format as tg


class TestDigestTelegramFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Digest = cls.env["digest.digest"]

    def test_telegram_fields_exist(self):
        for field in ("telegram_enabled", "telegram_bot_id", "telegram_send_mode"):
            self.assertIn(field, self.Digest._fields, f"Missing field: {field}")

    def test_telegram_enabled_default_false(self):
        digest = self.Digest.create({"name": "Test Digest"})
        self.assertFalse(digest.telegram_enabled)

    def test_telegram_send_mode_selection_values(self):
        field = self.Digest._fields["telegram_send_mode"]
        values = [s[0] for s in field.selection]
        self.assertIn("replace", values)
        self.assertIn("complement", values)

    def test_telegram_send_mode_default_replace(self):
        digest = self.Digest.create({"name": "Mode Digest", "telegram_enabled": True})
        self.assertEqual(digest.telegram_send_mode, "replace")

    def test_telegram_bot_id_comodel(self):
        field = self.Digest._fields["telegram_bot_id"]
        self.assertEqual(field.comodel_name, "telegram.bot")


class TestDigestTelegramHtmlEscape(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.digest = cls.env["digest.digest"].create(
            {"name": "Ana_<Bold>*&co", "telegram_enabled": True}
        )

    def test_digest_name_arrives_as_literal_html_text(self):
        result = self.digest._format_digest_for_telegram([], self.env.company)
        self.assertIn("<b>Ana_&lt;Bold&gt;*&amp;co</b>", result)
        self.assertNotIn("<Bold>", result)

    def test_column_values_are_escaped(self):
        kpi = {
            "kpi_name": "test",
            "kpi_fullname": "Sales",
            "kpi_col1": {"value": "$1 & <2>", "margin": 0, "col_subtitle": "A<B"},
        }
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertIn("A&lt;B: $1 &amp; &lt;2&gt;", result)

    def test_markdown_metacharacters_stay_literal(self):
        kpi = {"kpi_name": "test", "kpi_fullname": "Sales_Report*2025"}
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertEqual(result, "<b>Sales_Report*2025</b>")


class TestDigestTelegramKpiFormatting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.digest = cls.env["digest.digest"].create(
            {
                "name": "Format Test",
                "telegram_enabled": True,
            }
        )

    def _make_kpi(self, fullname="Messages", col1=None, col2=None, col3=None):
        kpi = {"kpi_name": "test", "kpi_fullname": fullname}
        for key, val in [("kpi_col1", col1), ("kpi_col2", col2), ("kpi_col3", col3)]:
            kpi[key] = val or {}
        return kpi

    def test_kpi_name_is_bold(self):
        kpi = self._make_kpi("Messages Sent")
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertTrue(result.startswith("<b>Messages Sent</b>"))

    def test_empty_columns_skipped(self):
        kpi = self._make_kpi()
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertEqual(result, "<b>Messages</b>")

    def test_positive_margin_shows_up_arrow(self):
        kpi = self._make_kpi(
            col1={"value": "100", "margin": 12.5, "col_subtitle": "Today"}
        )
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertIn("↑ +12.5%", result)

    def test_negative_margin_shows_down_arrow(self):
        kpi = self._make_kpi(
            col1={"value": "80", "margin": -7.3, "col_subtitle": "Today"}
        )
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertIn("↓ -7.3%", result)

    def test_zero_margin_shows_right_arrow(self):
        kpi = self._make_kpi(col1={"value": "50", "margin": 0, "col_subtitle": "Today"})
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertIn("→ 0.0%", result)

    def test_only_populated_columns_rendered(self):
        kpi = self._make_kpi(
            col1={"value": "10", "margin": 1.0, "col_subtitle": "Day"},
            col2={"value": "9", "margin": -1.0, "col_subtitle": "Week"},
        )
        result = self.digest._format_kpi_for_telegram(kpi)
        self.assertEqual(len(result.splitlines()), 3)

    def test_format_digest_contains_digest_name(self):
        result = self.digest._format_digest_for_telegram(
            [self._make_kpi()], self.env.company
        )
        self.assertIn("Format Test", result)

    def test_format_digest_contains_company_name(self):
        result = self.digest._format_digest_for_telegram(
            [self._make_kpi()], self.env.company
        )
        self.assertIn(f"<i>{tg.escape(self.env.company.name)}</i>", result)

    def test_format_digest_footer_present(self):
        result = self.digest._format_digest_for_telegram(
            [self._make_kpi()], self.env.company
        )
        self.assertIn("Generated by Odoo Digest", result)

    def test_format_digest_has_date(self):
        result = self.digest._format_digest_for_telegram(
            [self._make_kpi()], self.env.company
        )
        self.assertIn(str(odoo_fields.Date.today()), result)


class TestDigestTelegramChatLookup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Digest = cls.env["digest.digest"]

    def test_no_bot_configured_domain_excludes_bot_filter(self):
        digest = self.Digest.create({"name": "No Bot Digest", "telegram_enabled": True})
        user = self.env.user

        with patch.object(
            type(self.env["telegram.chat"]),
            "search",
            return_value=self.env["telegram.chat"],
        ) as mock_search:
            digest._get_user_telegram_chat(user)
            domain = mock_search.call_args[0][0]

        bot_filters = [
            d for d in domain if isinstance(d, (list, tuple)) and d[0] == "bot_id"
        ]
        self.assertFalse(
            bot_filters,
            "bot_id filter must not appear when telegram_bot_id is empty",
        )

    def test_chat_returns_empty_recordset_when_none_found(self):
        digest = self.Digest.create(
            {"name": "No Chat Digest", "telegram_enabled": True}
        )
        result = digest._get_user_telegram_chat(self.env.user)
        self.assertFalse(result)


class TestDigestTelegramCompany(TelegramBotTestCase):
    def test_the_digest_comes_through_a_bot_of_the_user_s_company(self):
        other_bot = self._bot_of_another_company("Other Digest Bot")
        self.env["telegram.chat"].create(
            {
                "chat_id": self.test_chat.chat_id,
                "chat_type": "private",
                "bot_id": other_bot.id,
                "account_id": self.test_account.id,
            }
        )
        digest = self.env["digest.digest"].create(
            {"name": "Company Digest", "telegram_enabled": True}
        )

        self.assertEqual(digest._get_user_telegram_chat(self.test_user), self.test_chat)
        digest.telegram_bot_id = other_bot
        self.assertFalse(digest._get_user_telegram_chat(self.test_user))


class TestDigestTelegramSendDisabled(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.digest = cls.env["digest.digest"].create(
            {
                "name": "Email Only Digest",
                "telegram_enabled": False,
            }
        )

    def test_disabled_calls_super(self):
        called = []

        with patch(
            "odoo.addons.digest.models.digest.DigestDigest._action_send_to_user",
            side_effect=lambda *a, **kw: called.append(True) or True,
        ):
            self.digest._action_send_to_user(self.env.user)

        self.assertTrue(
            called,
            "super()._action_send_to_user must be called when Telegram is disabled",
        )

    def test_disabled_no_telegram_bot_id(self):
        self.assertFalse(self.digest.telegram_bot_id)


class TestDigestTelegramSendActions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Digest = cls.env["digest.digest"]

    def test_action_test_telegram_disabled_raises(self):
        digest = self.Digest.create({"name": "Disabled", "telegram_enabled": False})
        with self.assertRaises(UserError):
            digest.action_test_telegram_send()

    def test_action_test_telegram_no_chat_raises(self):
        digest = self.Digest.create({"name": "No Chat", "telegram_enabled": True})
        with self.assertRaises(UserError):
            digest.action_test_telegram_send()

    def test_send_to_user_no_chat_replace_returns_false(self):
        digest = self.Digest.create(
            {
                "name": "No Chat Replace",
                "telegram_enabled": True,
                "telegram_send_mode": "replace",
            }
        )
        result = digest._action_send_to_user(self.env.user)
        self.assertFalse(result)

    def test_send_to_user_no_chat_complement_calls_super(self):
        digest = self.Digest.create(
            {
                "name": "No Chat Complement",
                "telegram_enabled": True,
                "telegram_send_mode": "complement",
            }
        )
        called = []

        with patch(
            "odoo.addons.digest.models.digest.DigestDigest._action_send_to_user",
            side_effect=lambda *a, **kw: called.append(True) or True,
        ):
            digest._action_send_to_user(self.env.user)

        self.assertTrue(
            called, "Email fallback must be invoked in complement mode with no chat"
        )

    def test_send_mode_round_trip(self):
        for mode in ("replace", "complement"):
            digest = self.Digest.create(
                {
                    "name": f"Mode {mode}",
                    "telegram_enabled": True,
                    "telegram_send_mode": mode,
                }
            )
            self.assertEqual(digest.telegram_send_mode, mode)
