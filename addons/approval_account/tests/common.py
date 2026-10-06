from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class AccountApprovalCommon(AccountTestInvoicingCommon):
    chart_template = "generic_coa"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("approval.group_approval_manager")
        shipped = cls.env.ref(
            "approval_account.approval_category_account_move"
        ) | cls.env.ref("approval_account.approval_category_accounting_request")
        cls.env["approval.category"].search(
            [("approval_type", "=", "accounting"), ("id", "not in", shipped.ids)]
        ).active = False
        cls.account_revenue = cls.company_data["default_account_revenue"]
        cls.account_expense = cls.company_data["default_account_expense"]
        cls.account_receivable = cls.company_data["default_account_receivable"]
        cls.account_payable = cls.company_data["default_account_payable"]
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver",
                "login": "approver",
                "email": "approver@test.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("account.group_account_manager").id,
                            cls.env.ref("base.group_user").id,
                        ],
                    ),
                ],
            },
        )
