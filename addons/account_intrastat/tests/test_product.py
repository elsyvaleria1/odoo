from odoo.tests import Form, tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestProduct(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({"name": "A product"})
        cls.intrastat_code = (
            cls.env["account.intrastat.code"]
            .sudo()
            .create(
                {
                    "name": "An Intrastat Code",
                    "type": "commodity",
                    "code": 1,
                    "supplementary_unit": "l",
                }
            )
        )

    def test_changing_intrastat_field_values_on_product(self):
        with Form(self.product) as form:
            form.intrastat_code_id = self.intrastat_code
            form.intrastat_supplementary_unit_amount = 10
            form.intrastat_origin_country_id = self.env.ref("base.nl")

        self.assertRecordValues(
            self.product,
            [
                {
                    "intrastat_code_id": self.intrastat_code.id,
                    "intrastat_supplementary_unit": "l",
                    "intrastat_supplementary_unit_amount": 10,
                    "intrastat_origin_country_id": self.env.ref("base.nl").id,
                }
            ],
        )

    def test_changing_intrastat_field_values_on_product_template(self):
        with Form(self.product.product_tmpl_id) as form:
            form.intrastat_code_id = self.intrastat_code

        with Form(self.product.product_tmpl_id) as form:
            form.intrastat_supplementary_unit_amount = 10
            form.intrastat_origin_country_id = self.env.ref("base.nl")

        self.assertRecordValues(
            self.product,
            [
                {
                    "intrastat_code_id": self.intrastat_code.id,
                    "intrastat_supplementary_unit": "l",
                    "intrastat_supplementary_unit_amount": 10,
                    "intrastat_origin_country_id": self.env.ref("base.nl").id,
                }
            ],
        )
