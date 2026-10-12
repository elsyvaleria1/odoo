from unittest.mock import patch

from lxml import etree

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .common import TestAccountBudgetCommon
from odoo.addons.base.models.res_currency import ResCurrency


@tagged("post_install", "-at_install")
class TestBudgetFlows(TestAccountBudgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.aal_expense = cls.env["account.analytic.line"].create(
            {
                "name": "expense entry",
                "date": "2019-06-01",
                "amount": -500.0,
                cls.project_column_name: cls.analytic_account_partner_a.id,
            }
        )
        cls.aal_revenue = cls.env["account.analytic.line"].create(
            {
                "name": "revenue entry",
                "date": "2019-06-01",
                "amount": 300.0,
                cls.project_column_name: cls.analytic_account_partner_a.id,
            }
        )
        cls.account_asset_fixed = cls.env["account.account"].create(
            {
                "name": "Machinery",
                "code": "BUDGTFIX",
                "account_type": "asset_fixed",
            }
        )
        cls.account_asset_non_current = cls.env["account.account"].create(
            {
                "name": "Long-term deposits",
                "code": "BUDGTNCA",
                "account_type": "asset_non_current",
            }
        )
        cls.account_asset_current = cls.env["account.account"].create(
            {
                "name": "Inventory",
                "code": "BUDGTCUR",
                "account_type": "asset_current",
            }
        )

    def test_budget_dates_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["budget.analytic"].create(
                {
                    "name": "Inverted",
                    "date_from": "2019-12-31",
                    "date_to": "2019-01-01",
                }
            )

    def test_an_empty_analytic_change_keeps_the_budget_figures(self):
        expense_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(expense_line, achieved=500.0)
        lines = self.env["account.analytic.line"]
        lines.write({"name": "nothing"})
        lines.unlink()
        with self.assertQueryCount(0):
            self.assertEqual(expense_line.achieved_amount, 500.0)

    def test_achieved_amount_and_above_budget(self):
        expense_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(expense_line, achieved=500.0)
        self.assertFalse(expense_line.is_above_budget)

        revenue_line = self.budget_analytic_revenue.budget_line_ids[0]
        self.assertBudgetLine(revenue_line, achieved=300.0)

        small_budget = self.env["budget.analytic"].create(
            {
                "name": "Small 2019",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "expense",
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 100.0,
                            self.project_column_name: (
                                self.analytic_account_partner_a.id
                            ),
                        }
                    )
                ],
            }
        )
        small_line = small_budget.budget_line_ids
        self.assertBudgetLine(small_line, achieved=500.0)
        self.assertTrue(small_line.is_above_budget)

    def test_read_group_custom_aggregates(self):
        lines = self.budget_analytic_expense.budget_line_ids
        [row] = self.env["budget.line"]._read_group(
            [("budget_analytic_id", "=", self.budget_analytic_expense.id)],
            groupby=["budget_analytic_id"],
            aggregates=[
                "achieved_amount:sum",
                "achieved_amount:sum_currency",
                "theoretical_amount:sum",
                "theoretical_percentage:avg",
            ],
        )
        _budget, achieved_sum, achieved_sum_cur, theo_sum, theo_avg = row
        self.assertEqual(achieved_sum, sum(lines.mapped("achieved_amount")))
        self.assertEqual(achieved_sum_cur, achieved_sum)
        self.assertEqual(theo_sum, sum(lines.mapped("theoretical_amount")))
        self.assertEqual(
            theo_avg,
            sum(lines.mapped("theoretical_percentage")) / len(lines),
        )

        with patch.object(
            ResCurrency,
            "_convert",
            lambda self, from_amount, to_currency, *args, **kwargs: from_amount * 2,
        ):
            [doubled_row] = self.env["budget.line"]._read_group(
                [("budget_analytic_id", "=", self.budget_analytic_expense.id)],
                groupby=["budget_analytic_id"],
                aggregates=["achieved_amount:sum", "achieved_amount:sum_currency"],
            )
        self.assertEqual(doubled_row[1], achieved_sum)
        self.assertEqual(doubled_row[2], 2 * achieved_sum)

    def test_state_actions_and_unlink_guard(self):
        budget = self.budget_analytic_expense
        budget.action_budget_confirm()
        self.assertEqual(budget.state, "confirmed")
        budget.action_budget_cancel()
        self.assertEqual(budget.state, "canceled")
        budget.action_budget_draft()
        self.assertEqual(budget.state, "draft")
        budget.action_budget_confirm()
        budget.action_budget_done()
        self.assertEqual(budget.state, "done")

        with self.assertRaises(UserError):
            budget.unlink()

        disposable = budget.copy()
        disposable.action_budget_cancel()
        disposable.unlink()
        self.assertFalse(disposable.exists())

        budget.action_budget_draft()
        budget.unlink()
        self.assertFalse(budget.exists())

    def test_budget_and_line_window_actions(self):
        budget = self.budget_analytic_revenue
        action = budget.action_view_budget_lines()
        self.assertEqual(action["res_model"], "budget.line")
        self.assertEqual(action["context"]["default_budget_analytic_id"], budget.id)
        self.assertIn(("budget_analytic_id", "in", budget.ids), action["domain"])

        action = budget.action_view_budget_report()
        self.assertEqual(action["res_model"], "budget.report")
        self.assertEqual(
            action["context"]["search_default_budget_analytic_id"], budget.id
        )

        line = budget.budget_line_ids[0]
        action = line.action_view_budget_entries()
        self.assertIn(("budget_line_id", "=", line.id), action["domain"])
        self.assertIn(
            (
                self.project_column_name,
                "in",
                self.analytic_account_partner_a.ids,
            ),
            action["domain"],
        )

    def test_report_action_view_reference(self):
        report_row = self.env["budget.report"].search(
            [
                ("res_model", "=", "account.analytic.line"),
                ("res_id", "=", self.aal_expense.id),
            ],
            limit=1,
        )
        self.assertTrue(report_row)
        action = report_row.action_view_reference()
        self.assertEqual(action["res_model"], "account.analytic.line")
        self.assertEqual(action["res_id"], self.aal_expense.id)

    def _isolated_budget(self, *, amount, budget_type="expense"):
        account = self.env["account.analytic.account"].create(
            {"name": "isolated", "plan_id": self.analytic_plan_projects.id}
        )
        budget = self.env["budget.analytic"].create(
            {
                "name": "Isolated 2019",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": budget_type,
                "budget_line_ids": [
                    Command.create(
                        {"budget_amount": 1000.0, self.project_column_name: account.id}
                    )
                ],
            }
        )
        entry = self.env["account.analytic.line"].create(
            {
                "name": "isolated entry",
                "date": "2019-06-01",
                "amount": amount,
                self.project_column_name: account.id,
            }
        )
        return budget, entry

    def test_report_row_grain_is_one_per_line_and_budget(self):
        report = self.env["budget.report"]
        budget, entry = self._isolated_budget(amount=-500.0)
        domain = [
            ("res_model", "=", "account.analytic.line"),
            ("res_id", "=", entry.id),
        ]

        rows = report.search(domain)
        self.assertEqual(len(rows), 1, "exactly one budget covers the entry")
        self.assertEqual(len(set(rows.ids)), len(rows), "row ids must be unique")
        self.assertEqual(rows.budget_analytic_id, budget)

        [(achieved,)] = report._read_group(domain, aggregates=["achieved:sum"])
        self.assertEqual(achieved, 500.0)

    def test_report_reports_an_uncovered_entry_once(self):
        report = self.env["budget.report"]
        orphan_account = self.env["account.analytic.account"].create(
            {"name": "outside every budget", "plan_id": self.analytic_plan_projects.id}
        )
        orphan = self.env["account.analytic.line"].create(
            {
                "name": "orphan entry",
                "date": "2019-06-01",
                "amount": -42.0,
                self.project_column_name: orphan_account.id,
            }
        )
        rows = report.search(
            [("res_model", "=", "account.analytic.line"), ("res_id", "=", orphan.id)]
        )
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.budget_analytic_id)

    def test_report_does_not_double_a_revenue_entry(self):
        report = self.env["budget.report"]
        _budget, entry = self._isolated_budget(amount=300.0, budget_type="revenue")
        [(achieved,)] = report._read_group(
            [("res_model", "=", "account.analytic.line"), ("res_id", "=", entry.id)],
            aggregates=["achieved:sum"],
        )
        self.assertEqual(achieved, 300.0)

    def test_report_fans_out_over_every_covering_budget(self):
        report = self.env["budget.report"]
        aal_domain = [
            ("res_model", "=", "account.analytic.line"),
            ("res_id", "=", self.aal_revenue.id),
        ]
        before = report.search(aal_domain)

        second = self.env["budget.analytic"].create(
            {
                "name": "Budget 2019: Revenue bis",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "revenue",
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 1000.0,
                            self.project_column_name: (
                                self.analytic_account_partner_a.id
                            ),
                        }
                    )
                ],
            }
        )
        after = report.search(aal_domain)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(len(set(after.ids)), len(after), "row ids must be unique")
        self.assertIn(second, after.budget_analytic_id)

    def test_report_sees_an_unflushed_budget(self):
        line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(line, achieved=500.0)

        self.budget_analytic_expense.budget_type = "revenue"
        self.assertEqual(
            line.achieved_amount,
            300.0,
            "an expense entry drops out and the revenue entry counts",
        )

    def test_plain_internal_user_cannot_rewrite_budget_figures(self):
        plain = self.env["res.users"].create(
            {
                "name": "Plain Employee",
                "login": "plain_employee_budget_test",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        line = self.budget_analytic_expense.budget_line_ids[0]

        self.assertTrue(
            line.with_user(plain).read(["budget_amount"]),
            "internal users must keep read access",
        )
        with self.assertRaises(AccessError):
            line.with_user(plain).write({"budget_amount": 999999.0})
        with self.assertRaises(AccessError):
            self.env["budget.line"].with_user(plain).create(
                {
                    "budget_analytic_id": self.budget_analytic_expense.id,
                    "budget_amount": 1.0,
                    self.project_column_name: self.analytic_account_partner_a.id,
                }
            )
        self.assertEqual(line.budget_amount, 55000.0, "the figure is untouched")

    def test_state_machine_refuses_illegal_transitions(self):
        budget = self.budget_analytic_expense
        with self.assertRaises(UserError, msg="draft cannot go straight to done"):
            budget.action_budget_done()

        budget.action_budget_cancel()
        with self.assertRaises(UserError, msg="a canceled budget cannot be opened"):
            budget.action_budget_confirm()
        with self.assertRaises(UserError, msg="a canceled budget cannot be done"):
            budget.action_budget_done()

        budget.action_budget_draft()
        budget.action_budget_confirm()
        budget.action_budget_done()
        with self.assertRaises(UserError, msg="a done budget cannot be canceled"):
            budget.action_budget_cancel()
        budget.action_budget_draft()
        self.assertEqual(budget.state, "draft")

    def test_unlink_guard_covers_revisions(self):
        original = self.budget_analytic_expense
        original.action_budget_confirm()
        revision = self.env["budget.analytic"].browse(
            original.action_create_revision()["res_id"]
        )
        revision.action_budget_confirm()
        self.assertEqual(revision.state, "confirmed")
        self.assertEqual(original.state, "revised")

        original.action_budget_draft()
        with self.assertRaises(UserError):
            original.unlink()
        self.assertTrue(revision.exists(), "the revision survives the refused delete")

        revision.action_budget_cancel()
        original.unlink()
        self.assertFalse(revision.exists(), "canceled revisions go with their original")

    def test_budget_line_period_cannot_diverge_from_its_budget(self):
        line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertFalse(line._fields["date_to"].store)
        line.write({"date_to": "2019-06-30"})
        self.env.invalidate_all()
        self.assertEqual(line.date_to, self.budget_analytic_expense.date_to)

    def test_achieved_amount_reacts_to_a_new_analytic_line(self):
        line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertEqual(line.achieved_amount, 500.0)
        self.env["account.analytic.line"].create(
            {
                "name": "another expense",
                "date": "2019-06-02",
                "amount": -250.0,
                self.project_column_name: self.analytic_account_partner_a.id,
            }
        )
        self.assertEqual(
            line.achieved_amount, 750.0, "no manual invalidation should be needed"
        )
        self.assertEqual(line.achieved_percentage, 750.0 / 55000.0)

    def test_a_budget_reset_to_draft_can_be_reopened_despite_revisions(self):
        budget = self.budget_analytic_expense
        budget.action_budget_confirm()
        self.env["budget.analytic"].browse(budget.action_create_revision()["res_id"])
        budget.action_budget_draft()
        self.assertEqual(budget.state, "draft")

        budget.action_budget_confirm()
        self.assertEqual(
            budget.state, "revised", "a budget with revisions reopens as revised"
        )

    def test_a_canceled_revision_does_not_block_reconfirm(self):
        budget = self.budget_analytic_expense
        budget.action_budget_confirm()
        revision = self.env["budget.analytic"].browse(
            budget.action_create_revision()["res_id"]
        )
        budget.action_budget_draft()
        revision.action_budget_cancel()

        budget.action_budget_confirm()
        self.assertEqual(
            budget.state,
            "confirmed",
            "a canceled revision should not keep the original permanently revised",
        )

    def test_state_error_message_uses_the_labels_the_buttons_show(self):
        budget = self.budget_analytic_expense
        with self.assertRaises(UserError) as error:
            budget.action_budget_done()
        self.assertIn("Draft", str(error.exception))
        self.assertIn("Done", str(error.exception))
        self.assertNotIn("confirmed", str(error.exception))

    def test_duplicating_a_budget_keeps_its_type(self):
        budget = self.budget_analytic_revenue
        copy = budget.copy()
        self.assertEqual(copy.budget_type, budget.budget_type)
        self.assertEqual(
            copy.budget_line_ids[0].achieved_amount,
            budget.budget_line_ids[0].achieved_amount,
            "same account, same period, same lines: the figure must match",
        )

    def test_a_budget_line_must_carry_an_analytic_account(self):
        with self.assertRaises(ValidationError):
            self.env["budget.line"].create(
                {
                    "budget_analytic_id": self.budget_analytic_expense.id,
                    "budget_amount": 1.0,
                }
            )
        with self.assertRaises(ValidationError):
            self.env["budget.analytic"].create(
                {
                    "name": "no account",
                    "date_from": "2019-01-01",
                    "date_to": "2019-12-31",
                    "budget_line_ids": [Command.create({"budget_amount": 1.0})],
                }
            )

    def test_a_budget_line_cannot_target_another_company_s_account(self):
        project_plan, _other_plans = self.env["account.analytic.plan"]._get_all_plans()
        other_company = self.env["res.company"].create({"name": "Other Co"})
        foreign_account = self.env["account.analytic.account"].create(
            {
                "name": "foreign",
                "plan_id": project_plan.id,
                "company_id": other_company.id,
            }
        )
        with self.assertRaises(UserError):
            self.env["budget.line"].create(
                {
                    "budget_analytic_id": self.budget_analytic_expense.id,
                    "budget_amount": 1.0,
                    "account_id": foreign_account.id,
                }
            )

    def test_report_figures_refresh_without_a_manual_invalidation(self):
        report = self.env["budget.report"]
        line = self.budget_analytic_expense.budget_line_ids[0]
        domain = [("budget_line_id", "=", line.id), ("line_type", "=", "budget")]
        self.assertEqual(report.search(domain).mapped("budget"), [55000.0])

        line.budget_amount = 4242.0
        self.assertEqual(
            report.search(domain).mapped("budget"),
            [4242.0],
            "writing a budget line must refresh the report with no manual invalidation",
        )

        self.budget_analytic_expense.name = "Renamed 2019"
        self.assertEqual(
            report.search(domain).mapped("description"),
            ["Renamed 2019"],
            "writing a budget must refresh the report too",
        )

    def test_the_budget_report_is_not_readable_by_every_employee(self):
        plain = self.env["res.users"].create(
            {
                "name": "Plain Employee",
                "login": "plain_employee_budget_report_test",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        with self.assertRaises(AccessError):
            self.env["budget.report"].with_user(plain).search([], limit=1)
        self.assertTrue(
            self.budget_analytic_expense.budget_line_ids[0]
            .with_user(plain)
            .read(["budget_amount"])
        )

    def test_the_analytic_account_budgets_tab_lists_its_lines(self):
        project_plan, _other_plans = self.env["account.analytic.plan"]._get_all_plans()
        account = self.env["account.analytic.account"].create(
            {"name": "tabbed", "plan_id": project_plan.id}
        )
        budget = self.env["budget.analytic"].create(
            {
                "name": "Tab 2019",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_line_ids": [
                    Command.create({"budget_amount": 10.0, "account_id": account.id})
                ],
            }
        )
        self.assertFalse(
            account.budget_line_ids.ids,
            "without the plan in context the inverse cannot resolve",
        )
        self.assertEqual(
            account.with_context(analytic_plan_id=project_plan.id).budget_line_ids,
            budget.budget_line_ids,
            "the tab's own context is what makes it list anything",
        )

        view = self.env.ref(
            "account_budget.view_account_analytic_account_form_inherit_budget"
        )
        self.assertIn(
            "'analytic_plan_id': plan_id",
            view.arch,
            "the Budgets tab must pass the plan the inverse is computed against",
        )
        self.assertIn('groups="analytic.group_analytic_accounting"', view.arch)

    def test_sum_currency_really_converts_across_companies(self):
        project_plan, _other_plans = self.env["account.analytic.plan"]._get_all_plans()
        other_currency = self.env.ref("base.EUR")
        if other_currency == self.env.company.currency_id:
            other_currency = self.env.ref("base.USD")
        other_currency.active = True
        self.env["res.currency.rate"].create(
            {"name": "2021-01-01", "currency_id": other_currency.id, "rate": 2.0}
        )
        other_company = self.env["res.company"].create(
            {"name": "Second currency Co", "currency_id": other_currency.id}
        )
        shared_account = self.env["account.analytic.account"].create(
            {"name": "shared", "plan_id": project_plan.id, "company_id": False}
        )

        budgets = self.env["budget.analytic"].create(
            [
                {
                    "name": f"Currency {company.name}",
                    "date_from": "2021-01-01",
                    "date_to": "2021-12-31",
                    "budget_type": "expense",
                    "company_id": company.id,
                    "budget_line_ids": [
                        Command.create(
                            {"budget_amount": 100.0, "account_id": shared_account.id}
                        )
                    ],
                }
                for company in (self.env.company, other_company)
            ]
        )
        self.env["account.analytic.line"].create(
            [
                {
                    "name": f"entry {company.name}",
                    "date": "2021-06-01",
                    "amount": -50.0,
                    "account_id": shared_account.id,
                    "company_id": company.id,
                }
                for company in (self.env.company, other_company)
            ]
        )

        env = self.env(
            context=dict(
                self.env.context,
                allowed_company_ids=[self.env.company.id, other_company.id],
            )
        )
        lines = budgets.budget_line_ids.with_env(env)
        self.assertEqual(lines.mapped("achieved_amount"), [50.0, 50.0])
        [(plain, converted)] = env["budget.line"]._read_group(
            [("id", "in", lines.ids)],
            groupby=[],
            aggregates=["achieved_amount:sum", "achieved_amount:sum_currency"],
        )
        self.assertEqual(plain, 100.0, "the plain sum adds two different currencies")
        self.assertEqual(
            converted, 75.0, "50 in company currency + 50 at rate 2.0 = 50 + 25"
        )

    def test_a_line_scoping_no_plan_claims_nothing(self):
        budget = self.env["budget.analytic"].create(
            {
                "name": "Unscoped 2019",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "expense",
            }
        )
        self.env.cr.execute(
            """
            INSERT INTO budget_line (budget_analytic_id, budget_amount, sequence,
                                     create_uid, write_uid, create_date, write_date)
                 VALUES (%s, 1000.0, 10, 1, 1, now(), now())
              RETURNING id
            """,
            (budget.id,),
        )
        [naked_id] = self.env.cr.fetchone()
        self.env["budget.line"].invalidate_model()
        naked = self.env["budget.line"].browse(naked_id)

        self.assertEqual(
            naked.achieved_amount,
            0.0,
            "an unscoped line must not absorb every entry in its period",
        )
        self.assertEqual(
            self.env["budget.report"].search_count(
                [("budget_line_id", "=", naked_id), ("line_type", "=", "budget")]
            ),
            1,
            "it still shows up as a budgeted row, so the bad data stays visible",
        )

    def test_a_partially_scoped_line_still_matches_on_the_plans_it_sets(self):
        entry = self.env["account.analytic.line"].create(
            {
                "name": "two-plan entry",
                "date": "2019-06-01",
                "amount": -125.0,
                self.project_column_name: self.analytic_account_partner_b.id,
                self.department_column_name: self.analytic_account_administratif_2.id,
            }
        )
        self.assertTrue(entry)
        project_only = self.budget_analytic_expense.budget_line_ids[1]
        self.assertFalse(project_only[self.department_column_name])
        self.assertEqual(
            project_only.achieved_amount,
            125.0,
            "an empty plan column is a wildcard, not a scope of nothing",
        )

    def test_asset_spend_counts_against_an_expense_budget(self):
        expense_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(expense_line, achieved=500.0)

        self.env["account.analytic.line"].create(
            [
                {
                    "name": "tractor",
                    "date": "2019-06-15",
                    "amount": -1000.0,
                    "general_account_id": self.account_asset_fixed.id,
                    self.project_column_name: self.analytic_account_partner_a.id,
                },
                {
                    "name": "tenancy deposit",
                    "date": "2019-06-15",
                    "amount": -250.0,
                    "general_account_id": self.account_asset_non_current.id,
                    self.project_column_name: self.analytic_account_partner_a.id,
                },
            ]
        )

        self.assertBudgetLine(expense_line, achieved=1750.0)

    def test_a_current_asset_entry_stays_out_of_the_budget(self):
        expense_line = self.budget_analytic_expense.budget_line_ids[0]

        self.env["account.analytic.line"].create(
            {
                "name": "inventory leg of a COGS pair",
                "date": "2019-06-15",
                "amount": 1000.0,
                "general_account_id": self.account_asset_current.id,
                self.project_column_name: self.analytic_account_partner_a.id,
            }
        )

        self.assertBudgetLine(expense_line, achieved=500.0)

    def _entry_with_analytic_distribution(self, date, account=None):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": (
                                account or self.company_data["default_account_expense"]
                            ).id,
                            "debit": 100.0,
                            "analytic_distribution": {
                                str(self.analytic_account_partner_a.id): 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_payable"
                            ].id,
                            "credit": 100.0,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        return move

    def test_a_move_lists_the_budgets_its_analytic_entries_fall_under(self):
        move = self._entry_with_analytic_distribution("2019-06-15")

        self.assertEqual(
            move.budget_analytic_ids,
            self.budget_analytic_expense | self.budget_analytic_both,
        )

    def test_a_move_outside_every_budget_period_lists_no_budget(self):
        move = self._entry_with_analytic_distribution("2020-06-15")

        self.assertFalse(move.budget_analytic_ids)

    def test_a_report_scoped_to_analytic_lines_holds_those_lines_alone(self):
        move = self._entry_with_analytic_distribution("2019-06-15")
        self._entry_with_analytic_distribution("2019-07-15")
        line_ids = move.line_ids.analytic_line_ids.ids
        report = self.env["budget.report"]

        def rows(records):
            return sorted(
                (row.res_model, row.res_id, row.budget_analytic_id.id)
                for row in records
            )

        scoped = report.with_context(budget_report_analytic_line_ids=line_ids)
        self.assertEqual(
            rows(scoped.search([])),
            rows(
                report.search(
                    [
                        ("res_model", "=", "account.analytic.line"),
                        ("res_id", "in", line_ids),
                    ]
                )
            ),
        )
        self.assertTrue(scoped.search([("budget_analytic_id", "!=", False)]))

    def test_the_budget_period_is_a_single_daterange_field(self):
        arch = etree.fromstring(
            self.env["budget.analytic"].get_view(
                self.env.ref("account_budget.view_budget_analytic_form").id, "form"
            )["arch"]
        )
        period = arch.xpath("//field[@name='date_from']")
        self.assertEqual(len(period), 1, "the period is one field, not two")
        self.assertEqual(period[0].get("widget"), "daterange")
        self.assertEqual(period[0].get("options"), "{'end_date_field': 'date_to'}")
        self.assertEqual(
            period[0].get("readonly"),
            "state != 'draft'",
            "the period must stay locked outside draft",
        )
        self.assertFalse(
            arch.xpath("//field[@name='date_to']"),
            "the end date is rendered by the daterange widget, not on its own",
        )
