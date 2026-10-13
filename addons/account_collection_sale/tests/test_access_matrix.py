from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

PRIVILEGED = (
    "a collector posts the invoice of their cash sale only through "
    "account_collection_sale.privilege_invoice_cash_sale, which no user holds"
)

HANDED_OVER = (
    "a collector hands over the goods of their cash sale only through "
    "account_collection_sale.privilege_hand_over_cash_sale, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestAccountCollectionSaleAccessMatrix(AccessMatrixCase):
    personas = {
        "collector_a": Persona("account_collection.group_collection_collector"),
        "seller_a": Persona(
            "sale.group_sale_salesman",
            "account_collection.group_collection_collector",
        ),
        "invoice_a": Persona("account.group_account_invoice"),
        "manager_a": Persona("account.group_account_manager"),
        "employee_a": Persona(),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "payment.transaction",
            "transaction_a",
            note=PRIVILEGED,
            invoice_a="rwc",
            manager_a="rwc",
        ),
        Cell(
            "account.move",
            "invoice_a",
            note=PRIVILEGED,
            seller_a="r",
            invoice_a="rwcd post",
            manager_a="rwcd post",
        ),
        Cell(
            "account.move.line",
            "invoice_line_a",
            note=PRIVILEGED,
            seller_a="r",
            invoice_a="rwcd",
            manager_a="rwcd",
        ),
        Cell(
            "stock.picking",
            "delivery_a",
            note=HANDED_OVER,
            installed={"marin": {"seller_a": "-wc -validate"}},
            seller_a="rwc validate",
            invoice_a="rwc validate",
            manager_a="rwc validate",
        ),
        Cell(
            "stock.move",
            "delivery_move_a",
            note=HANDED_OVER,
            installed={"marin": {"seller_a": "-wc"}},
            seller_a="rwc",
            invoice_a="rwc",
            manager_a="rwc",
        ),
        Cell(
            "stock.move.line",
            "delivery_move_line_a",
            note=HANDED_OVER,
            collector_a="r",
            seller_a="r",
            invoice_a="r",
            manager_a="r",
            employee_a="r",
        ),
        Cell(
            "wizard.sale.order.cash.collect",
            "wizard_a",
            note="a collector opens the cash-sale dialog; the privilege does the rest",
            collector_a="rwcd",
            seller_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a = cls.companies["a"]
        env["account.chart.template"].try_loading("generic_coa", company=a)
        sale_journal = env["account.journal"].search(
            [
                *env["account.journal"]._get_domain_company_compatible(a),
                ("type", "=", "sale"),
            ],
            limit=1,
        ) or env["account.journal"].with_company(a).create(
            {"name": "matrix sales", "code": "MXSA", "type": "sale"}
        )
        receivable = env["account.account"].create(
            {
                "name": "matrix receivable",
                "code": "105996",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.set(a.ids)],
            }
        )
        customer = (
            env["res.partner"]
            .with_company(a)
            .create(
                {
                    "name": "matrix customer",
                    "property_account_receivable_id": receivable.id,
                }
            )
        )
        income = env["account.account"].create(
            {
                "name": "matrix income",
                "code": "401996",
                "account_type": "income",
                "company_ids": [Command.set(a.ids)],
            }
        )
        product = (
            env["product.product"]
            .with_company(a)
            .create(
                {
                    "name": "matrix product",
                    "list_price": 10.0,
                    "taxes_id": False,
                    "property_account_income_id": income.id,
                }
            )
        )
        order = (
            env["sale.order"]
            .with_company(a)
            .create(
                {
                    "partner_id": customer.id,
                    "user_id": cls.users["seller_a"].id,
                    "payment_term_id": env.ref(
                        "payment_term.account_payment_term_immediate"
                    ).id,
                    "line_ids": [Command.create({"product_id": product.id})],
                }
            )
        )
        order.action_confirm()
        delivery = order.picking_ids[:1]
        delivery.action_assign()
        invoice = order._create_invoices(final=True).with_env(env)
        invoice.journal_id = sale_journal
        wizard = (
            env["wizard.sale.order.cash.collect"]
            .with_user(cls.users["seller_a"])
            .create({"order_id": order.id})
        )
        unknown = env.ref("payment.payment_method_unknown")
        provider = env["payment.provider"].create(
            {
                "name": "matrix provider",
                "code": "none",
                "state": "test",
                "company_id": a.id,
                "payment_method_ids": [Command.set(unknown.ids)],
            }
        )
        unknown.active = True
        transaction = env["payment.transaction"].create(
            {
                "provider_id": provider.id,
                "payment_method_id": unknown.id,
                "amount": invoice.amount_total,
                "currency_id": invoice.currency_id.id,
                "partner_id": customer.id,
                "reference": "matrix transaction",
                "invoice_ids": [Command.set(invoice.ids)],
            }
        )
        return {
            "transaction_a": transaction,
            "invoice_a": invoice,
            "invoice_line_a": invoice.invoice_line_ids[:1],
            "wizard_a": wizard.sudo(),
            "delivery_a": delivery,
            "delivery_move_a": delivery.move_ids[:1],
            "delivery_move_line_a": delivery.move_line_ids[:1],
        }
