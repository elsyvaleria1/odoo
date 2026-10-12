from unittest.mock import patch

from odoo import Command
from odoo.tests import new_test_user, tagged

from .common import PartnerLedgerTelegramTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot

OWN = "account_telegram.privilege_print_own_statement"
RENDER = "odoo.addons.web.models.ir_actions_report.IrActionsReport._render_html_to_pdf"


@tagged("post_install", "-at_install")
class TestStatementAuthority(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        cls.customer = cls._create_partner({"name": "Zyxpropio SA"})
        cls._post_statement_line(cls.customer)
        cls._bound_account("555001", cls.customer)
        cls.stranger = cls._create_partner({"name": "Zyxajeno SA"})
        cls._post_statement_line(cls.stranger)
        cls.employee = new_test_user(
            cls.env, login="tg_statement_employee", groups="base.group_user"
        )
        cls._bound_account("555002", cls.employee.partner_id, user=cls.employee)
        cls._post_statement_line(cls.employee.partner_id)
        cls.accountant = new_test_user(
            cls.env,
            login="tg_statement_accountant",
            groups="base.group_user,account.group_account_readonly",
        )
        cls._bound_account("555003", cls.accountant.partner_id, user=cls.accountant)
        cls.privileges = cls.env["res.groups"]._privilege_ids((OWN,))

    def _webhook(self, update):
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        self.printed_options = []
        printed = []
        export = type(self.env["report.formula"]).export_to_pdf

        def spy(report, options):
            self.printed_options.append(
                (options["partner_ids"], [c["id"] for c in options["companies"]])
            )
            printed.append(
                {
                    "uid": report.env.uid,
                    "su": report.env.su,
                    "privileges": report.env.privileges & self.privileges,
                }
            )
            return export(report, options)

        with (
            patch.object(type(self.env["report.formula"]), "export_to_pdf", spy),
            patch(RENDER, lambda *args, **kwargs: b"%PDF-1.4 statement"),
            patch.object(TelegramBot, "send_document") as sent,
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(), update
            )
        texts = [
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        ]
        return printed, sent, texts

    def _command(self, chat_id, text, update_id):
        return self._webhook(
            {
                "update_id": update_id,
                "message": self.mock_telegram_message(chat_id=chat_id, text=text),
            }
        )

    def _button(self, chat_id, data, update_id):
        return self._webhook(
            {
                "update_id": update_id,
                "callback_query": self.mock_telegram_callback_query(
                    chat_id=chat_id, callback_data=data
                ),
            }
        )

    def _logs(self, partner):
        return self.env["telegram.financial.report.log"].search(
            [("target_partner_id", "=", partner.id)]
        )

    def test_a_contact_prints_their_own_statement_on_the_own_privilege(self):
        printed, sent, _texts = self._button("555001", "fin_period_1m", 9301)

        own = self.env["res.groups"]._privilege_ids((OWN,))
        self.assertEqual(
            printed, [{"uid": self.public.id, "su": False, "privileges": own}]
        )
        sent.assert_called_once()
        log = self._logs(self.customer)
        self.assertTrue(log.success)
        self.assertEqual(log.create_uid, self.public)

    def test_the_own_privilege_reads_no_other_contact_s_entries(self):
        lines = self.env["account.move.line"].with_user(self.public)
        own = lines.with_privilege(OWN).search(
            [("account_id.account_type", "=", "asset_receivable")]
        )
        self.assertIn(self.customer, own.partner_id)
        self.assertNotIn(self.stranger, own.partner_id)
        self.assertFalse(lines.has_access("read"))

    def test_only_who_reads_the_partner_ledger_prints_any_customer(self):
        partners = self.env["res.partner"]
        self.assertTrue(
            partners.with_user(self.accountant).has_access("print_statement")
        )
        self.assertFalse(
            partners.with_user(self.employee).has_access("print_statement")
        )
        self.assertFalse(partners.with_user(self.public).has_access("print_statement"))

    def test_a_contact_cannot_ask_for_another_customer(self):
        printed, sent, texts = self._command("555001", "/edocliente", 9305)

        self.assertFalse(printed)
        sent.assert_not_called()
        self.assertTrue(any("linked Odoo user" in text for text in texts))

    def test_an_accounting_reader_prints_a_customer_s_statement_as_themself(self):
        self._command("555003", "/edocliente", 9311)
        chat = self.env["telegram.chat"].search([("chat_id", "=", "555003")])
        self.assertEqual(chat.flow_step, "ecmanager_search")
        self._button("555003", f"ecm_partner_{self.stranger.id}", 9312)
        printed, sent, _texts = self._button("555003", "ecm_period_year", 9313)

        self.assertEqual(
            printed,
            [{"uid": self.accountant.id, "su": False, "privileges": frozenset()}],
        )
        sent.assert_called_once()
        self.assertEqual(self._logs(self.stranger).create_uid, self.accountant)

    def test_a_plain_employee_cannot_ask_for_another_customer(self):
        printed, sent, texts = self._command("555002", "/edocliente", 9321)

        self.assertFalse(printed)
        sent.assert_not_called()
        self.assertTrue(
            any("reads customer statements in Odoo" in text for text in texts)
        )

    def test_a_plain_employee_prints_their_own_on_the_own_privilege(self):
        printed, sent, _texts = self._button("555002", "fin_period_1m", 9322)

        self.assertEqual(
            printed,
            [{"uid": self.employee.id, "su": False, "privileges": self.privileges}],
        )
        sent.assert_called_once()

    def _speak_for_another_company(self):
        other = self.env["res.company"].create({"name": "TG Statement Other Co"})
        self.test_bot.company_id = other
        return other

    def test_a_contact_prints_their_own_statement_from_another_company_s_bot(self):
        other = self._speak_for_another_company()
        self._post_statement_line(self.customer, company=other)
        self._post_statement_line(self.stranger, company=other)

        printed, sent, texts = self._button("555001", "fin_period_1m", 9331)

        self.assertEqual([entry["uid"] for entry in printed], [self.public.id], texts)
        self.assertEqual(self.printed_options, [([self.customer.id], [other.id])])
        sent.assert_called_once()
        self.assertTrue(self._logs(self.customer).success)

    def test_a_member_prints_their_own_in_the_bot_s_company(self):
        other = self._speak_for_another_company()
        member = new_test_user(
            self.env,
            login="tg_statement_member",
            groups="base.group_user",
            company_ids=[Command.set((self.env.company | other).ids)],
        )
        self._bound_account("555010", member.partner_id, user=member)
        self._post_statement_line(member.partner_id, company=other)

        printed, sent, _texts = self._button("555010", "fin_period_1m", 9332)

        self.assertEqual(
            printed,
            [{"uid": member.id, "su": False, "privileges": self.privileges}],
        )
        self.assertEqual(self.printed_options, [([member.partner_id.id], [other.id])])
        sent.assert_called_once()

    def test_an_employee_of_another_company_than_the_bot_s_is_refused(self):
        other = self._speak_for_another_company()
        self._post_statement_line(self.employee.partner_id, company=other)

        printed, sent, texts = self._button("555002", "fin_period_1m", 9333)

        self.assertFalse(printed)
        sent.assert_not_called()
        self.assertTrue(
            any("not a member of the company this bot speaks for" in t for t in texts),
            texts,
        )
