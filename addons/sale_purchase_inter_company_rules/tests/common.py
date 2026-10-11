from odoo import Command

from odoo.addons.account_inter_company_rules.tests.common import (
    TestInterCompanyRulesCommon,
)


class TestInterCompanyRulesCommonSOPO(TestInterCompanyRulesCommon):
    @classmethod
    def get_default_groups(cls):
        groups = super().get_default_groups()
        return groups | cls.quick_ref("sale.group_sale_manager")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.user.group_ids += cls.env.ref("sale.group_discount_per_so_line")
        cls.env.user.group_ids += cls.env.ref("base.group_uom")

        cls.res_users_company_a.group_ids += (
            cls.env.ref("sale.group_sale_salesman")
            + cls.env.ref("purchase.group_purchase_user")
            + cls.env.ref("sale.group_discount_per_so_line")
        )
        cls.res_users_company_b.group_ids += (
            cls.env.ref("sale.group_sale_salesman")
            + cls.env.ref("purchase.group_purchase_user")
            + cls.env.ref("sale.group_discount_per_so_line")
        )

        (cls.company_a + cls.company_b).write({"country_id": cls.env.ref("base.us").id})
        cls.fp_a = cls.env["account.fiscal.position"].create(
            {
                "name": f"Fiscal Position {cls.company_a.name}",
                "auto_apply": True,
                "country_id": cls.env.ref("base.us").id,
                "company_id": cls.company_a.id,
            }
        )

        cls.fp_b = cls.env["account.fiscal.position"].create(
            {
                "name": f"Fiscal Position {cls.company_b.name}",
                "auto_apply": True,
                "country_id": cls.env.ref("base.us").id,
                "company_id": cls.company_b.id,
            }
        )

        (
            cls.company_a.tax_config_id.account_sale_tax_id
            | cls.company_a.tax_config_id.account_purchase_tax_id
        ).fiscal_position_ids = [Command.link(cls.fp_a.id)]
        (
            cls.company_b.tax_config_id.account_sale_tax_id
            | cls.company_b.tax_config_id.account_purchase_tax_id
        ).fiscal_position_ids = [Command.link(cls.fp_b.id)]

    @classmethod
    def _create_unprivileged_user(cls, login, company):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "email": f"{login}@example.com",
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
