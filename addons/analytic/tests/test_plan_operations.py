import psycopg

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestAnalyticPlanOperations(TransactionCase):
    def test_delete_plan(self):
        plan = self.env["account.analytic.plan"].create({"name": "Test Plan"})
        column = plan._column_name()

        self.env.cr.execute(f"SELECT {column} FROM account_analytic_line LIMIT 1")

        plan.unlink()
        with self.assertRaises(psycopg.errors.UndefinedColumn), mute_logger("odoo.db"):
            self.env.cr.execute(f"SELECT {column} FROM account_analytic_line LIMIT 1")

    def test_delete_subplan(self):
        parent = self.env["account.analytic.plan"].create({"name": "Parent Plan"})
        plan = self.env["account.analytic.plan"].create(
            {"name": "Test Plan", "parent_id": parent.id}
        )
        other_plan = self.env["account.analytic.plan"].create(
            {"name": "Other Plan", "parent_id": parent.id}
        )
        self.assertFalse(plan._get_plan_column("account.analytic.line"))
        related_field = plan._get_related_field("account.analytic.line")
        self.assertTrue(related_field.exists())
        other_plan.unlink()
        self.assertTrue(related_field.exists())
        plan.unlink()
        self.assertFalse(related_field.exists())

    def test_delete_plan_with_its_subplans(self):
        Plan = self.env["account.analytic.plan"]
        root = Plan.create({"name": "Root Plan"})
        child = Plan.create({"name": "Child Plan", "parent_id": root.id})
        grandchild = Plan.create({"name": "Grandchild Plan", "parent_id": child.id})
        column_name = root._column_name()
        column = root._get_plan_column("account.analytic.line")
        related_fields = (child | grandchild)._get_related_field(
            "account.analytic.line"
        )
        self.assertEqual(len(related_fields), 2)

        root.unlink()

        self.assertFalse(column.exists())
        self.assertFalse(related_fields.exists())
        self.assertFalse((child | grandchild).exists())
        self.assertNotIn(
            column_name, self.env["account.analytic.line"]._get_plan_fnames()
        )

    def test_delete_plans_of_two_trees_at_once(self):
        Plan = self.env["account.analytic.plan"]
        lone_root, root = Plan.create([{"name": "Lone Root"}, {"name": "Root"}])
        child = Plan.create({"name": "Child", "parent_id": root.id})
        lone_column = lone_root._column_name()
        related_field = child._get_related_field("account.analytic.line")

        (lone_root | root).unlink()

        self.assertFalse(related_field.exists())
        self.assertNotIn(
            lone_column, self.env["account.analytic.line"]._get_plan_fnames()
        )
        self.assertFalse(Plan.search([("root_id", "in", (lone_root | root).ids)]))

    def test_delete_subplan_with_a_sibling_tree_kept(self):
        Plan = self.env["account.analytic.plan"]
        doomed_root, root = Plan.create([{"name": "Doomed Root"}, {"name": "Root"}])
        child, kept = Plan.create(
            [
                {"name": "Child", "parent_id": root.id},
                {"name": "Kept", "parent_id": root.id},
            ]
        )
        related_field = kept._get_related_field("account.analytic.line")

        (doomed_root | child).unlink()

        self.assertTrue(related_field.exists())
        self.assertEqual(kept.root_id, root)
        self.assertIn(
            root._column_name(), self.env["account.analytic.line"]._get_plan_fnames()
        )

    def test_rename_plan(self):
        plan = self.env["account.analytic.plan"].create({"name": "Test Plan"})
        column = plan._get_plan_column("account.analytic.line")
        plan.name = "New name"
        self.assertEqual(column.field_description, "New name")

    def test_promote_subplan(self):
        parent = self.env["account.analytic.plan"].create({"name": "Parent Plan"})
        plan = self.env["account.analytic.plan"].create(
            {"name": "Test Plan", "parent_id": parent.id}
        )
        self.assertFalse(plan._get_plan_column("account.analytic.line"))
        self.assertTrue(plan._get_related_field("account.analytic.line"))
        plan.parent_id = False
        self.assertTrue(plan._get_plan_column("account.analytic.line"))
        self.assertFalse(plan._get_related_field("account.analytic.line"))

    def test_demote_plan(self):
        parent = self.env["account.analytic.plan"].create({"name": "Parent Plan"})
        plan = self.env["account.analytic.plan"].create({"name": "Test Plan"})
        self.assertTrue(plan._get_plan_column("account.analytic.line"))
        self.assertFalse(plan._get_related_field("account.analytic.line"))
        plan.parent_id = parent
        self.assertFalse(plan._get_plan_column("account.analytic.line"))
        self.assertTrue(plan._get_related_field("account.analytic.line"))

    def test_project_plan_cannot_be_reparented(self):
        project_plan, __ = self.env["account.analytic.plan"]._get_all_plans()
        other_plan = self.env["account.analytic.plan"].create({"name": "Other Plan"})
        with self.assertRaises(ValidationError):
            project_plan.parent_id = other_plan.id

    def test_delete_plan_with_view(self):
        plan = self.env["account.analytic.plan"].create({"name": "Test Plan"})
        column = plan._column_name()

        self.env["ir.ui.view"].create(
            {
                "name": "Manual view",
                "model": "account.analytic.line",
                "type": "search",
                "arch": f'<search><field name="{column}"/></search>',
            }
        )

        with self.assertRaisesRegex(UserError, "still present in views"):
            plan.unlink()

    def test_validate_deleted_account(self):
        plan, mandatory_plan = self.env["account.analytic.plan"].create(
            [
                {
                    "name": "Test Plan",
                },
                {
                    "name": "Mandatory Plan",
                    "default_applicability": "mandatory",
                },
            ]
        )
        test_account, mandatory_account = self.env["account.analytic.account"].create(
            [
                {
                    "name": "Test Account",
                    "code": "TAC",
                    "plan_id": plan.id,
                },
                {
                    "name": "Mandatory Account",
                    "code": "manda",
                    "plan_id": mandatory_plan.id,
                },
            ]
        )
        distribution_model = (
            self.env["account.analytic.distribution.model"]
            .create({})
            .with_context(validate_analytic=True)
        )

        distribution_model.analytic_distribution = {f"{test_account.id}": 100}
        with self.assertRaisesRegex(UserError, r"require a 100% analytic distribution"):
            distribution_model._check_distribution()

        distribution_model.analytic_distribution = {
            f"{test_account.id},{mandatory_account.id}": 100
        }
        distribution_model._check_distribution()

        test_account.unlink()
        plan.unlink()
        distribution_model._check_distribution()

    def test_validate_company_plans(self):
        company_2 = self.env["res.company"].create(
            {
                "name": "company_2",
            }
        )
        plan = self.env["account.analytic.plan"].create(
            [
                {
                    "name": "Plan",
                    "default_applicability": "optional",
                }
            ]
        )
        applicability = self.env["account.analytic.applicability"].create(
            {
                "business_domain": "general",
                "analytic_plan_id": plan.id,
                "applicability": "mandatory",
                "company_id": company_2.id,
            }
        )
        self.env["account.analytic.account"].create(
            [
                {
                    "name": "Mandatory Account",
                    "code": "manda",
                    "plan_id": plan.id,
                }
            ]
        )
        distribution_model = (
            self.env["account.analytic.distribution.model"]
            .create({})
            .with_context(validate_analytic=True)
        )

        distribution_model._check_distribution(
            business_domain="general", company_id=self.env.company.id
        )

        applicability.company_id = False
        with self.assertRaisesRegex(UserError, r"require a 100% analytic distribution"):
            distribution_model._check_distribution(
                business_domain="general", company_id=self.env.company.id
            )
        with self.assertRaisesRegex(UserError, r"require a 100% analytic distribution"):
            distribution_model._check_distribution(business_domain="general")
