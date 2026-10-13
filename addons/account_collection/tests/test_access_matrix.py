from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OWN = "a collector prepares and hands in only their own remittances"
PRIVILEGED = (
    "a collector books their collection's entry and reconciles it only through "
    "account_collection.privilege_register_collection, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestAccountCollectionAccessMatrix(AccessMatrixCase):
    personas = {
        "collector_a": Persona("account_collection.group_collection_collector"),
        "other_collector_a": Persona("account_collection.group_collection_collector"),
        "invoice_a": Persona("account.group_account_invoice"),
        "manager_a": Persona("account.group_account_manager"),
        "readonly_a": Persona("account.group_account_readonly"),
        "invoice_b": Persona("account.group_account_invoice", company="b"),
        "employee_a": Persona(),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "account.collection.remittance",
            "remittance_a",
            note=OWN,
            collector_a="rwc submit reopen cancel",
            invoice_a="rwc submit reopen validate cancel",
            manager_a="rwcd submit reopen validate cancel",
            readonly_a="r",
        ),
        Cell(
            "account.collection.custody.report",
            "custody_report_a",
            note="a collector reads how long they have held their own collections",
            collector_a="r",
            invoice_a="r",
            manager_a="r",
            readonly_a="r",
        ),
        Cell(
            "account.payment",
            "payment_a",
            note="a collector reads what they collected, never another's collections",
            collector_a="r",
            invoice_a="rwcd",
            manager_a="rwcd",
            readonly_a="r",
        ),
        Cell(
            "account.journal",
            "custody_journal",
            note="a collector reads the tills and bank accounts they hand money in to",
            installed={"approval_account": {"employee_a": "r"}},
            collector_a="r",
            other_collector_a="r",
            invoice_a="r",
            manager_a="rwcd",
            readonly_a="r",
        ),
        Cell(
            "account.payment.channel",
            "custody_channel",
            note=PRIVILEGED,
            collector_a="r",
            other_collector_a="r",
            invoice_a="rwcd",
            manager_a="rwcd",
            readonly_a="r",
            employee_a="r",
        ),
        Cell(
            "account.move",
            "payment_move_a",
            note=PRIVILEGED,
            invoice_a="rwcd post",
            manager_a="rwcd post",
            readonly_a="r",
        ),
        Cell(
            "account.move.line",
            "custody_line_a",
            note=PRIVILEGED,
            invoice_a="rwcd",
            manager_a="rwcd",
            readonly_a="r",
        ),
        Cell(
            "account.partial.reconcile",
            "partial_a",
            note=PRIVILEGED,
            invoice_a="rwcd",
            manager_a="rwcd",
            readonly_a="r",
        ),
        Cell(
            "account.full.reconcile",
            "full_a",
            note=PRIVILEGED,
            invoice_a="rwcd",
            manager_a="rwcd",
            readonly_a="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a = cls.companies["a"]
        collector = cls.users["collector_a"]
        env["account.chart.template"].try_loading("generic_coa", company=a)
        sale_journal = env["account.journal"].search(
            [
                *env["account.journal"]._get_domain_company_compatible(a),
                ("type", "=", "sale"),
            ],
            limit=1,
        ) or env["account.journal"].with_company(a).create(
            {"name": "matrix sales", "code": "MXSL", "type": "sale"}
        )
        custody_account = env["account.account"].create(
            {
                "name": "matrix custody",
                "code": "101997",
                "account_type": "asset_current",
                "reconcile": True,
                "company_ids": [Command.set(a.ids)],
            }
        )
        journal = (
            env["account.journal"]
            .with_company(a)
            .create({"name": "matrix custody", "code": "MXCU", "type": "cash"})
        )
        journal.inbound_payment_channel_ids.payment_account_id = custody_account
        journal.is_collection_custody = True
        receivable = env["account.account"].create(
            {
                "name": "matrix receivable",
                "code": "105997",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.set(a.ids)],
            }
        )
        income = env["account.account"].create(
            {
                "name": "matrix income",
                "code": "401997",
                "account_type": "income",
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
        invoice = (
            env["account.move"]
            .with_company(a)
            .create(
                {
                    "move_type": "out_invoice",
                    "journal_id": sale_journal.id,
                    "partner_id": customer.id,
                    "invoice_date": "2026-09-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "matrix",
                                "account_id": income.id,
                                "price_unit": 10.0,
                                "tax_ids": False,
                            }
                        )
                    ],
                }
            )
        )
        invoice.action_post()
        payment = (
            invoice.with_user(collector)
            .with_privilege(
                "account_collection.privilege_register_collection",
                reason="the matrix collector records a collection",
            )
            ._create_collection_payment(
                10.0, invoice.invoice_date, "cash", collector, journal
            )
            .sudo()
        )
        custody_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == custody_account
        )
        partial = invoice.line_ids.matched_credit_ids[:1]
        remittance = (
            env["account.collection.remittance"].with_user(collector).create({})
        )
        return {
            "remittance_a": remittance.sudo(),
            "custody_report_a": env["account.collection.custody.report"].browse(
                payment.id
            ),
            "payment_a": payment,
            "custody_journal": journal,
            "custody_channel": journal.inbound_payment_channel_ids[:1],
            "payment_move_a": payment.move_id,
            "custody_line_a": custody_line,
            "partial_a": partial,
            "full_a": partial.full_reconcile_id,
        }
