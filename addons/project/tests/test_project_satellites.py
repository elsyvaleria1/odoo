from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import new_test_user
from odoo.tools.translate import code_translations

from .test_project_base import TestProjectCommon


class TestAnalyticAccountDeletionGuard(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        plan = cls.env["account.analytic.plan"].create({"name": "Guarded"})
        cls.account = cls.env["account.analytic.account"].create(
            {"name": "Guarded account", "plan_id": plan.id}
        )
        cls.project = cls.env["project.project"].create(
            {
                "name": "Members only",
                "account_id": cls.account.id,
                "privacy_visibility": "followers",
            }
        )
        cls.task = cls.env["project.task"].create(
            {"name": "Kept", "project_id": cls.project.id}
        )

    def test_an_archived_task_still_keeps_its_account(self) -> None:
        self.task.active = False
        with self.assertRaises(UserError):
            self.account.unlink()

    def test_a_task_the_deleter_cannot_read_still_keeps_its_account(self) -> None:
        accountant = new_test_user(
            self.env,
            "guard_accountant",
            groups="base.group_user,analytic.group_analytic_accounting",
        )
        self.assertFalse(self.task.with_user(accountant).has_access("read"))
        with self.assertRaises(UserError):
            self.account.with_user(accountant).unlink()

    def test_an_account_without_tasks_is_deleted(self) -> None:
        self.task.unlink()
        self.project.account_id = False
        self.account.unlink()
        self.assertFalse(self.account.exists())


class TestBenefitReviewReminder(TestProjectCommon):
    def test_the_reminder_speaks_the_accountable_owners_language(self) -> None:
        self.env["res.lang"]._activate_lang("fr_FR")
        key = ("project", "fr_FR")
        code_translations.python_translations[key] = {
            **code_translations.get_python_translations(*key),
            "Benefit review: %s": "Revue du bénéfice : %s",
        }
        self.addCleanup(code_translations.python_translations.pop, key)
        self.user_projectuser.lang = "fr_FR"
        benefit = self.env["project.benefit"].create(
            {
                "name": "Faster delivery",
                "project_id": self.project_pigs.id,
                "accountable_id": self.user_projectuser.id,
                "date_review": fields.Date.today() - timedelta(days=1),
            }
        )
        self.env["project.benefit"].with_context(
            lang="en_US"
        )._cron_check_review_dates()
        self.assertEqual(
            benefit.activity_ids.summary, "Revue du bénéfice : Faster delivery"
        )


class TestForecastMessagesAreTranslated(TestProjectCommon):
    def test_an_empty_forecast_answers_in_the_users_language(self) -> None:
        self.env["res.lang"]._activate_lang("fr_FR")
        key = ("project", "fr_FR")
        code_translations.python_translations[key] = {
            **code_translations.get_python_translations(*key),
            "No remaining items to forecast.": "Rien à prévoir.",
        }
        self.addCleanup(code_translations.python_translations.pop, key)
        wizard = (
            self.env["wizard.project.project.view.forecast"]
            .with_context(lang="fr_FR")
            .create({"project_id": self.project_pigs.id, "remaining_items": 0})
        )
        wizard.action_run_forecast()
        self.assertEqual(wizard.result_text, "Rien à prévoir.")
