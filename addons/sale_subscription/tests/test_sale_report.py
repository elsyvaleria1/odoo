from odoo import Command, fields
from odoo.tests import freeze_time, tagged

from odoo.addons.sale_subscription.tests.common_sale_subscription import (
    TestSubscriptionCommon,
)


@tagged("-at_install", "post_install")
class TestSaleReport(TestSubscriptionCommon):
    def setUp(self):
        super().setUp()
        self.recurring_product_tmp, self.no_recurring_product_tmpl = self.env[
            "product.template"
        ].create(
            [
                {
                    "name": "Product A",
                    "type": "service",
                    "list_price": 100,
                    "taxes_id": [Command.set(self.tax_10.ids)],
                    "recurring_invoice": True,
                    "uom_id": self.env.ref("base.product_uom_unit").id,
                },
                {
                    "name": "Product B",
                    "type": "consu",
                    "list_price": 100,
                    "taxes_id": [Command.set(self.tax_10.ids)],
                    "recurring_invoice": False,
                    "uom_id": self.env.ref("base.product_uom_unit").id,
                },
            ]
        )
        self.recurring_product, self.no_recurring_product = (
            self.recurring_product_tmp | self.no_recurring_product_tmpl
        ).product_variant_id
        self.original_subscription = self.env["sale.order"].create(
            {
                "name": "Test subscription",
                "is_subscription": True,
                "notes": "Subscription description",
                "partner_id": self.user_portal.partner_id.id,
                "plan_id": self.plan_month.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": self.recurring_product.name,
                            "product_id": self.recurring_product.id,
                            "product_qty": 2.0,
                            "price_unit": self.recurring_product.list_price,
                        }
                    )
                ],
            }
        )
        self.original_subscription.action_confirm()
        self.env["sale.order"]._cron_recurring_create_invoice()

    def test_report_no_confirm_upsell(self):
        action = self.original_subscription.prepare_upsell_order()
        upsell_sub = self.env["sale.order"].browse(action["res_id"])
        self.env.flush_all()

        report_lines = self.env["sale.report"].search(
            [("name", "in", [self.original_subscription.name, upsell_sub.name])]
        )
        self.assertEqual(len(report_lines), 1)
        self.assertEqual(report_lines.product_id, self.recurring_product)
        self.assertEqual(report_lines.product_uom_qty, 2)

    def test_report_confirm_upsell(self):
        action = self.original_subscription.prepare_upsell_order()
        upsell_sub = self.env["sale.order"].browse(action["res_id"])
        upsell_sub.action_confirm()
        self.env.flush_all()

        report_lines = self.env["sale.report"].search(
            [("name", "in", [self.original_subscription.name, upsell_sub.name])]
        )
        self.assertEqual(len(report_lines), 1)
        self.assertEqual(report_lines.product_id, self.recurring_product)
        self.assertEqual(report_lines.product_uom_qty, 2)

    def test_report_confirm_upsell_with_same_product(self):
        action = self.original_subscription.prepare_upsell_order()
        upsell_sub = self.env["sale.order"].browse(action["res_id"])
        upsell_sub.line_ids = [
            Command.create(
                {
                    "name": self.recurring_product.name,
                    "product_id": self.recurring_product.id,
                    "product_qty": 1.0,
                    "price_unit": self.recurring_product.list_price,
                }
            )
        ]
        upsell_sub.action_confirm()
        self.env.flush_all()

        report_lines = self.env["sale.report"].search(
            [("name", "in", [self.original_subscription.name, upsell_sub.name])]
        )
        self.assertEqual(len(report_lines), 1)
        self.assertEqual(report_lines.product_id, self.recurring_product)
        self.assertEqual(report_lines.product_uom_qty, 3)
        self.assertEqual(report_lines.price_subtotal, 300)

    def test_report_confirm_upsell_with_other_product(self):
        action = self.original_subscription.prepare_upsell_order()
        upsell_sub = self.env["sale.order"].browse(action["res_id"])
        upsell_sub.line_ids = [
            Command.create(
                {
                    "name": self.no_recurring_product.name,
                    "product_id": self.no_recurring_product.id,
                    "product_qty": 5.0,
                    "price_unit": self.no_recurring_product.list_price,
                }
            )
        ]
        upsell_sub.action_confirm()
        self.env.flush_all()

        report_lines = self.env["sale.report"].search(
            [("name", "in", [self.original_subscription.name, upsell_sub.name])]
        )
        self.assertEqual(len(report_lines), 2)
        recurring_line = report_lines.filtered(
            lambda l: l.product_id == self.recurring_product
        )
        self.assertEqual(recurring_line.product_uom_qty, 2)
        self.assertEqual(recurring_line.price_subtotal, 200)
        no_recurring_line = report_lines.filtered(
            lambda l: l.product_id == self.no_recurring_product
        )
        self.assertEqual(no_recurring_line.product_uom_qty, 5)

    def test_report_confirm_upsell_with_same_product_and_discount(self):
        with freeze_time("2024-08-30 02:01:00 UTC"):
            action = self.original_subscription.prepare_upsell_order()
            upsell_sub = self.env["sale.order"].browse(action["res_id"])
            upsell_sub.line_ids = [
                Command.create(
                    {
                        "name": self.recurring_product.name,
                        "product_id": self.recurring_product.id,
                        "product_qty": 1.0,
                        "price_unit": self.recurring_product.list_price,
                        "discount": 30,
                    }
                )
            ]
            upsell_sub.action_confirm()
            self.env.flush_all()

            report_lines = self.env["sale.report"].search(
                [("name", "in", [self.original_subscription.name, upsell_sub.name])]
            )
            self.assertEqual(len(report_lines), 1)
            self.assertEqual(report_lines.product_id, self.recurring_product)
            self.assertEqual(report_lines.product_uom_qty, 3)
            self.assertEqual(report_lines.price_subtotal, 300)
            self.assertEqual(
                upsell_sub.line_ids.filtered("discount").price_subtotal, 70
            )
            # Note: on the Sales report, it is normal to lose the discount given in the upsell.

    def _create_expansion_log(self, order):
        self.env["sale.order.log"].sudo().create(
            {
                "event_type": "1_expansion",
                "event_date": fields.Date.today(),
                "order_id": order.id,
                "recurring_monthly": 80,
                "amount_signed": 80,
                "subscription_state": order.subscription_state,
            }
        )
        self.env.flush_all()
        return [("order_id", "=", order.id), ("event_type", "=", "1_expansion")]

    def test_log_report_reads_as_salesman(self):
        domain = self._create_expansion_log(self.original_subscription)
        log_report = self.env["sale.order.log.report"].with_user(self.sale_user)

        rows = log_report.search_read(domain, ["amount_signed", "log_currency_id"])
        groups = log_report.formatted_read_group(
            domain, ["event_type"], ["amount_signed:sum", "__count"]
        )

        self.assertEqual(
            [(row["amount_signed"], row["log_currency_id"][0]) for row in rows],
            [(80.0, self.original_subscription.currency_id.id)],
        )
        self.assertEqual(
            [
                (group["event_type"], group["amount_signed:sum"], group["__count"])
                for group in groups
            ],
            [("1_expansion", 80.0, 1)],
        )

    def test_log_report_ignores_another_companys_rates(self):
        other_company = self.env.ref("base.main_company")
        self.assertNotEqual(other_company, self.env.company)
        self.env["res.currency.rate"].sudo().create(
            {
                "currency_id": self.original_subscription.currency_id.id,
                "company_id": other_company.id,
                "name": "2020-01-01",
                "rate": 4.0,
            }
        )
        domain = self._create_expansion_log(self.original_subscription)

        rows = (
            self.env["sale.order.log.report"]
            .with_user(self.sale_user)
            .search_read(domain, ["amount_signed", "mrr_change_normalized"])
        )

        self.assertEqual(
            [(row["amount_signed"], row["mrr_change_normalized"]) for row in rows],
            [(80.0, 80.0)],
        )

    def _create_eur_subscription(self, rates):
        eur = self._enable_currency("EUR")
        self.env["res.currency.rate"].sudo().search(
            [("currency_id", "=", eur.id)]
        ).unlink()
        self.env["res.currency.rate"].create(
            [
                {
                    "currency_id": eur.id,
                    "company_id": company.id,
                    "name": date,
                    "rate": rate,
                }
                for company, date, rate in rates
            ]
        )
        return eur, self.env["sale.order"].create(
            {
                "is_subscription": True,
                "partner_id": self.user_portal.partner_id.id,
                "plan_id": self.plan_month.id,
                "pricelist_id": self.env["product.pricelist"]
                .create({"name": "EUR", "currency_id": eur.id})
                .id,
            }
        )

    def test_log_report_keeps_an_archived_currency(self):
        eur, subscription = self._create_eur_subscription(
            [(self.env.company, "2020-01-01", 2.0)]
        )
        domain = self._create_expansion_log(subscription)
        eur.action_archive()

        rows = (
            self.env["sale.order.log.report"]
            .with_user(self.sale_user)
            .search_read(
                domain,
                ["amount_signed", "log_currency_id", "mrr_change_normalized"],
            )
        )

        self.assertEqual(
            [
                (
                    row["amount_signed"],
                    row["log_currency_id"][0],
                    row["mrr_change_normalized"],
                )
                for row in rows
            ],
            [(80.0, eur.id, 40.0)],
        )

    def _read_normalized_mrr(self, subscription):
        rows = (
            self.env["sale.order.log.report"]
            .with_user(self.sale_user)
            .search_read(
                self._create_expansion_log(subscription), ["mrr_change_normalized"]
            )
        )
        return [row["mrr_change_normalized"] for row in rows]

    def test_log_report_prefers_its_company_rate_over_a_newer_shared_one(self):
        _eur, subscription = self._create_eur_subscription(
            [
                (self.env.company, "2020-01-01", 4.0),
                (self.env["res.company"], "2021-01-01", 2.0),
            ]
        )

        self.assertEqual(self._read_normalized_mrr(subscription), [20.0])

    def test_log_report_takes_the_earliest_rate_before_the_first_one(self):
        _eur, subscription = self._create_eur_subscription(
            [
                (self.env.company, "2098-01-01", 4.0),
                (self.env.company, "2099-01-01", 2.0),
            ]
        )

        self.assertEqual(self._read_normalized_mrr(subscription), [20.0])
