import datetime

from odoo import Command

from odoo.addons.sale.tests.common import SaleCommon, TestSaleCommon


class UncatchableException(BaseException):
    pass


class SaleSubscriptionCommon(SaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        (
            cls.plan_week,
            cls.plan_month,
            cls.plan_2_month,
            cls.plan_year,
        ) = cls.env["sale.subscription.plan"].create(
            [
                {
                    "name": "Weekly",
                    "repeat_interval": 1,
                    "repeat_unit": "week",
                    "sequence": 1,
                },
                {
                    "name": "Monthly",
                    "repeat_interval": 1,
                    "repeat_unit": "month",
                    "sequence": 4,
                },
                {
                    "name": "2 Months",
                    "repeat_interval": 2,
                    "repeat_unit": "month",
                    "sequence": 8,
                },
                {
                    "name": "Yearly",
                    "repeat_interval": 1,
                    "repeat_unit": "year",
                    "sequence": 52,
                },
            ]
        )

    @classmethod
    def _create_product(cls, **kwargs):
        if "recurring_invoice" not in kwargs:
            kwargs["recurring_invoice"] = True
        return super()._create_product(**kwargs)


class TestSubscriptionCommon(TestSaleCommon):
    def setUp(self):
        super().setUp()

        SO = type(self.env["sale.order"])

        def _subscription_launch_cron_single(self, batch_size):
            self.env["sale.order"]._create_recurring_invoice(batch_size=batch_size)

        self.patch(
            SO, "_subscription_launch_cron_parallel", _subscription_launch_cron_single
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.ref("base.main_company").currency_id = cls.env.ref("base.USD")

        cls.env["res.config.settings"].create(
            {"group_product_pricelist": True}
        ).execute()

        cls.context_no_mail = {
            "no_reset_password": True,
            "mail_create_nosubscribe": True,
            "mail_create_nolog": True,
        }
        AnalyticPlan = cls.env["account.analytic.plan"].with_context(
            cls.context_no_mail
        )
        Analytic = cls.env["account.analytic.account"].with_context(cls.context_no_mail)
        cls.SaleOrder = cls.env["sale.order"].with_context(cls.context_no_mail)
        Tax = cls.env["account.tax"].with_context(cls.context_no_mail)
        cls.ProductTmpl = cls.env["product.template"].with_context(cls.context_no_mail)
        cls.country_belgium = cls.env.ref("base.be")

        cls.account_payable = cls.company_data["default_account_payable"]
        cls.account_receivable = cls.company_data["default_account_receivable"]
        cls.account_income = cls.company_data["default_account_revenue"]
        cls.company_data[
            "company"
        ].account_config_id.deferred_expense_journal_id = cls.company_data[
            "default_journal_misc"
        ].id
        cls.company_data[
            "company"
        ].account_config_id.deferred_revenue_journal_id = cls.company_data[
            "default_journal_misc"
        ].id
        cls.company_data[
            "company"
        ].account_config_id.deferred_expense_account_id = cls.company_data[
            "default_account_deferred_expense"
        ].id
        cls.company_data[
            "company"
        ].account_config_id.deferred_revenue_account_id = cls.company_data[
            "default_account_deferred_revenue"
        ].id

        cls.tax_10 = Tax.create(
            {
                "name": "10% tax",
                "amount_type": "percent",
                "amount": 10,
            }
        )
        cls.tax_20 = Tax.create(
            {
                "name": "20% tax",
                "amount_type": "percent",
                "amount": 20,
            }
        )
        cls.journal = cls.company_data["default_journal_sale"]

        (
            cls.plan_week,
            cls.plan_month,
            cls.plan_2_month,
            cls.plan_year,
        ) = cls.env["sale.subscription.plan"].create(
            [
                {
                    "name": "Weekly",
                    "repeat_interval": 1,
                    "repeat_unit": "week",
                    "sequence": 1,
                },
                {
                    "name": "Monthly",
                    "repeat_interval": 1,
                    "repeat_unit": "month",
                    "sequence": 4,
                },
                {
                    "name": "2 Months",
                    "repeat_interval": 2,
                    "repeat_unit": "month",
                    "sequence": 8,
                },
                {
                    "name": "Yearly",
                    "repeat_interval": 1,
                    "repeat_unit": "year",
                    "sequence": 52,
                },
            ]
        )

        cls.sub_product_tmpl = cls.ProductTmpl.create(
            {
                "name": "BaseTestProduct",
                "type": "service",
                "recurring_invoice": True,
                "uom_id": cls.uom_unit.id,
                "subscription_rule_ids": [
                    Command.create({"plan_id": cls.plan_month.id, "fixed_price": 1}),
                    Command.create({"plan_id": cls.plan_year.id, "fixed_price": 100}),
                ],
            }
        )
        cls.product = cls.sub_product_tmpl.product_variant_id
        cls.product.write(
            {
                "list_price": 50.0,
                "taxes_id": [(6, 0, [cls.tax_10.id])],
                "property_account_income_id": cls.account_income.id,
            }
        )

        cls.product_tmpl_2 = cls.ProductTmpl.create(
            {
                "name": "TestProduct2",
                "type": "service",
                "recurring_invoice": True,
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.product2 = cls.product_tmpl_2.product_variant_id
        cls.product2.write(
            {
                "list_price": 20.0,
                "taxes_id": [(6, 0, [cls.tax_10.id])],
                "property_account_income_id": cls.account_income.id,
            }
        )

        cls.product_tmpl_3 = cls.ProductTmpl.create(
            {
                "name": "TestProduct3",
                "type": "service",
                "recurring_invoice": True,
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.product3 = cls.product_tmpl_3.product_variant_id
        cls.product3.write(
            {
                "list_price": 15.0,
                "taxes_id": [(6, 0, [cls.tax_10.id])],
                "property_account_income_id": cls.account_income.id,
            }
        )

        cls.product_tmpl_4 = cls.ProductTmpl.create(
            {
                "name": "TestProduct4",
                "type": "service",
                "recurring_invoice": True,
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.product4 = cls.product_tmpl_4.product_variant_id
        cls.product4.write(
            {
                "list_price": 15.0,
                "taxes_id": [(6, 0, [cls.tax_20.id])],
                "property_account_income_id": cls.account_income.id,
            }
        )
        cls.product_tmpl_5 = cls.ProductTmpl.create(
            {
                "name": "One shot product",
                "type": "service",
                "recurring_invoice": False,
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.product5 = cls.product_tmpl_3.product_variant_id
        cls.product5.write(
            {
                "list_price": 42.0,
                "taxes_id": [(6, 0, [cls.tax_10.id])],
                "property_account_income_id": cls.account_income.id,
            }
        )
        cls.subscription_tmpl = cls.env["sale.order.template"].create(
            {
                "name": "Subscription template without discount",
                "is_unlimited": False,
                "duration_value": 2,
                "duration_unit": "year",
                "note": "This is the template description",
                "plan_id": cls.plan_month.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Product 1",
                            "product_id": cls.product.id,
                            "product_qty": 1,
                            "product_uom_id": cls.product.uom_id.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Product 2",
                            "product_id": cls.product2.id,
                            "product_qty": 1,
                            "product_uom_id": cls.product2.uom_id.id,
                        }
                    ),
                ],
            }
        )
        cls.templ_5_days = cls.env["sale.order.template"].create(
            {
                "name": "Template 2 days",
                "is_unlimited": False,
                "note": "This is the template description",
                "duration_value": 4,
                "duration_unit": "year",
                "plan_id": cls.plan_year.copy(default={"auto_close_limit": 5}).id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": cls.product.name,
                            "product_id": cls.product.id,
                            "product_qty": 3.0,
                            "product_uom_id": cls.product.uom_id.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": cls.product2.name,
                            "product_id": cls.product2.id,
                            "product_qty": 2.0,
                            "product_uom_id": cls.product2.uom_id.id,
                        },
                    ),
                ],
            }
        )
        cls.templ_60_days = cls.templ_5_days.copy()
        cls.templ_60_days.plan_id = cls.plan_year.copy(default={"auto_close_limit": 60})

        TestUsersEnv = cls.env["res.users"].with_context({"no_reset_password": True})
        group_portal_id = cls.env.ref("base.group_portal").id
        group_sale_salesman = cls.env.ref("sale.group_sale_salesman")
        cls.country_belgium = cls.env.ref("base.be")
        cls.user_portal = TestUsersEnv.create(
            {
                "name": "Beatrice Portal",
                "login": "Beatrice",
                "country_id": cls.country_belgium.id,
                "email": "beatrice.employee@example.com",
                "group_ids": [(6, 0, [group_portal_id])],
                "property_account_payable_id": cls.account_payable.id,
                "property_account_receivable_id": cls.account_receivable.id,
                "company_id": cls.company_data["company"].id,
            }
        )

        cls.malicious_user = TestUsersEnv.create(
            {
                "name": "Al Capone",
                "login": "al",
                "password": "alalalal",
                "email": "al@capone.it",
                "group_ids": [(6, 0, [group_portal_id])],
                "property_account_receivable_id": cls.account_receivable.id,
                "property_account_payable_id": cls.account_receivable.id,
            }
        )
        cls.legit_user = TestUsersEnv.create(
            {
                "name": "Eliot Ness",
                "login": "ness",
                "password": "nessnessness",
                "email": "ness@USDT.us",
                "group_ids": [(6, 0, [group_portal_id])],
                "property_account_receivable_id": cls.account_receivable.id,
                "property_account_payable_id": cls.account_receivable.id,
            }
        )
        cls.sale_user = TestUsersEnv.create(
            {
                "name": "Test Salesman",
                "login": "salesman",
                "password": "salesman",
                "email": "default_user_salesman@example.com",
                "group_ids": [Command.set(group_sale_salesman.ids)],
            }
        )

        cls.plan_1 = AnalyticPlan.create(
            {
                "name": "Test Plan 1",
            }
        )
        cls.account_1 = Analytic.create(
            {
                "partner_id": cls.user_portal.partner_id.id,
                "name": "Test Account 1",
                "plan_id": cls.plan_1.id,
            }
        )
        cls.account_2 = Analytic.create(
            {
                "partner_id": cls.user_portal.partner_id.id,
                "name": "Test Account 2",
                "plan_id": cls.plan_1.id,
            }
        )

        cls.subscription = cls.SaleOrder.create(
            {
                "name": "TestSubscription",
                "is_subscription": True,
                "plan_id": cls.plan_month.id,
                "notes": "original subscription description",
                "partner_id": cls.user_portal.partner_id.id,
                "template_id": cls.subscription_tmpl.id,
                "require_signature": False,
            }
        )
        cls.subscription._onchange_template_id()
        cls.subscription.start_date = False
        cls.subscription.end_date = False
        cls.company = cls.env.company
        cls.company.country_id = cls.env.ref("base.us")
        cls.account_receivable = cls.env["account.account"].create(
            {
                "name": "Ian Anderson",
                "code": "IA",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        cls.account_sale = cls.env["account.account"].create(
            {
                "name": "Product Sales ",
                "code": "S200000",
                "account_type": "income",
                "reconcile": False,
            }
        )

        cls.sale_journal = cls.env["account.journal"].create(
            {
                "name": "reflets.info",
                "code": "ref",
                "type": "sale",
                "company_id": cls.company.id,
                "default_account_id": cls.account_sale.id,
            }
        )
        belgium = cls.env.ref("base.be")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Stevie Nicks",
                "email": "sti@fleetwood.mac",
                "country_id": belgium.id,
                "property_account_receivable_id": cls.account_receivable.id,
                "property_account_payable_id": cls.account_receivable.id,
                "company_id": cls.company.id,
            }
        )
        cls.provider = cls.env["payment.provider"].create(
            {
                "name": "The Wire",
                "company_id": cls.company.id,
                "state": "test",
                "redirect_form_view_id": cls.env["ir.ui.view"]
                .search([("type", "=", "qweb")], limit=1)
                .id,
            }
        )
        cls.payment_method_id = cls.env.ref("payment.payment_method_unknown").id
        cls.payment_token = (
            cls.env["payment.token"]
            .sudo()
            .create(
                {
                    "payment_details": "Jimmy McNulty",
                    "partner_id": cls.partner.id,
                    "provider_id": cls.provider.id,
                    "payment_method_id": cls.payment_method_id,
                    "provider_ref": "Omar Little",
                }
            )
        )
        Partner = cls.env["res.partner"]
        cls.partner_a_invoice = Partner.create(
            {
                "parent_id": cls.partner_a.id,
                "type": "invoice",
            }
        )
        cls.partner_a_shipping = Partner.create(
            {
                "parent_id": cls.partner_a.id,
                "type": "delivery",
            }
        )

    @staticmethod
    def _get_optional_product_lines(order):
        return order.line_ids.filtered(
            lambda line: not line.display_type and line._is_line_optional(),
        )

    @classmethod
    def get_default_groups(cls):
        groups = super().get_default_groups()
        return groups | cls.env.ref("sale.group_sale_manager")

    def _mock_subscription_do_payment(self, payment_token, invoice, auto_commit=False):
        tx_obj = self.env["payment.transaction"]
        refs = invoice.invoice_line_ids.sale_line_ids.order_id.mapped(
            "client_order_ref"
        )
        ref_vals = [r for r in refs if r]
        reference = "CONTRACT-%s-%s-%s" % (
            invoice.id,
            "".join(ref_vals),
            datetime.datetime.now().strftime("%y%m%d_%H%M%S%f"),
        )
        provider = invoice.env.context.get("test_provider", self.provider)
        values = [
            {
                "amount": invoice.amount_total,
                "provider_id": provider.id,
                "payment_method_id": self.payment_method_id,
                "operation": "offline",
                "currency_id": invoice.currency_id.id,
                "reference": reference,
                "token_id": payment_token.id,
                "partner_id": invoice.partner_id.id,
                "partner_country_id": invoice.partner_id.country_id.id,
                "sale_order_ids": [
                    (6, 0, invoice.invoice_line_ids.sale_line_ids.order_id.ids)
                ],
                "invoice_ids": [(6, 0, [invoice.id])],
                "state": "done",
                "subscription_action": "automatic_send_mail",
            }
        ]
        return tx_obj.create(values)

    def _mock_subscription_do_payment_rejected(
        self, payment_method, invoice, auto_commit=False
    ):
        tx = self._mock_subscription_do_payment(payment_method, invoice)
        tx.state = "pending"
        tx._set_error("Payment declined")
        tx._post_process()
        tx.env.cr.flush()
        return tx

    def _mock_subscription_do_payment_pending(
        self, payment_method, invoice, auto_commit=False
    ):
        tx = self._mock_subscription_do_payment(payment_method, invoice)
        tx.state = "pending"
        tx.env.cr.flush()
        return tx

    def _mock_prepare_invoice_data(self):
        invoice = self.original_prepare_invoice()
        invoice["bank_account_id"] = False
        return invoice

    def _mock_subscription_process_invoice_to_send(self, account_moves):
        subscription_id = account_moves.line_ids.subscription_id
        if self.crashing_sub_id in subscription_id.ids:
            raise UncatchableException("I want to break free")

    def flush_tracking(self):
        self.env.flush_all()
        self.cr.flush()

    def _get_quantities(self, order_line):
        order_line = order_line.sorted("id")
        order_line.invalidate_recordset(
            fnames=["qty_transferred", "qty_invoiced", "qty_to_invoice"]
        )
        order_line._compute_invoice_amounts()
        order_line._compute_qty_transferred()
        return {
            "ordered": order_line.mapped("product_qty"),
            "delivered": order_line.mapped("qty_transferred"),
            "invoiced": order_line.mapped("qty_invoiced"),
            "to_invoice": order_line.mapped("qty_to_invoice"),
            "qty_delivered_method": order_line.mapped("qty_transferred_method"),
        }

    @classmethod
    def _create_product(cls, **kwargs):
        if "recurring_invoice" not in kwargs:
            kwargs["recurring_invoice"] = True
        return super()._create_product(**kwargs)
