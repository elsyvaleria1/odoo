from datetime import date
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import tests
from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests import Form
from odoo.tests.common import TransactionCase, new_test_user


@tests.tagged("post_install", "-at_install")
class TestRuleParameter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rule_parameter = cls.env["hr.rule.parameter"].create(
            {
                "name": "Test Parameter",
                "code": "test_param",
            }
        )

        values = [
            {
                "rule_parameter_id": cls.rule_parameter.id,
                "parameter_value": str(year),
                "date_from": date(year, 1, 1),
            }
            for year in [2016, 2017, 2018, 2020]
        ]
        cls.env["hr.rule.parameter.value"].create(values)

    @patch.object(Date, "today", lambda: date(2019, 10, 10))
    def test_get_last_version(self):
        value = self.env["hr.rule.parameter"]._get_parameter_from_code("test_param")
        self.assertEqual(value, 2018, "It should get last valid value")

    def test_get_middle_version(self):
        value = self.env["hr.rule.parameter"]._get_parameter_from_code(
            "test_param", date=date(2017, 5, 5)
        )
        self.assertEqual(value, 2017, "It should get the 2017 version")

    def test_get_unexisting_version(self):
        with self.assertRaises(UserError):
            self.env["hr.rule.parameter"]._get_parameter_from_code(
                "test_param", date=date(2014, 5, 5)
            )

    def test_wrong_code(self):
        with self.assertRaises(UserError):
            self.env["hr.rule.parameter"]._get_parameter_from_code("wrong_code")

    def test_multicompany(self):

        be = self.env.ref("base.be")
        fr = self.env.ref("base.fr")
        company_1 = self.env["res.company"].create(
            {"name": "Table", "country_id": be.id}
        )
        company_2 = self.env["res.company"].create(
            {"name": "Tableau", "country_id": fr.id}
        )
        user = new_test_user(
            self.env,
            login="bub",
            groups="hr.group_hr_user",
            company_id=company_2.id,
            company_ids=[(6, 0, (company_1 + company_2).ids)],
        )

        rule_parameter = self.env["hr.rule.parameter"].create(
            {
                "name": "Test Parameter",
                "code": "test_parameter",
                "country_id": be.id,
            }
        )
        self.env["hr.rule.parameter.value"].create(
            {
                "rule_parameter_id": rule_parameter.id,
                "date_from": date(2015, 10, 10),
                "parameter_value": 100,
            }
        )

        with self.assertRaises(UserError):
            self.env["hr.rule.parameter"].with_user(user).with_company(
                company_2
            )._get_parameter_from_code("test_parameter")

        be_value = (
            self.env["hr.rule.parameter"]
            .with_user(user)
            .with_company(company_1)
            ._get_parameter_from_code("test_parameter")
        )
        self.assertEqual(be_value, 100)

        with self.assertRaises(UserError):
            self.env["hr.rule.parameter"].with_user(user).with_company(
                company_2
            )._get_parameter_from_code("test_parameter")

    def test_future_rule_parameter(self):
        with Form(self.env["hr.rule.parameter"]) as rule:
            rule.name = "Test Future Parameter"
            rule.code = "test_future_param"
            with rule.parameter_version_ids.new() as rule_value:
                rule_value.parameter_value = "2"
                rule_value.date_from = date.today() + relativedelta(months=2)
        new_rule = rule.save()
        self.assertTrue(new_rule.exists())

    def test_duplicate_rule_parameter(self):
        copy = self.rule_parameter.copy()
        self.assertTrue(copy.exists())
        self.assertEqual(copy.code, "test_param_copy")
        self.assertEqual(copy.name, "Test Parameter (copy)")

    def test_duplicate_rule_parameter_honours_explicit_code(self):
        copy = self.rule_parameter.copy({"code": "chosen_code"})
        self.assertEqual(copy.code, "chosen_code")

    def test_parameter_value_update_is_logged_on_the_parameter(self):
        value = self.rule_parameter.parameter_version_ids.filtered(
            lambda v: v.date_from == date(2016, 1, 1)
        )
        messages_before = len(self.rule_parameter.message_ids)

        value.parameter_value = "2016.5"

        messages = self.rule_parameter.message_ids
        self.assertEqual(len(messages) - messages_before, 1)
        body = messages[0].body
        self.assertIn("2016", body)
        self.assertIn("2016.5", body)

    def test_parameter_date_from_update_is_logged_on_the_parameter(self):
        value = self.rule_parameter.parameter_version_ids.filtered(
            lambda v: v.date_from == date(2017, 1, 1)
        )
        messages_before = len(self.rule_parameter.message_ids)

        value.date_from = date(2017, 7, 1)

        messages = self.rule_parameter.message_ids
        self.assertEqual(len(messages) - messages_before, 1)
        self.assertIn("2017-07-01", messages[0].body)

    def test_parameter_value_update_logs_every_record_of_a_batch(self):
        values = self.rule_parameter.parameter_version_ids
        self.assertGreater(len(values), 1)
        messages_before = len(self.rule_parameter.message_ids)

        values.write({"parameter_value": "9999"})

        self.assertEqual(
            len(self.rule_parameter.message_ids) - messages_before, len(values)
        )

    def test_parameter_value_rewritten_to_the_same_value_logs_nothing(self):
        value = self.rule_parameter.parameter_version_ids.filtered(
            lambda v: v.date_from == date(2018, 1, 1)
        )
        messages_before = len(self.rule_parameter.message_ids)

        value.write({"parameter_value": "2018"})

        self.assertEqual(len(self.rule_parameter.message_ids), messages_before)
