from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools.safe_eval import safe_eval

from .common import PaymentApprovalTelegramTestCase
from odoo.addons.approval.tests.common import pool_step


class TestBankStatementSettlementWindow(PaymentApprovalTelegramTestCase):
    def test_card_payment_tc_adds_7_days(self):
        payment_date = date(2024, 1, 15)
        expected_date = date(2024, 1, 22)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "TC"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, expected_date)

    def test_card_payment_td_adds_7_days(self):
        payment_date = date(2024, 2, 10)
        expected_date = date(2024, 2, 17)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "TD"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, expected_date)

    def test_check_payment_adds_2_days(self):
        payment_date = date(2024, 5, 8)
        expected_date = date(2024, 5, 10)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "CHEQUE"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, expected_date)

    def test_transfer_payment_same_date(self):
        payment_date = date(2024, 3, 20)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "TRANSFERENCIA"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, payment_date)

    def test_cash_payment_same_date(self):
        payment_date = date(2024, 4, 5)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "EFECTIVO"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, payment_date)

    def test_no_telegram_data_same_date(self):
        payment_date = date(2024, 5, 10)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": False,
            }
        )

        self.assertEqual(request.bank_statement_date_end, payment_date)

    def test_empty_payment_method_same_date(self):
        payment_date = date(2024, 6, 15)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": ""},
            }
        )

        self.assertEqual(request.bank_statement_date_end, payment_date)

    def test_no_date_returns_false(self):
        category_no_date = self.env["approval.category"].create(
            {
                "name": "No Date Category",
                "sequence_code": "TGND",
                "has_bsl": "required",
                "has_date": "no",
                "company_id": self.company.id,
            }
        )

        request = self.env["approval.request"].create(
            {
                "name": "No Date Request",
                "category_id": category_no_date.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
                "telegram_data": {"payment_method": "TC"},
            }
        )

        self.assertFalse(request.bank_statement_date_end)

    def test_has_bsl_no_returns_false(self):
        category_no_bsl = self.env["approval.category"].create(
            {
                "name": "No BSL Category",
                "sequence_code": "TGNB",
                "has_bsl": "no",
                "has_date": "required",
                "company_id": self.company.id,
            }
        )

        request = self.env["approval.request"].create(
            {
                "name": "No BSL Request",
                "category_id": category_no_bsl.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
                "date": date(2024, 7, 1),
                "telegram_data": {"payment_method": "TC"},
            }
        )

        self.assertFalse(request.bank_statement_date_end)

    def test_card_payment_month_boundary(self):
        payment_date = date(2024, 1, 28)
        expected_date = date(2024, 2, 4)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "TC"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, expected_date)

    def test_card_payment_year_boundary(self):
        payment_date = date(2024, 12, 28)
        expected_date = date(2025, 1, 4)

        request = self.create_approval_request(
            {
                "date": payment_date,
                "telegram_data": {"payment_method": "TD"},
            }
        )

        self.assertEqual(request.bank_statement_date_end, expected_date)

    def _picker_domain(self, request):
        return safe_eval(
            request._fields["bank_statement_line_id"].domain,
            {
                "bank_statement_date": request.bank_statement_date,
                "bank_statement_date_end": request.bank_statement_date_end,
                "amount": request.amount,
                "include_reconciled_bsl": request.include_reconciled_bsl,
                "bank_statement_line_id": request.bank_statement_line_id.id,
            },
        )

    def test_a_card_payment_can_pick_a_line_that_settled_a_week_later(self):
        payment_date = date(2024, 3, 4)
        request = self.create_approval_request(
            {
                "date": payment_date,
                "amount": 1500.0,
                "telegram_data": {"payment_method": "TC"},
            }
        )
        settled_late = self.create_statement_line(
            payment_date + timedelta(days=7), -1500.0
        )

        found = self.env["account.bank.statement.line"].search(
            self._picker_domain(request),
        )

        self.assertIn(settled_late, found)

    def test_a_transfer_cannot_reach_beyond_its_own_day(self):
        payment_date = date(2024, 3, 4)
        request = self.create_approval_request(
            {
                "date": payment_date,
                "amount": 1500.0,
                "telegram_data": {"payment_method": "Transferencia"},
            }
        )
        next_day = self.create_statement_line(payment_date + timedelta(days=1), -1500.0)

        found = self.env["account.bank.statement.line"].search(
            self._picker_domain(request),
        )

        self.assertNotIn(next_day, found)


@tagged("post_install", "-at_install")
class TestAutomationRuntimeCreation(PaymentApprovalTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.automation = cls.env["automation.rule"].create(
            {
                "name": "TEST - approval automation",
                "model_id": cls.env.ref("automation.model_automation_runtime_line").id,
                "trigger": "on_hand",
            }
        )
        cls.env["ir.actions.server"].create(
            {
                "name": "TEST - mark done",
                "automation_rule_id": cls.automation.id,
                "model_id": cls.env.ref("automation.model_automation_runtime_line").id,
                "state": "code",
                "sequence": 10,
                "code": "action.mark_action_done_and_continue(record)",
            }
        )
        cls.approval_category.automation_id = cls.automation

        cls.approver = new_test_user(
            cls.env,
            login="tg_ordinary_approver",
            groups="base.group_user",
        )
        cls.approval_category.write(
            {"step_ids": pool_step([(cls.approver.id, False, 10)], minimum=1)}
        )

    def _request(self, **vals):
        request = self.create_approval_request(
            {"partner_id": self.partner_fx.id, "amount": 1500.0, **vals}
        )
        request.action_confirm()
        return request

    def test_an_ordinary_internal_user_can_start_the_workflow(self):
        request = self._request().with_user(self.approver)

        request._create_automation_runtime()

        self.assertTrue(request.automation_runtime_id)
        self.assertEqual(request.automation_runtime_id.state, "in_progress")

    def test_the_runtime_records_who_approved_not_the_superuser(self):
        request = self._request().with_user(self.approver)

        request._create_automation_runtime()

        self.assertEqual(request.automation_runtime_id.create_uid, self.approver)

    def test_the_runtime_takes_the_request_currency_not_the_company_s(self):
        other_currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("id", "!=", self.company.currency_id.id)], limit=1)
        )
        request = self._request(currency_id=other_currency.id)

        request._create_automation_runtime()

        self.assertEqual(
            request.automation_runtime_id.currency_id,
            other_currency,
            "`amount` is a Monetary on both sides, so taking the company "
            "currency relabels the figure instead of converting it",
        )

    def test_the_runtime_date_is_the_day_the_payment_happened(self):
        request = self._request(date="2024-06-16 02:00:00").with_context(
            tz="America/Mexico_City"
        )

        request._create_automation_runtime()

        self.assertEqual(request.automation_runtime_id.date, date(2024, 6, 15))

    def test_a_second_runtime_for_one_approval_is_refused(self):
        request = self._request()
        request._create_automation_runtime()

        with self.assertRaises(UserError):
            request._create_automation_runtime()

    def test_a_partner_that_no_longer_exists_does_not_stop_the_workflow(self):
        ghost = self._create_partner({"name": "Deleted Payment Partner"})
        ghost_id = ghost.id
        ghost.unlink()

        request = self._request(telegram_data={"partner_cn_id": ghost_id})

        request._create_automation_runtime()

        runtime = request.automation_runtime_id
        self.assertTrue(runtime)
        self.assertEqual(runtime.partner_id, request.partner_id)
        self.assertFalse(runtime.third_party_id)

    def test_the_customer_from_telegram_is_the_run_s_partner(self):
        request = self._request(telegram_data={"partner_cn_id": self.partner_cn.id})

        request._create_automation_runtime()

        runtime = request.automation_runtime_id
        self.assertEqual(runtime.partner_id, self.partner_cn)
        self.assertEqual(
            runtime.third_party_id,
            request.partner_id,
            "the party the request is invoiced to stands in for the customer",
        )
        self.assertEqual(runtime.company_ids, request.company_id)

    def test_a_customer_invoiced_in_his_own_name_has_no_third_party(self):
        request = self._request(telegram_data={"partner_cn_id": self.partner_fx.id})

        request._create_automation_runtime()

        runtime = request.automation_runtime_id
        self.assertEqual(runtime.partner_id, request.partner_id)
        self.assertFalse(runtime.third_party_id)

    def test_the_last_approval_settles_the_request_s_statement_line_as_its_approver(
        self,
    ):
        self.approval_category.write(
            {"has_automation": "required", "has_bsl": "required"}
        )
        st_line = self.create_statement_line(date.today(), -1500.0)
        request = self._request(bank_statement_line_id=st_line.id)

        request.with_user(self.env.ref("base.user_admin")).action_approve()
        request.with_user(self.approver).action_approve()

        runtime = request.automation_runtime_id
        self.assertEqual(request.state, "approved")
        self.assertEqual(runtime.state, "in_progress")
        self.assertEqual(runtime.create_uid, self.approver)
        self.assertEqual(runtime.st_line_id, st_line)
        self.assertEqual(st_line.partner_id, request.partner_id)

    def test_the_workflow_privilege_reaches_only_a_claimed_statement_line(self):
        claimed = self.create_statement_line(date.today(), -1500.0)
        approved = self._request(bank_statement_line_id=claimed.id)
        approved.with_user(self.env.ref("base.user_admin")).action_approve()
        approved.with_user(self.approver).action_approve()
        self.assertEqual(approved.state, "approved")
        pending = self.create_statement_line(date.today(), -2000.0)
        self._request(bank_statement_line_id=pending.id)
        unclaimed = self.create_statement_line(date.today(), -2500.0)
        lines = (
            self.env["account.bank.statement.line"]
            .with_user(self.approver)
            .with_privilege(
                "approval_account_telegram.privilege_start_approved_workflow"
            )
        )

        self.assertFalse(
            self.env["account.bank.statement.line"]
            .with_user(self.approver)
            .has_access("read")
        )
        self.assertTrue(lines.browse(claimed.id).has_access("write"))
        self.assertFalse(lines.browse(pending.id).has_access("read"))
        self.assertFalse(lines.browse(unclaimed.id).has_access("read"))
        self.assertFalse(lines.browse(claimed.id).has_access("unlink"))

    def test_the_last_approval_starts_the_workflow_as_its_approver(self):
        self.approval_category.write({"has_automation": "required", "has_bsl": "no"})
        request = self._request()

        request.with_user(self.env.ref("base.user_admin")).action_approve()
        request.with_user(self.approver).action_approve()

        self.assertEqual(request.state, "approved")
        self.assertEqual(request.automation_runtime_id.state, "in_progress")
        self.assertEqual(request.automation_runtime_id.create_uid, self.approver)

    def test_the_approver_holds_no_automation_right_of_their_own(self):
        runtimes = self.env["automation.runtime"].with_user(self.approver)

        with self.assertRaises(AccessError):
            runtimes.create(
                {"automation_id": self.automation.id, "company_id": self.company.id}
            )

    def test_the_workflow_privilege_grants_no_more_than_starting_a_run(self):
        request = self._request().with_user(self.approver)
        request._create_automation_runtime()
        privileged = request.env["automation.runtime"].with_privilege(
            "approval_account_telegram.privilege_start_approved_workflow"
        )
        free_action = self.env["ir.actions.server"].create(
            {
                "name": "TEST - an action of no workflow",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": "pass",
            }
        )

        with self.assertRaises(AccessError):
            privileged.browse(request.automation_runtime_id.id).unlink()
        with self.assertRaises(AccessError):
            privileged.env["automation.rule"].browse(self.automation.id).write(
                {"name": "renamed"}
            )
        with self.assertRaises(AccessError):
            privileged.env["ir.actions.server"].browse(free_action.id).read(["name"])
