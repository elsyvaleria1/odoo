import datetime

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo.tests.common import HttpCase, tagged

from odoo.addons.base.models.access_link import hash_token
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("-at_install", "post_install")
class TestLinkExpirationDate(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.validity_period = 30
        cls.fail_text = "This link is invalid. Please contact the HR Responsible to get a new one..."

        cls.structure_type = cls.env["hr.payroll.structure.type"].create(
            {"name": "struct"}
        )
        cls.job = cls.env["hr.job"].create(
            {
                "name": "Familiar job",
            }
        )
        cls.simple_user = mail_new_test_user(
            cls.env,
            name="Nandor Relentless",
            login="Al Qolnidar",
            email="Nandor@odoo.com",
            groups="base.group_user",
        )
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Nandor", "user_id": cls.simple_user.id}
        )

        cls.offer_refusal_reason = cls.env[
            "hr.contract.salary.offer.refusal.reason"
        ].create(
            {
                "name": "Salary too high",
            }
        )

    def _applicant_offer(self, **values):
        applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Guillermo De La Cruz",
                "email_from": "Guillermo@example.com",
            }
        )
        contract_template = self.env["hr.version"].create(
            {"job_id": self.job.id, "name": "Template Maze Runner Contract"}
        )
        return self.env["hr.contract.salary.offer"].create(
            {
                "applicant_id": applicant.id,
                "contract_template_id": contract_template.id,
                **values,
            }
        )

    def test_an_applicant_s_offer_opens_by_a_link_until_it_expires(self):
        end = datetime.date.today() + relativedelta(days=10)
        offer = self._applicant_offer(offer_end_date=end)
        token = offer.access_token
        link = (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", offer._name), ("res_id", "=", offer.id)])
        )

        self.assertEqual(
            (len(link), link.partner_id, link.role, link.token_hash),
            (1, offer.applicant_id.partner_id, "comment", hash_token(token)),
        )
        self.assertEqual(
            link.date_to, datetime.datetime.combine(end, datetime.time(23, 59, 59))
        )
        self.assertTrue(offer._offer_token_opens(token))
        self.assertFalse(offer._offer_token_opens("x" * 32))

        offer.offer_end_date = end + relativedelta(days=5)
        offer.invalidate_recordset(["access_token"])

        self.assertEqual(offer.access_token, token)
        self.assertEqual(
            link.date_to,
            datetime.datetime.combine(
                end + relativedelta(days=5), datetime.time(23, 59, 59)
            ),
        )

    def test_an_offer_ending_far_ahead_keeps_its_link_until_that_day(self):
        end = datetime.date.today() + relativedelta(years=2)
        offer = self._applicant_offer(offer_end_date=end)
        link = (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", offer._name), ("res_id", "=", offer.id)])
        )
        self.assertEqual(
            link.date_to, datetime.datetime.combine(end, datetime.time(23, 59, 59))
        )

    def test_another_applicant_revokes_the_offer_s_link(self):
        offer = self._applicant_offer()
        token = offer.access_token
        other = self.env["hr.applicant"].create(
            {"partner_name": "Nadja", "email_from": "nadja@example.com"}
        )

        offer.applicant_id = other

        self.assertFalse(offer._offer_token_opens(token))
        self.assertTrue(offer._offer_token_opens(offer.access_token))

    def test_an_offer_to_an_employee_who_signs_in_has_no_link(self):
        self.employee.version_id.write(
            {
                "wage": 6500,
                "structure_type_id": self.structure_type.id,
                "job_id": self.job.id,
            }
        )
        self.employee.version_id.action_generate_offer()

        self.assertFalse(self.employee.version_id.salary_offer_ids.access_token)

    def test_generate_offer_by_hr_user(self):
        hr_user = mail_new_test_user(
            self.env,
            name="HR Officer User",
            login="hr_officer_user",
            groups="hr.group_hr_user,hr_recruitment.group_hr_recruitment_user",
        )
        self.env["hr.version"].create(
            {
                "name": "Contract Template",
                "final_yearly_costs": 6500,
                "job_id": self.job.id,
            }
        )
        applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Guillermo De La Cruz",
                "email_from": "Guillermo@example.com",
            }
        )
        applicant.with_user(hr_user).action_generate_offer()
        self.assertEqual(applicant.salary_offers_count, 1)

    def test_link_for_applicant(self):
        self.env["hr.version"].create(
            {
                "name": "Contract Template",
                "wage": 6500,
                "structure_type_id": self.structure_type.id,
                "job_id": self.job.id,
            }
        )
        applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Guillermo De La Cruz",
                "email_from": "Guillermo@example.com",
            }
        )

        applicant.action_generate_offer()
        offer = applicant.salary_offer_ids
        end = offer.offer_create_date + relativedelta(days=self.validity_period)
        self.assertEqual(offer.offer_end_date, end)
        url = f"/salary_package/simulation/offer/{offer.id}?token={offer.access_token}"
        with freeze_time(end):
            res = self.url_open(url)
        self.assertTrue(
            self.fail_text not in str(res.content),
            "The applicant should not be redirected to the invalid link page",
        )

        with freeze_time(end + relativedelta(days=1)):
            late_res = self.url_open(url)
        self.assertTrue(
            self.fail_text in str(late_res.content),
            "The applicant should be redirected to the invalid link page",
        )

    def test_an_expired_link_refuses_the_configurator_rpc_with_its_message(self):
        self.env["hr.version"].create(
            {
                "name": "Contract Template",
                "wage": 6500,
                "structure_type_id": self.structure_type.id,
                "job_id": self.job.id,
            }
        )
        applicant = self.env["hr.applicant"].create(
            {
                "partner_name": "Guillermo De La Cruz",
                "email_from": "Guillermo@example.com",
            }
        )
        applicant.action_generate_offer()
        offer = applicant.salary_offer_ids

        with freeze_time(offer.offer_end_date + relativedelta(days=1)):
            response = self.url_open(
                "/salary_package/update_salary",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "id": 0,
                    "params": {
                        "offer_id": offer.id,
                        "benefits": {},
                        "token": offer.access_token,
                    },
                },
            )
        error = response.json()["error"]
        self.assertEqual(
            error["data"]["name"],
            "odoo.exceptions.AccessError",
            "a JSON-RPC route refused with an HTML error page the envelope cannot "
            "carry, so the refusal reached the client as a server error",
        )
        self.assertIn(self.fail_text, error["data"]["message"])

    def test_link_for_employee(self):
        self.employee.version_id.write(
            {
                "wage": 6500,
                "structure_type_id": self.structure_type.id,
                "job_id": self.job.id,
            }
        )
        employee_version = self.employee.version_id

        employee_version.action_generate_offer()
        offer = employee_version.salary_offer_ids
        end = offer.offer_create_date + relativedelta(days=self.validity_period)
        self.assertEqual(offer.offer_end_date, end)
        url = f"/salary_package/simulation/offer/{offer.id}"
        with freeze_time(end):
            self.authenticate(self.simple_user.login, self.simple_user.login)
            res = self.url_open(url)
        self.assertTrue(
            self.fail_text not in str(res.content),
            "The Employee should not be redirected to the invalid link page",
        )

        with freeze_time(end + relativedelta(days=1)):
            self.authenticate(self.simple_user.login, self.simple_user.login)
            late_res = self.url_open(url)
        self.assertTrue(
            self.fail_text in str(late_res.content),
            "The Employee should be redirected to the invalid link page",
        )
