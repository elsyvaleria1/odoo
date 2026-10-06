from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .test_approval_request import ApprovalRequestTestBase
from odoo.addons.approval.tests.common import pool_step
from odoo.addons.telegram.models.telegram_bot import TelegramBot


@tagged("post_install", "-at_install")
class TestDecisionAuthority(ApprovalRequestTestBase):
    """A decision taken in Telegram is its approver's own: the approval
    module's doors ask it of them, never of the superuser."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co_approver = new_test_user(
            cls.env, login="tg_co_approver", groups="base.group_user"
        )
        cls.outsider = new_test_user(
            cls.env, login="tg_outsider", groups="base.group_user"
        )
        cls.outsider_chat_id = "777301"
        cls._bound_account(
            cls.outsider_chat_id, cls.outsider.partner_id, user=cls.outsider
        )
        joint = cls.env["approval.category"].create(
            {
                "name": "Telegram Joint Category",
                "company_id": cls.company.id,
                "sequence_code": "TGJOINT",
                "step_ids": pool_step(
                    [(cls.test_user.id, False, 10), (cls.co_approver.id, False, 10)],
                    minimum=2,
                ),
            }
        )
        cls.joint_request = cls.env["approval.request"].create(
            {
                "category_id": joint.id,
                "request_owner_id": cls.env.ref("base.user_admin").id,
            }
        )
        cls.joint_request.action_confirm()
        cls.co_approver_row = cls.joint_request.approver_ids.filtered(
            lambda approver: approver.user_id == cls.co_approver
        )

    def _press(self, data, chat_id=None):
        chat_id = chat_id or self.test_chat.chat_id
        query = self.mock_telegram_callback_query(
            callback_data=data,
            chat_id=chat_id,
            message_id=7,
            from_user=self._sender_of(chat_id),
        )
        return self._through_the_doors(
            lambda: self.env["telegram.router"]._dispatch_callback_query(
                self.test_bot, query
            )
        )

    def _type(self, text):
        message = self.mock_telegram_message(chat_id=self.test_chat.chat_id, text=text)
        return self._through_the_doors(
            lambda: self.env["telegram.router"]._dispatch_message(
                self.test_bot, message
            )
        )

    def _through_the_doors(self, call):
        doors = []
        request_class = type(self.env["approval.request"])
        verb_door = request_class._verb_door

        def door(records, verb, admitted):
            doors.append((verb, records.env.uid, records.env.su))
            return verb_door(records, verb, admitted)

        with (
            patch.object(request_class, "_verb_door", door),
            patch.object(TelegramBot, "send_message") as mock_send,
            self.mock_api_gateway_post(),
        ):
            call()
        return doors, mock_send

    def test_an_approver_approves_as_themself(self):
        doors, mock_send = self._press(f"ar:a:{self.approver.id}")

        self.assertIn(("approve", self.test_user.id, False), doors)
        self.assertEqual(self.approval_request.state, "approved")
        self.assertEqual(self.approver.decided_by_user_id, self.test_user)
        self.assertIn("You approved", mock_send.call_args.args[1])

    def test_an_approver_refuses_as_themself(self):
        self._press(f"ar:rr:{self.approver.id}:0")
        doors, _mock_send = self._press("ar:rn:skip")

        self.assertIn(("refuse", self.test_user.id, False), doors)
        self.assertEqual(self.approval_request.state, "refused")

    def test_an_approver_asks_for_a_change_as_themself(self):
        self._press(f"ar:cf:{self.approver.id}:reason")
        doors, _mock_send = self._type("add the invoice number")

        self.assertIn(("request_change", self.test_user.id, False), doors)
        self.assertEqual(self.approval_request.pending_change_field, "reason")
        self.assertEqual(self.approval_request.tg_change_note, "add the invoice number")
        note = self.approval_request.message_ids.filtered(
            lambda message: "add the invoice number" in (message.body or "")
        )
        self.assertEqual(note.author_id, self.test_user.partner_id)
        self.assertEqual(note.create_uid, self.test_user)

    def test_a_co_approver_s_row_is_not_theirs_to_decide(self):
        doors, mock_send = self._press(f"ar:a:{self.co_approver_row.id}")

        self.assertFalse(doors)
        self.assertEqual(self.co_approver_row.state, "pending")
        self.assertIn("no longer available", mock_send.call_args.args[1])

    def test_the_approval_module_refuses_a_decision_on_another_s_row(self):
        with self.assertRaises(UserError):
            self.env["telegram.approval.notifier"]._approve(
                self.co_approver_row.with_user(self.test_user)
            )
        self.assertEqual(self.co_approver_row.state, "pending")
        self.assertEqual(self.joint_request.state, "pending")

    def test_a_linked_user_who_is_no_approver_changes_nothing(self):
        doors, mock_send = self._press(
            f"ar:a:{self.approver.id}", chat_id=self.outsider_chat_id
        )

        self.assertFalse(doors)
        self.assertEqual(self.approver.state, "pending")
        self.assertEqual(self.approval_request.state, "pending")
        self.assertIn("no longer available", mock_send.call_args.args[1])

    def _ask_change(self, request, approver, user):
        request.with_user(user).with_context(
            skip_wizard=True, requested_change_field="reason"
        ).action_request_change(approver=approver.with_user(user))

    def test_the_owner_s_correction_is_their_own_write(self):
        admin = self.env.ref("base.user_admin")
        category = self.env["approval.category"].create(
            {
                "name": "Telegram Owner Category",
                "company_id": self.company.id,
                "sequence_code": "TGOWNER",
                "step_ids": pool_step([(admin.id, False, 10)], minimum=1),
            }
        )
        own_request = self.env["approval.request"].create(
            {
                "category_id": category.id,
                "request_owner_id": self.test_user.id,
                "reason": "<p>first</p>",
            }
        )
        own_request.action_confirm()
        self._ask_change(own_request, own_request.approver_ids, admin)

        self._press(f"ar:fix:{own_request.id}")
        doors, mock_send = self._type("second")

        self.assertIn(("resubmit", self.test_user.id, False), doors)
        self.assertFalse(own_request.pending_change_field)
        self.assertEqual(own_request.reason, "<p>second</p>")
        self.assertEqual(own_request.write_uid, self.test_user)
        self.assertIn("back in approval", mock_send.call_args.args[1])

    def test_someone_else_s_request_is_not_theirs_to_correct(self):
        self._ask_change(self.approval_request, self.approver, self.test_user)

        doors, mock_send = self._press(f"ar:fix:{self.approval_request.id}")

        self.assertFalse(doors)
        self.assertEqual(self.approval_request.pending_change_field, "reason")
        self.assertIn("no longer needs corrections", mock_send.call_args.args[1])
