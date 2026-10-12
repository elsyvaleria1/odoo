from datetime import date, timedelta

from odoo.tests import new_test_user, tagged

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.telegram.tests.common import NOT_A_MENU, TelegramBotTestCase

NEW = "New approval request"
RESUBMITTED = "resubmitted"


@tagged("post_install", "-at_install")
class TestAskedApproversArePushedOnce(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bot.notify_approvals = True
        cls.company = cls.env.ref("base.main_company")
        cls.owner = cls.env.ref("base.user_admin")
        cls.test_user.group_ids = [(4, cls.env.ref("base.group_user").id)]
        cls.colleague = new_test_user(
            cls.env, login="tg_ask_colleague", groups="base.group_user"
        )
        account = cls._bound_account(
            "770001", cls.colleague.partner_id, user=cls.colleague
        )
        cls.colleague_chat = cls.env["telegram.chat"].create(
            {
                "chat_id": "770001",
                "chat_type": "private",
                "bot_id": cls.test_bot.id,
                "account_id": account.id,
            }
        )
        cls.third = new_test_user(
            cls.env, login="tg_ask_third", groups="base.group_user"
        )

    @classmethod
    def _category(cls, code, members, minimum, **step_vals):
        category = cls.env["approval.category"].create(
            {
                "name": f"Telegram Ask {code}",
                "company_id": cls.company.id,
                "sequence_code": code,
                "step_ids": pool_step(members, minimum=minimum, **step_vals),
            }
        )
        category.step_ids.member_ids.filtered(
            lambda member: member.user_id in (cls.test_user | cls.colleague)
        ).notify_telegram = True
        return category

    def _submit(self, category):
        request = self.env["approval.request"].create(
            {"category_id": category.id, "request_owner_id": self.owner.id}
        )
        request.action_confirm()
        return request

    def _row(self, request, user):
        return request.approver_ids.filtered(lambda row: row.user_id == user)

    def _texts(self, chat, after=0):
        messages = self.env["telegram.message"].search(
            [
                ("chat_id", "=", chat.id),
                ("message_type", "=", "outbound"),
                ("id", ">", after),
                NOT_A_MENU,
            ],
            order="id",
        )
        return [message.payload["text"] for message in messages]

    def _last_id(self):
        return self.env["telegram.message"].search([], order="id desc", limit=1).id

    def _approve(self, request, user):
        self.env["telegram.approval.notifier"]._approve(
            self._row(request, user).with_user(user)
        )

    def test_a_co_approver_s_approval_does_not_push_the_others_again(self):
        category = self._category(
            "TGASKPAR",
            [
                (self.colleague.id, False, 10),
                (self.test_user.id, False, 10),
                (self.third.id, False, 10),
            ],
            minimum=3,
        )
        request = self._submit(category)
        mark = self._last_id()

        self._approve(request, self.colleague)

        self.assertEqual(request.state, "pending")
        self.assertEqual(self._texts(self.test_chat, after=mark), [])

    def test_only_the_approver_whose_turn_it_is_is_pushed(self):
        category = self._category(
            "TGASKSEQ",
            [(self.colleague.id, False, 1), (self.test_user.id, False, 2)],
            minimum=2,
            in_order=True,
        )
        request = self._submit(category)

        self.assertEqual(len(self._texts(self.colleague_chat)), 1)
        self.assertEqual(self._texts(self.test_chat), [])

        self._approve(request, self.colleague)

        texts = self._texts(self.test_chat)
        self.assertEqual(len(texts), 1)
        self.assertIn(NEW, texts[0])

    def test_a_delegate_handed_the_activity_is_pushed_once(self):
        category = self._category(
            "TGASKDEL",
            [(self.test_user.id, False, 10), (self.third.id, False, 10)],
            minimum=2,
        )
        request = self._submit(category)
        today = date.today()

        self._row(request, self.test_user).sudo().write(
            {
                "delegate_id": self.colleague.id,
                "delegate_start_date": today - timedelta(days=1),
                "delegate_end_date": today + timedelta(days=1),
            }
        )

        texts = self._texts(self.colleague_chat)
        self.assertEqual(len(texts), 1)
        self.assertIn(NEW, texts[0])

    def test_a_resubmission_is_one_message_per_approver(self):
        category = self._category(
            "TGASKFIX",
            [(self.colleague.id, False, 10), (self.test_user.id, False, 10)],
            minimum=2,
        )
        request = self._submit(category)
        self._approve(request, self.colleague)
        request.with_user(self.test_user).with_context(
            skip_wizard=True, requested_change_field="reason"
        ).action_request_change(
            approver=self._row(request, self.test_user).with_user(self.test_user)
        )
        mark = self._last_id()

        request.with_user(self.owner).action_resubmit()

        for chat in (self.test_chat, self.colleague_chat):
            texts = self._texts(chat, after=mark)
            self.assertEqual(len(texts), 1, chat.chat_id)
            self.assertIn(RESUBMITTED, texts[0])
            self.assertNotIn(NEW, texts[0])

    def test_a_new_round_after_a_reset_is_pushed_again(self):
        category = self._category(
            "TGASKRST", [(self.test_user.id, False, 10)], minimum=1
        )
        request = self._submit(category)
        request.action_cancel()
        request.action_reset_to_draft()
        mark = self._last_id()

        request.action_confirm()

        texts = self._texts(self.test_chat, after=mark)
        self.assertEqual(len(texts), 1)
        self.assertIn(NEW, texts[0])

    def test_the_inbox_copy_skips_exactly_the_pushed_approvers(self):
        category = self._category(
            "TGASKCTX",
            [(self.test_user.id, False, 10), (self.third.id, False, 10)],
            minimum=2,
        )
        rows = self._submit(category).approver_ids

        skipped = rows._get_ask_context().get("mail_telegram_skip_partner_ids")

        self.assertEqual(skipped, [self.test_user.partner_id.id])
        self.test_bot.notify_approvals = False
        self.assertEqual(rows._get_ask_context(), {})
