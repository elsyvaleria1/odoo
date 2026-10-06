from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import reconcile_with_settlement
from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestSaleAccessMatrix(AccessMatrixCase):
    personas = {
        "salesman_a": Persona("sale.group_sale_salesman"),
        "team_a": Persona("sale.group_sale_salesman_team"),
        "all_leads_a": Persona("sale.group_sale_salesman_all_leads"),
        "manager_a": Persona("sale.group_sale_manager"),
        "reader_a": Persona("sale.group_sale_readonly"),
        "employee_a": Persona(),
        "salesman_b": Persona("sale.group_sale_salesman", company="b"),
        "portal_c": Persona(portal="customer_c"),
        "manager_ab": Persona("sale.group_sale_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "sale.order",
            "order_own",
            salesman_a="rwc confirm",
            all_leads_a="rwc confirm",
            manager_a="rwcd confirm",
            reader_a="r",
            portal_c="r",
            manager_ab="rwcd confirm",
        ),
        Cell(
            "sale.order",
            "order_other",
            all_leads_a="rwc confirm",
            manager_a="rwcd confirm",
            reader_a="r",
            manager_ab="rwcd confirm",
        ),
        Cell(
            "sale.order",
            "order_unset",
            note="an order without a salesperson is every salesperson's",
            salesman_a="rwc confirm",
            team_a="rwc confirm",
            all_leads_a="rwc confirm",
            manager_a="rwcd confirm",
            reader_a="r",
            manager_ab="rwcd confirm",
        ),
        Cell(
            "sale.order",
            "order_b",
            salesman_b="rwc confirm",
            manager_ab="rwcd confirm",
        ),
        Cell(
            "sale.order.line",
            "line_own",
            salesman_a="rwcd",
            all_leads_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "sale.order.line",
            "line_other",
            all_leads_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "sale.report",
            "report_own",
            salesman_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "sale.report",
            "report_other",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "sale.invoice.match",
            "match_own",
            salesman_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "sale.invoice.match",
            "match_other",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "sale.invoice.line.match",
            "line_match_other",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.move",
            "invoice_own",
            salesman_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            portal_c="r",
            manager_ab="r",
        ),
        Cell(
            "account.move",
            "invoice_other",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell("account.move", "bill", note="a vendor bill is no salesperson's"),
        Cell(
            "account.move.line",
            "invoice_own_line",
            salesman_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            portal_c="r",
            manager_ab="r",
        ),
        Cell("account.move.line", "bill_line"),
        Cell(
            "account.payment",
            "payment",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.partial.reconcile",
            "partial",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.journal",
            "journal_sale",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="r",
            manager_ab="r",
            installed={"approval_account": {"reader_a": "r", "employee_a": "r"}},
        ),
        Cell(
            "account.analytic.account",
            "analytic",
            salesman_a="rwc",
            team_a="rwc",
            all_leads_a="rwc",
            manager_a="rwc",
            reader_a="r",
            employee_a="r",
            manager_ab="rwc",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan_sale",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            salesman_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan_partner",
            note="a sales manager manages the plans of orders only",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            salesman_b="r",
            manager_ab="r",
        ),
        Cell(
            "mail.activity.plan.template",
            "activity_plan_template",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            salesman_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "mail.activity.type",
            "activity_type",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            salesman_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "payment.token",
            "token",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="r",
            manager_ab="r",
        ),
        Cell(
            "product.attribute.custom.value",
            "custom_value",
            note="the custom value an order line of company A carries",
            salesman_a="rwcd",
            team_a="rwcd",
            all_leads_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
            installed={"website_sale": {"portal_c": "r"}},
        ),
        Cell(
            "res.partner",
            "customer_d",
            note="crm lets a salesperson create and edit the customers of their leads",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwc",
            reader_a="r",
            employee_a="r",
            salesman_b="r",
            manager_ab="rwc",
            installed={
                "crm": {
                    "salesman_a": "wc",
                    "team_a": "wc",
                    "all_leads_a": "wc",
                    "salesman_b": "wc",
                }
            },
        ),
        Cell(
            "product.pricelist",
            "pricelist",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "product.pricelist.item",
            "pricelist_item",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "sale.config",
            "config_a",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            manager_ab="r",
        ),
        Cell(
            "sale.order.template",
            "quotation_template",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "sale.order.template.line",
            "quotation_template_line",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "loss.reason",
            "loss_reason",
            salesman_a="r",
            team_a="r",
            all_leads_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        users = cls.users
        customer_c = cls.partners["customer_c"]
        customer_d = env["res.partner"].create({"name": "customer_d"})
        product = env["product.product"].create(
            {"name": "matrix product", "list_price": 10.0}
        )

        def order(name, company, user, partner):
            return (
                env["sale.order"]
                .with_company(company)
                .create(
                    {
                        "partner_id": partner.id,
                        "user_id": user and user.id,
                        "company_id": company.id,
                        "line_ids": [
                            Command.create({"product_id": product.id, "product_qty": 1})
                        ],
                    }
                )
            )

        orders = {
            "order_own": order("own", a, users["salesman_a"], customer_c),
            "order_other": order("other", a, users["manager_a"], customer_d),
            "order_unset": order("unset", a, False, customer_d),
            "order_b": order("b", b, users["salesman_b"], customer_d),
        }

        def invoice(move_type, user, partner):
            return (
                env["account.move"]
                .with_company(a)
                .create(
                    {
                        "move_type": move_type,
                        "partner_id": partner.id,
                        "invoice_user_id": user.id,
                        "invoice_line_ids": [
                            Command.create(
                                {"product_id": product.id, "price_unit": 10.0}
                            )
                        ],
                    }
                )
            )

        invoice_own = invoice("out_invoice", users["salesman_a"], customer_c)
        invoice_other = invoice("out_invoice", users["manager_a"], customer_d)
        bill = invoice("in_invoice", users["manager_a"], customer_d)
        invoice_own.action_post()
        invoice_other.action_post()
        payment = (
            env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=invoice_own.ids)
            .create({"amount": 5.0})
            ._create_payments()
        )
        partial = invoice_own.line_ids.matched_credit_ids[
            :1
        ] or reconcile_with_settlement(invoice_own, 5.0)

        plan = env["account.analytic.plan"].create({"name": "matrix plan"})
        analytic = env["account.analytic.account"].create(
            {"name": "matrix analytic", "plan_id": plan.id, "company_id": a.id}
        )
        activity_plan = env["mail.activity.plan"].create(
            {"name": "matrix sale plan", "res_model": "sale.order"}
        )
        activity_plan_other = env["mail.activity.plan"].create(
            {"name": "matrix partner plan", "res_model": "res.partner"}
        )
        activity_type = env["mail.activity.type"].create(
            {"name": "matrix type", "res_model": "sale.order"}
        )
        plan_template = env["mail.activity.plan.template"].create(
            {
                "plan_id": activity_plan.id,
                "activity_type_id": activity_type.id,
                "summary": "matrix",
            }
        )
        provider = env["payment.provider"].create(
            {"name": "matrix provider", "company_id": a.id}
        )
        method = (
            env["payment.method"].with_context(active_test=False).search([], limit=1)
        )
        token = env["payment.token"].create(
            {
                "provider_id": provider.id,
                "payment_method_id": method.id,
                "partner_id": customer_d.id,
                "provider_ref": "matrix",
            }
        )
        attribute = env["product.attribute"].create(
            {
                "name": "matrix attribute",
                "value_ids": [Command.create({"name": "custom", "is_custom": True})],
            }
        )
        template = product.product_tmpl_id
        template.attribute_line_ids = [
            Command.create(
                {"attribute_id": attribute.id, "value_ids": attribute.value_ids.ids}
            )
        ]
        custom_value = env["product.attribute.custom.value"].create(
            {
                "custom_product_template_attribute_value_id": template.attribute_line_ids.product_template_value_ids[
                    :1
                ].id,
                "sale_order_line_id": orders["order_own"].line_ids.id,
                "custom_value": "matrix",
            }
        )
        pricelist = env["product.pricelist"].create(
            {"name": "matrix pricelist", "company_id": a.id}
        )
        pricelist_item = env["product.pricelist.item"].create(
            {"pricelist_id": pricelist.id, "fixed_price": 1.0}
        )
        quotation_template = env["sale.order.template"].create(
            {
                "name": "matrix template",
                "company_id": a.id,
                "line_ids": [
                    Command.create({"product_id": product.id, "product_qty": 1})
                ],
            }
        )
        report = env["sale.report"].sudo()
        match = env["sale.invoice.match"].sudo()
        line_match = env["sale.invoice.line.match"].sudo()
        return {
            **orders,
            "line_own": orders["order_own"].line_ids,
            "line_other": orders["order_other"].line_ids,
            "report_own": report.search(
                [("order_reference", "=", f"sale.order,{orders['order_own'].id}")],
                limit=1,
            ),
            "report_other": report.search(
                [("order_reference", "=", f"sale.order,{orders['order_other'].id}")],
                limit=1,
            ),
            "match_own": match.search([("move_id", "=", invoice_own.id)]),
            "match_other": match.search([("move_id", "=", invoice_other.id)]),
            "line_match_other": line_match.search(
                [("account_move_id", "=", invoice_other.id)], limit=1
            ),
            "invoice_own": invoice_own,
            "invoice_other": invoice_other,
            "bill": bill,
            "invoice_own_line": invoice_own.invoice_line_ids,
            "bill_line": bill.invoice_line_ids,
            "payment": payment,
            "partial": partial,
            "journal_sale": invoice_own.journal_id,
            "analytic": analytic,
            "activity_plan_sale": activity_plan,
            "activity_plan_partner": activity_plan_other,
            "activity_plan_template": plan_template,
            "activity_type": activity_type,
            "token": token,
            "custom_value": custom_value,
            "customer_d": customer_d,
            "pricelist": pricelist,
            "pricelist_item": pricelist_item,
            "config_a": env["sale.config"].search([("company_id", "=", a.id)], limit=1),
            "quotation_template": quotation_template,
            "loss_reason": env["loss.reason"].create(
                {"name": "matrix lost sale", "scope": "sale", "company_id": a.id}
            ),
            "quotation_template_line": quotation_template.line_ids,
        }
