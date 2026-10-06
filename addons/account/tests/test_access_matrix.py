from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import reconcile_with_settlement
from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestAccountAccessMatrix(AccessMatrixCase):
    personas = {
        "billing_a": Persona("account.group_account_invoice"),
        "basic_a": Persona("account.group_account_basic"),
        "accountant_a": Persona("account.group_account_user"),
        "manager_a": Persona("account.group_account_manager"),
        "reader_a": Persona("account.group_account_readonly"),
        "employee_a": Persona(),
        "billing_b": Persona("account.group_account_invoice", company="b"),
        "portal_c": Persona(portal="customer_c"),
        "manager_ab": Persona("account.group_account_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "account.move",
            "invoice_c",
            billing_a="rwcd post",
            basic_a="rwcd post",
            accountant_a="rwcd post",
            manager_a="rwcd post",
            reader_a="r",
            portal_c="r",
            manager_ab="rwcd post",
        ),
        Cell(
            "account.move",
            "invoice_draft",
            billing_a="rwcd post",
            basic_a="rwcd post",
            accountant_a="rwcd post",
            manager_a="rwcd post",
            reader_a="r",
            manager_ab="rwcd post",
        ),
        Cell(
            "account.move",
            "bill",
            billing_a="rwcd post",
            basic_a="rwcd post",
            accountant_a="rwcd post",
            manager_a="rwcd post",
            reader_a="r",
            manager_ab="rwcd post",
        ),
        Cell(
            "account.move",
            "invoice_b",
            billing_b="rwcd post",
            manager_ab="rwcd post",
        ),
        Cell(
            "account.move.line",
            "invoice_c_line",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.move.line",
            "invoice_b_line",
            billing_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "account.payment",
            "payment",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.partial.reconcile",
            "partial",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.full.reconcile",
            "full",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.invoice.report",
            "invoice_report",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.move.match",
            "move_match",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="r",
            reader_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.account",
            "account",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.account.tag",
            "account_tag",
            billing_a="r",
            basic_a="r",
            accountant_a="rwcd",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            manager_ab="r",
            installed={"accountant": {"manager_a": "wcd", "manager_ab": "wcd"}},
        ),
        Cell(
            "account.group",
            "account_group",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.root",
            "account_root",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            manager_ab="r",
        ),
        Cell(
            "account.code.mapping",
            "code_mapping",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rw",
            reader_a="r",
            employee_a="r",
            manager_ab="rw",
        ),
        Cell(
            "account.analytic.account",
            "analytic",
            billing_a="r",
            basic_a="r",
            accountant_a="rwcd",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            manager_ab="r",
            installed={"accountant": {"manager_a": "wcd", "manager_ab": "wcd"}},
        ),
        Cell(
            "account.analytic.plan",
            "analytic_plan",
            accountant_a="rwcd",
            installed={"accountant": {"manager_a": "rwcd", "manager_ab": "rwcd"}},
        ),
        Cell(
            "account.analytic.applicability",
            "analytic_applicability",
            accountant_a="rwcd",
            installed={"accountant": {"manager_a": "rwcd", "manager_ab": "rwcd"}},
        ),
        Cell(
            "account.analytic.distribution.model",
            "analytic_distribution_model",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.analytic.line",
            "analytic_line",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.audit.account.status",
            "audit_status",
            billing_a="r",
            basic_a="r",
            accountant_a="rwc",
            manager_a="rwc",
            reader_a="r",
            manager_ab="rwc",
        ),
        Cell(
            "account.bank.statement",
            "statement",
            billing_a="r",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.bank.statement.line",
            "statement_line",
            billing_a="r",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.cash.rounding",
            "cash_rounding",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            billing_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "account.config",
            "config_a",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "tax.config",
            "tax_config_a",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.fiscal.position",
            "fiscal_position",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
            installed={"website_sale": {"portal_c": "r"}},
        ),
        Cell(
            "account.fiscal.position.account",
            "fiscal_position_account",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.fiscal.year",
            "fiscal_year",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.incoterms",
            "incoterm",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.journal",
            "journal_sale",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
            installed={"approval_account": {"employee_a": "r"}},
        ),
        Cell(
            "account.journal.group",
            "journal_group",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.lock_exception",
            "lock_exception",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rc",
            reader_a="r",
            employee_a="r",
            manager_ab="rc",
        ),
        Cell(
            "account.payment.channel",
            "payment_channel",
            billing_a="rwcd",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.payment.method",
            "payment_method",
            billing_a="rwd",
            basic_a="rwd",
            accountant_a="rwd",
            manager_a="rwd",
            reader_a="r",
            employee_a="r",
            billing_b="rwd",
            manager_ab="rwd",
        ),
        Cell(
            "account.payment.term",
            "payment_term",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.payment.term.line",
            "payment_term_line",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.reconcile.model",
            "reconcile_model",
            billing_a="rc",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.reconcile.model.line",
            "reconcile_model_line",
            billing_a="rc",
            basic_a="rwcd",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.report.annotation",
            "report_annotation",
            billing_a="r",
            basic_a="r",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.report.budget",
            "budget",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.report.budget.item",
            "budget_item",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.report.horizontal.group",
            "horizontal_group",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.report.horizontal.group.rule",
            "horizontal_group_rule",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.return",
            "return",
            billing_a="r",
            basic_a="r",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.return.check",
            "return_check",
            billing_a="r",
            basic_a="r",
            accountant_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.return.check.template",
            "return_check_template",
            accountant_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "account.return.type",
            "return_type",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.tax.unit",
            "tax_unit",
            note="a tax unit is read in each of its companies",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.tax",
            "tax",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.tax.group",
            "tax_group",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "account.tax.repartition.line",
            "tax_repartition_line",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "report.formula",
            "report_formula",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "report.formula.line",
            "report_formula_line",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "report.formula.column",
            "report_formula_column",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "report.formula.expression",
            "report_formula_expression",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            billing_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "report.formula.external.value",
            "report_formula_external_value",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "res.currency",
            "currency",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "res.currency.rate",
            "currency_rate",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="rwcd",
            reader_a="r",
            employee_a="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "res.partner.bank.account",
            "bank_account",
            billing_a="r",
            basic_a="r",
            accountant_a="r",
            manager_a="r",
            reader_a="r",
            employee_a="r",
            billing_b="r",
            manager_ab="r",
        ),
        Cell(
            "res.users.grant",
            "deductibility_grant",
            employee_a="r",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        env["account.chart.template"].try_loading("generic_coa", company=b)
        customer_c = cls.partners["customer_c"]
        customer_d = env["res.partner"].create({"name": "customer_d"})
        product = env["product.product"].create(
            {"name": "matrix product", "list_price": 10.0}
        )

        def move(company, move_type, partner, post=True, **values):
            record = (
                env["account.move"]
                .with_company(company)
                .create(
                    {
                        "move_type": move_type,
                        "partner_id": partner.id,
                        "invoice_date": "2026-09-01",
                        "invoice_line_ids": [
                            Command.create(
                                {"product_id": product.id, "price_unit": 10.0}
                            )
                        ],
                        **values,
                    }
                )
            )
            if post:
                record.action_post()
            return record

        invoice_c = move(a, "out_invoice", customer_c)
        invoice_draft = move(a, "out_invoice", customer_d, post=False)
        bill = move(a, "in_invoice", customer_d)
        invoice_b = move(b, "out_invoice", customer_d)
        paid = move(a, "out_invoice", customer_d)
        payment = (
            env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=paid.ids)
            .create({})
            ._create_payments()
        )
        partial = paid.line_ids.matched_credit_ids[:1] or reconcile_with_settlement(
            paid, paid.amount_total
        )

        def one(model, domain=()):
            found = (
                env[model].with_context(active_test=False).search(list(domain), limit=1)
            )
            assert found, f"the chart holds no {model}"
            return found

        company_a = [("company_id", "=", a.id)]
        account = one("account.account", [("company_ids", "in", a.ids)])
        account_other = env["account.account"].search(
            [("company_ids", "in", a.ids), ("id", "!=", account.id)], limit=1
        )
        journal_bank = one("account.journal", [*company_a, ("type", "=", "bank")])
        plan = env["account.analytic.plan"].create({"name": "matrix plan"})
        analytic = env["account.analytic.account"].create(
            {"name": "matrix analytic", "plan_id": plan.id, "company_id": a.id}
        )
        statement_line = env["account.bank.statement.line"].create(
            {
                "journal_id": journal_bank.id,
                "amount": 10.0,
                "payment_ref": "matrix",
                "date": "2026-09-01",
            }
        )
        statement = env["account.bank.statement"].create(
            {"name": "matrix", "line_ids": [Command.set(statement_line.ids)]}
        )
        fiscal_position = env["account.fiscal.position"].create(
            {"name": "matrix position", "company_id": a.id}
        )
        return_type = env["account.return.type"].create({"name": "matrix return"})
        account_return = env["account.return"].create(
            {
                "name": "matrix return",
                "date_from": "2026-01-01",
                "date_to": "2026-03-31",
                "type_id": return_type.id,
                "company_id": a.id,
            }
        )
        horizontal = env["account.report.horizontal.group"].create(
            {
                "name": "matrix horizontal",
                "rule_ids": [Command.create({"field_name": "partner_id"})],
            }
        )
        budget = env["account.report.budget"].create(
            {"name": "matrix budget", "company_id": a.id}
        )
        report = env["report.formula"].create({"name": "matrix report"})
        report_line = env["report.formula.line"].create(
            {"name": "matrix line", "report_id": report.id, "hierarchy_level": 1}
        )
        expression = env["report.formula.expression"].create(
            {
                "report_line_id": report_line.id,
                "label": "balance",
                "engine": "external",
                "formula": "sum",
            }
        )
        term = one("account.payment.term")
        reconcile_model = env["account.reconcile.model"].create(
            {
                "name": "matrix model",
                "company_id": a.id,
                "line_ids": [Command.create({"account_id": account.id})],
            }
        )
        grant_group = env.ref("account.group_partial_purchase_deductibility")
        return {
            "invoice_c": invoice_c,
            "invoice_draft": invoice_draft,
            "bill": bill,
            "invoice_b": invoice_b,
            "invoice_c_line": invoice_c.invoice_line_ids,
            "invoice_b_line": invoice_b.invoice_line_ids,
            "payment": payment,
            "partial": partial,
            "full": paid.line_ids.full_reconcile_id,
            "invoice_report": env["account.invoice.report"]
            .sudo()
            .search([("move_id", "=", invoice_c.id)], limit=1),
            "move_match": env["account.move.match"]
            .sudo()
            .search([("move_id", "=", invoice_c.id)], limit=1),
            "account": account,
            "account_tag": one("account.account.tag"),
            "account_group": env["account.group"].create(
                {"name": "matrix group", "code_prefix_start": "99", "company_id": a.id}
            ),
            "account_root": one("account.root"),
            "code_mapping": env["account.code.mapping"].search(
                [("account_id", "in", account.ids)], limit=1
            ),
            "analytic": analytic,
            "analytic_plan": plan,
            "analytic_applicability": env["account.analytic.applicability"].create(
                {
                    "business_domain": "general",
                    "applicability": "optional",
                    "analytic_plan_id": plan.id,
                }
            ),
            "analytic_distribution_model": env[
                "account.analytic.distribution.model"
            ].create({"analytic_distribution": {str(analytic.id): 100}}),
            "analytic_line": env["account.analytic.line"].create(
                {"name": "matrix", "account_id": analytic.id, "company_id": a.id}
            ),
            "audit_status": env["account.audit.account.status"].create(
                {"audit_id": account_return.id, "account_id": account.id}
            ),
            "statement": statement,
            "statement_line": statement_line,
            "cash_rounding": env["account.cash.rounding"].create(
                {"name": "matrix rounding", "rounding": 0.05}
            ),
            "config_a": env["account.config"].search(company_a, limit=1),
            "tax_config_a": env["tax.config"].search(company_a, limit=1),
            "fiscal_position": fiscal_position,
            "fiscal_position_account": env["account.fiscal.position.account"].create(
                {
                    "position_id": fiscal_position.id,
                    "account_src_id": account.id,
                    "account_dest_id": account_other.id,
                }
            ),
            "fiscal_year": env["account.fiscal.year"].create(
                {
                    "name": "matrix year",
                    "date_from": "2025-01-01",
                    "date_to": "2025-12-31",
                    "company_id": a.id,
                }
            ),
            "incoterm": one("account.incoterms"),
            "journal_sale": invoice_c.journal_id,
            "journal_group": env["account.journal.group"].create(
                {"name": "matrix ledger", "company_id": a.id}
            ),
            "lock_exception": env["account.lock_exception"].create(
                {
                    "sale_lock_date": "2024-01-01",
                    "company_id": a.id,
                    "user_id": cls.users["billing_a"].id,
                    "end_datetime": fields.Datetime.now(),
                }
            ),
            "payment_channel": one(
                "account.payment.channel", [("journal_id.company_id", "=", a.id)]
            ),
            "payment_method": one("account.payment.method"),
            "payment_term": term,
            "payment_term_line": term.line_ids[:1],
            "reconcile_model": reconcile_model,
            "reconcile_model_line": reconcile_model.line_ids,
            "report_annotation": env["account.report.annotation"].create(
                {
                    "message_id": invoice_c.message_ids[:1].id,
                    "date": "2026-09-01",
                }
            ),
            "budget": budget,
            "budget_item": env["account.report.budget.item"].create(
                {"budget_id": budget.id, "account_id": account.id, "date": "2026-09-01"}
            ),
            "horizontal_group": horizontal,
            "horizontal_group_rule": horizontal.rule_ids,
            "return": account_return,
            "return_check": env["account.return.check"].create(
                {"code": "matrix", "name": "matrix", "return_id": account_return.id}
            ),
            "return_check_template": env["account.return.check.template"].create(
                {"name": "matrix", "return_type": return_type.id}
            ),
            "return_type": return_type,
            "tax_unit": env["account.tax.unit"].create(
                {
                    "name": "matrix unit",
                    "country_id": a.country_id.id or env.ref("base.us").id,
                    "vat": "MATRIX-VAT",
                    "company_ids": [Command.set([a.id, b.id])],
                    "main_company_id": a.id,
                }
            ),
            "tax": one("account.tax", [("company_ids", "in", a.ids)]),
            "tax_group": one("account.tax.group"),
            "tax_repartition_line": one(
                "account.tax.repartition.line",
                [("tax_id.company_ids", "in", a.ids)],
            ),
            "report_formula": report,
            "report_formula_line": report_line,
            "report_formula_column": env["report.formula.column"].create(
                {
                    "name": "Balance",
                    "expression_label": "balance",
                    "report_id": report.id,
                }
            ),
            "report_formula_expression": expression,
            "report_formula_external_value": env[
                "report.formula.external.value"
            ].create(
                {
                    "name": "matrix",
                    "date": "2026-09-01",
                    "target_report_expression_id": expression.id,
                    "company_id": a.id,
                }
            ),
            "currency": a.currency_id,
            "currency_rate": env["res.currency.rate"].create(
                {"currency_id": a.currency_id.id, "rate": 1.0, "name": "2020-01-01"}
            ),
            "bank_account": env["res.partner.bank.account"].create(
                {"acc_number": "MATRIX-1", "partner_id": customer_d.id}
            ),
            "deductibility_grant": env["res.users.grant"].create(
                {"user_id": cls.users["employee_a"].id, "group_id": grant_group.id}
            ),
        }
