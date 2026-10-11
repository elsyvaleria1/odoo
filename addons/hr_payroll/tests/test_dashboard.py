import base64
from datetime import date

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("-at_install", "post_install", "payroll_dashboard_ui")
class TestDashboardUi(HttpCase):
    def test_dashboard_ui(self):
        company = self.env["res.company"].create(
            {
                "name": "Payroll Dashboard Company",
            }
        )
        user = mail_new_test_user(
            self.env,
            name="Laurie Poiret",
            login="dashboarder",
            groups="base.group_user,hr_payroll.group_hr_payroll_manager",
            company_id=company.id,
        )
        if self.env.ref("sign.group_sign_manager", raise_if_not_found=False):
            user.group_ids += self.env.ref(
                "sign.group_sign_manager", raise_if_not_found=False
            )
        department = self.env["hr.department"].create(
            {
                "name": "Payroll",
                "company_id": company.id,
            }
        )
        self.env["hr.employee"].create(
            {
                "user_id": user.id,
                "company_id": company.id,
                "department_id": department.id,
                "resource_calendar_id": company.resource_calendar_id.id,
            }
        )
        if self.env["ir.module.module"].search(
            [("name", "=", "sign"), ("state", "=", "installed")]
        ):
            user.group_ids += self.env.ref(
                "sign.group_sign_manager", raise_if_not_found=False
            )
            with file_open("sign/static/demo/employment.pdf", "rb") as f:
                pdf_content = base64.b64encode(f.read())

            attachment = (
                self.env["ir.attachment"]
                .with_user(user)
                .create(
                    {
                        "type": "binary",
                        "datas": pdf_content,
                        "name": "Employment Contract.pdf",
                    }
                )
            )
            template = (
                self.env["sign.template"]
                .with_user(user)
                .create(
                    {
                        "name": "Employment Contract",
                    }
                )
            )
            self.env["sign.document"].with_user(user).create(
                {
                    "attachment_id": attachment.id,
                    "template_id": template.id,
                }
            )
        self.start_tour(
            "/web", "payroll_dashboard_ui_tour", login="dashboarder", timeout=300
        )


@tagged("-at_install", "post_install", "payroll_dashboard")
class TestDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Dashboard Company",
            }
        )
        cls.user = mail_new_test_user(
            cls.env,
            name="Laurie Poiret",
            login="dashboarder",
            groups="base.group_user,hr_payroll.group_hr_payroll_manager",
            company_id=cls.company.id,
        )

    def test_multi_sections(self):
        Payslip = self.env["hr.payslip"]

        all_sections = Payslip._get_dashboard_default_sections()
        dashboard = Payslip.get_payroll_dashboard_data(all_sections)
        self.assertTrue(all(section in dashboard for section in all_sections))

        sub_sections = all_sections[1:3]
        dashboard = Payslip.get_payroll_dashboard_data(sub_sections)
        self.assertEqual(len(sub_sections), len(dashboard))
        self.assertTrue(all(section in dashboard for section in sub_sections))

    def test_dashboard_batches(self):
        payslip_runs = self.env["hr.payslip.run"].create(
            [
                {
                    "name": "Batch 1 - Oct",
                    "date_start": "2021-10-01",
                    "date_end": "2021-10-31",
                    "company_id": self.company.id,
                },
                {
                    "name": "Batch 1 - Sept",
                    "date_start": "2021-09-01",
                    "date_end": "2021-09-30",
                    "company_id": self.company.id,
                },
                {
                    "name": "Batch 2 - Sept",
                    "date_start": "2021-09-01",
                    "date_end": "2021-09-30",
                    "company_id": self.company.id,
                },
                {
                    "name": "Batch 1 - June",
                    "date_start": "2021-06-01",
                    "date_end": "2021-06-30",
                    "company_id": self.company.id,
                },
                {
                    "name": "Batch 1 - May",
                    "date_start": "2021-05-01",
                    "date_end": "2021-05-31",
                    "company_id": self.company.id,
                },
            ]
        )
        with freeze_time(date(2021, 12, 31)):
            batches_to_return = payslip_runs.filtered(lambda r: r.date_start.month >= 6)
            dashboard = (
                self.env["hr.payslip"]
                .with_user(self.user)
                .get_payroll_dashboard_data(sections=["batches"])
            )
            self.assertTrue("batches" in dashboard)
            self.assertEqual(len(dashboard["batches"]), len(batches_to_return))
            self.assertEqual(
                {read["id"] for read in dashboard["batches"]},
                set(batches_to_return.ids),
            )

    def test_dashboard_empty_stats(self):
        dashboard = (
            self.env["hr.payslip"]
            .with_user(self.user)
            .get_payroll_dashboard_data(sections=["stats"])
        )
        self.assertTrue(all(stats["is_sample"] is True for stats in dashboard["stats"]))

    def _test_dashboard_stats(self):
        today = date.today()
        self.env["hr.employee"].create(
            [
                {
                    "name": "Employee 1",
                    "company_id": self.company.id,
                    "date_version": today - relativedelta(months=1, day=1),
                    "contract_date_start": today - relativedelta(months=1, day=1),
                    "contract_date_end": False,
                    "wage": 1000,
                },
                {
                    "name": "Employee 2",
                    "company_id": self.company.id,
                    "date_version": today - relativedelta(day=1),
                    "contract_date_start": today - relativedelta(day=1),
                    "contract_date_end": False,
                    "wage": 2000,
                },
                {
                    "name": "Employee 3",
                    "company_id": self.company.id,
                    "date_version": today + relativedelta(months=1, day=1),
                    "contract_date_start": today + relativedelta(months=1, day=1),
                    "contract_date_end": False,
                    "wage": 4500,
                },
            ]
        )

        self.env["hr.employee"].flush_model()
        self.env["hr.version"].flush_model()

        dashboard = (
            self.env["hr.payslip"]
            .with_user(self.user)
            .get_payroll_dashboard_data(sections=["stats"])
        )
        employer_cost = employees = None
        for section in dashboard["stats"]:
            if section["id"] == "employer_cost":
                employer_cost = section
            elif section["id"] == "employees":
                employees = section
        self.assertTrue(all([employer_cost, employees]))

        employees_stat = employees["data"]["monthly"]
        self.assertEqual(employees_stat[0]["value"], 1)
        self.assertEqual(employees_stat[1]["value"], 2)
        self.assertEqual(employees_stat[2]["value"], 3)

        return employees["data"]["yearly"]

    def test_dashboard_stat_end_of_year(self):
        with freeze_time(date(2021, 12, 1)):
            employees_stat = self._test_dashboard_stats()
            self.assertEqual(employees_stat[0]["value"], 0)
            self.assertEqual(employees_stat[1]["value"], 2)
            self.assertEqual(employees_stat[2]["value"], 3)

    def test_dashboard_stat_start_of_year(self):
        with freeze_time(date(2021, 1, 1)):
            employees_stat = self._test_dashboard_stats()
            self.assertEqual(employees_stat[0]["value"], 1)
            self.assertEqual(employees_stat[1]["value"], 3)
            self.assertEqual(employees_stat[2]["value"], 3)

    def test_dashboard_stat_middle_of_year(self):
        with freeze_time(date(2021, 6, 1)):
            employees_stat = self._test_dashboard_stats()
            self.assertEqual(employees_stat[0]["value"], 0)
            self.assertEqual(employees_stat[1]["value"], 3)
            self.assertEqual(employees_stat[2]["value"], 3)

    def test_dashboard_no_english_language_access(self):
        Payslip = self.env["hr.payslip"]
        self.env["res.lang"]._activate_lang("fr_FR")
        fr_lang = self.env["res.lang"].search([["code", "=", "fr_FR"]])
        if "website" in self.env:
            self.env["website"].search([]).write(
                {"language_ids": fr_lang.ids, "default_lang_id": fr_lang.id}
            )
        self.env["res.users"].with_context(active_test=False).search([]).write(
            {"lang": "fr_FR"}
        )
        self.env["res.partner"].with_context(active_test=False).search([]).write(
            {"lang": "fr_FR"}
        )

        self.env["res.lang"].search([["code", "=", "en_US"]]).active = False

        Payslip.get_payroll_dashboard_data()
        Payslip.get_dashboard_warnings()
