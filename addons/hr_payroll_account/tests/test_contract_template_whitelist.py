from odoo import tests
from odoo.tests.common import TransactionCase


@tests.tagged("post_install", "-at_install")
class TestContractTemplateWhitelist(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("hr_payroll.group_hr_payroll_manager")
        cls.employee = cls.env["hr.employee"].create({"name": "Template Target"})
        plan = cls.env["account.analytic.plan"].create({"name": "Payroll Plan"})
        cls.analytic_account = cls.env["account.analytic.account"].create(
            {"name": "Payroll Cost Center", "plan_id": plan.id}
        )

    def _load_template(self, template):
        wizard = (
            self.env["wizard.hr.employee.update.contract"]
            .with_context(active_model="hr.employee", active_id=self.employee.id)
            .create({"contract_template_id": template.id})
        )
        wizard.action_load_template()

    def test_analytic_distribution_is_loaded_from_the_template(self):
        distribution = {str(self.analytic_account.id): 100.0}
        template = self.env["hr.version"].create(
            {
                "name": "Analytic Template",
                "analytic_distribution": distribution,
            }
        )
        version = self.employee.version_id
        self.assertFalse(version.analytic_distribution, "nothing set up front")

        self._load_template(template)

        self.assertEqual(
            version.analytic_distribution,
            distribution,
            "the analytic distribution configured on the template must be copied",
        )
