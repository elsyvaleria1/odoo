from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import reconcile_with_settlement
from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestPurchaseAccessMatrix(AccessMatrixCase):
    personas = {
        "buyer_a": Persona("purchase.group_purchase_user"),
        "buyer_all_a": Persona("purchase.group_purchase_user_all"),
        "manager_a": Persona("purchase.group_purchase_manager"),
        "reader_a": Persona("purchase.group_purchase_readonly"),
        "employee_a": Persona(),
        "buyer_b": Persona("purchase.group_purchase_user", company="b"),
        "portal_v": Persona(portal="vendor_v"),
        "manager_ab": Persona("purchase.group_purchase_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "purchase.order",
            "order_own",
            buyer_a="rwcd confirm",
            buyer_all_a="rwcd confirm",
            manager_a="rwcd confirm unlock",
            reader_a="r",
            portal_v="r",
            manager_ab="rwcd confirm unlock",
        ),
        Cell(
            "purchase.order",
            "order_other",
            buyer_all_a="rwcd confirm",
            manager_a="rwcd confirm unlock",
            reader_a="r",
            manager_ab="rwcd confirm unlock",
        ),
        Cell(
            "purchase.order",
            "order_unset",
            buyer_a="rwcd confirm",
            buyer_all_a="rwcd confirm",
            manager_a="rwcd confirm unlock",
            reader_a="r",
            manager_ab="rwcd confirm unlock",
        ),
        Cell(
            "purchase.order",
            "order_b",
            buyer_b="rwcd confirm",
            manager_ab="rwcd confirm unlock",
        ),
        Cell(
            "purchase.order.line",
            "line_own",
            buyer_a="rwcd",
            buyer_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            portal_v="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.order.line",
            "line_other",
            buyer_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.report",
            "report_own",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "purchase.report",
            "report_other",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "purchase.bill.match",
            "match_own",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "purchase.bill.match",
            "match_other",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "purchase.bill.line.match",
            "line_match_other",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.move",
            "bill_own",
            buyer_a="rwcd",
            buyer_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            portal_v="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.move",
            "bill_other",
            buyer_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.move",
            "invoice",
        ),
        Cell(
            "account.move.line",
            "bill_own_line",
            buyer_a="rwc",
            buyer_all_a="rwc",
            manager_a="rwcd",
            reader_a="r",
            portal_v="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.move.line",
            "bill_other_line",
            buyer_all_a="rwc",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.move.line",
            "invoice_line",
        ),
        Cell(
            "account.payment",
            "payment",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.partial.reconcile",
            "partial",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.journal",
            "journal_purchase",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="r",
            manager_ab="r",
            installed={"approval_account": {"reader_a": "r", "employee_a": "r"}},
        ),
        Cell(
            "account.analytic.line",
            "analytic_line",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "res.partner",
            "vendor_d",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="rwc",
            reader_a="r",
            employee_a="r",
            buyer_b="r",
            manager_ab="rwc",
        ),
        Cell(
            "product.supplierinfo",
            "supplierinfo",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "product.pricelist.item",
            "pricelist_item",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "srm.tag",
            "tag",
            buyer_a="rwc",
            buyer_all_a="rwc",
            manager_a="rwcd",
            buyer_b="rwc",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.config",
            "config_a",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            manager_ab="r",
        ),
        Cell(
            "loss.reason",
            "loss_reason",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.order.template",
            "rfq_template",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.order.template.line",
            "rfq_template_line",
            buyer_a="r",
            buyer_all_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        users = cls.users
        vendor_v = cls.partners["vendor_v"]
        vendor_d = env["res.partner"].create({"name": "vendor_d"})
        product = env["product.product"].create(
            {"name": "matrix product", "standard_price": 10.0}
        )

        def order(company, user, partner):
            return (
                env["purchase.order"]
                .with_company(company)
                .create(
                    {
                        "partner_id": partner.id,
                        "user_id": user and user.id,
                        "company_id": company.id,
                        "line_ids": [
                            Command.create(
                                {
                                    "product_id": product.id,
                                    "product_qty": 1,
                                    "price_unit": 10.0,
                                }
                            )
                        ],
                    }
                )
            )

        orders = {
            "order_own": order(a, users["buyer_a"], vendor_v),
            "order_other": order(a, users["manager_a"], vendor_d),
            "order_unset": order(a, False, vendor_d),
            "order_b": order(b, users["buyer_b"], vendor_d),
        }

        def move(move_type, user, partner):
            return (
                env["account.move"]
                .with_company(a)
                .create(
                    {
                        "move_type": move_type,
                        "partner_id": partner.id,
                        "invoice_user_id": user.id,
                        "invoice_date": "2026-09-01",
                        "invoice_line_ids": [
                            Command.create(
                                {"product_id": product.id, "price_unit": 10.0}
                            )
                        ],
                    }
                )
            )

        bill_own = move("in_invoice", users["buyer_a"], vendor_v)
        bill_other = move("in_invoice", users["manager_a"], vendor_d)
        invoice = move("out_invoice", users["buyer_a"], vendor_d)
        bill_own.action_post()
        bill_other.action_post()
        payment = (
            env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=bill_own.ids)
            .create({"amount": 5.0})
            ._create_payments()
        )
        partial = bill_own.line_ids.matched_debit_ids[:1] or reconcile_with_settlement(
            bill_own, 5.0
        )
        plan = env["account.analytic.plan"].create({"name": "matrix plan"})
        analytic = env["account.analytic.account"].create(
            {"name": "matrix analytic", "plan_id": plan.id, "company_id": a.id}
        )
        analytic_line = env["account.analytic.line"].create(
            {
                "name": "matrix",
                "account_id": analytic.id,
                "amount": 10.0,
                "company_id": a.id,
            }
        )
        supplierinfo = env["product.supplierinfo"].create(
            {
                "partner_id": vendor_d.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "price": 9.0,
            }
        )
        pricelist = env["product.pricelist"].create(
            {"name": "matrix pricelist", "company_id": a.id}
        )
        pricelist_item = env["product.pricelist.item"].create(
            {"pricelist_id": pricelist.id, "fixed_price": 1.0}
        )
        rfq_template = env["purchase.order.template"].create(
            {
                "name": "matrix rfq template",
                "company_id": a.id,
                "line_ids": [
                    Command.create({"product_id": product.id, "product_qty": 1})
                ],
            }
        )
        report = env["purchase.report"].sudo()
        match = env["purchase.bill.match"].sudo()
        line_match = env["purchase.bill.line.match"].sudo()
        return {
            **orders,
            "line_own": orders["order_own"].line_ids,
            "line_other": orders["order_other"].line_ids,
            "report_own": report.search(
                [("order_reference", "=", f"purchase.order,{orders['order_own'].id}")],
                limit=1,
            ),
            "report_other": report.search(
                [
                    (
                        "order_reference",
                        "=",
                        f"purchase.order,{orders['order_other'].id}",
                    )
                ],
                limit=1,
            ),
            "match_own": match.search([("move_id", "=", bill_own.id)]),
            "match_other": match.search([("move_id", "=", bill_other.id)]),
            "line_match_other": line_match.search(
                [("account_move_id", "=", bill_other.id)], limit=1
            ),
            "bill_own": bill_own,
            "bill_other": bill_other,
            "invoice": invoice,
            "bill_own_line": bill_own.invoice_line_ids,
            "bill_other_line": bill_other.invoice_line_ids,
            "invoice_line": invoice.invoice_line_ids,
            "payment": payment,
            "partial": partial,
            "journal_purchase": bill_own.journal_id,
            "analytic_line": analytic_line,
            "vendor_d": vendor_d,
            "supplierinfo": supplierinfo,
            "pricelist_item": pricelist_item,
            "tag": env["srm.tag"].create({"name": "matrix tag"}),
            "loss_reason": env["loss.reason"].create(
                {
                    "name": "matrix lost purchase",
                    "scope": "purchase",
                    "company_id": a.id,
                }
            ),
            "rfq_template": rfq_template,
            "rfq_template_line": rfq_template.line_ids,
            "config_a": env["purchase.config"].search(
                [("company_id", "=", a.id)], limit=1
            ),
        }
