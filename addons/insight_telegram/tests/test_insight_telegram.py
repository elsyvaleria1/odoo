import contextlib
import io
from datetime import date
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from psycopg import errors as pg_errors

from odoo import Command, fields
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged

from odoo.addons.insight_telegram.models.telegram_chat import (
    CHUNK_LIMIT,
    _chunks,
    _decision,
)
from odoo.addons.insight_telegram.services import catalog, documents, files, write_ops
from odoo.addons.insight_telegram.services.insight_agent import InsightAgent
from odoo.addons.insight_telegram.services.insight_assistant import (
    InsightAssistant,
    _schema,
)
from odoo.addons.insight_telegram.services.odoo_reader import OdooReader
from odoo.addons.insight_telegram.services.odoo_tools import OdooTools
from odoo.addons.telegram.tests.common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestOdooReader(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader_user = cls.env.ref("insight_telegram.user_reader")
        cls.probe = cls.env["res.partner"].create({"name": "Ask Probe Partner"})

    def setUp(self):
        super().setUp()
        # in test mode the reader's cursors share the test transaction, the
        # read-only ones under a read-only savepoint
        self.reader = OdooReader(self.registry, self.reader_user.id)

    def test_the_reader_sees_every_company_as_superuser(self):
        self.assertFalse(self.reader_user.active, "the reader never logs in")
        with self.reader.env() as env:
            self.assertTrue(env.su)
            self.assertEqual(env.companies, env["res.company"].search([]))
            self.assertTrue(env["res.partner"].browse(self.probe.id).exists())

    def test_the_reader_cannot_write(self):
        with self.assertRaises(pg_errors.ReadOnlySqlTransaction):
            with self.reader.env() as env:
                env["res.partner"].browse(self.probe.id).write({"name": "Changed"})
                env.flush_all()
        self.probe.invalidate_recordset(["name"])
        self.assertEqual(self.probe.name, "Ask Probe Partner")

    def test_a_long_report_is_cut(self):
        with self.reader.env() as env:
            env.cr.execute("SHOW statement_timeout")
            self.assertEqual(env.cr.fetchone()[0], "20s")


def _tiny_pdf() -> bytes:
    """A one-page PDF any reader opens: a document's page count is read on save."""
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=3, height=3)
    writer.write(buffer)
    return buffer.getvalue()


TINY_PDF = _tiny_pdf()


def _call(reader, name, **arguments):
    return json_loads(reader.call(name, arguments))


@tagged("post_install", "-at_install")
class TestOdooTools(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader_user = cls.env.ref("insight_telegram.user_reader")
        cls.probe = cls.env["res.partner"].create(
            {"name": "Ask Probe Partner", "is_company": True}
        )

    def setUp(self):
        super().setUp()
        # the reader opens its own cursors: in test mode they share the test
        # transaction, read-only ones under a read-only savepoint
        self.reader = OdooTools(OdooReader(self.registry, self.reader_user.id))

    def test_search_reads_what_the_reader_user_could_not(self):
        self.assertFalse(self.reader_user.active, "the reader never logs in")
        rows = _call(
            self.reader,
            "search_records",
            model="res.partner",
            domain=[["name", "=", "Ask Probe Partner"]],
            fields=["name", "is_company"],
        )["records"]
        self.assertEqual(
            rows,
            [{"id": self.probe.id, "name": "Ask Probe Partner", "is_company": True}],
        )

    def test_count_and_aggregate(self):
        domain = [["name", "=", "Ask Probe Partner"]]
        self.assertEqual(
            _call(self.reader, "count_records", model="res.partner", domain=domain),
            {"count": 1},
        )
        groups = _call(
            self.reader,
            "aggregate_records",
            model="res.partner",
            domain=domain,
            groupby=["is_company"],
            aggregates=["__count"],
        )["groups"]
        self.assertEqual(groups, [{"is_company": True, "__count": 1}])

    def test_find_and_describe_models(self):
        models = _call(self.reader, "find_models", query="res.partner")["models"]
        self.assertIn("res.partner", [row["model"] for row in models])
        described = _call(self.reader, "describe_model", model="res.partner")["fields"]
        self.assertEqual(described["name"]["type"], "char")
        self.assertNotIn("image_1920", described, "binaries are never offered")

    def test_secret_models_are_refused(self):
        for model in (
            "ir.config_parameter",
            "res.users.apikeys",
            "credential.credential",
        ):
            with self.subTest(model=model):
                result = _call(self.reader, "count_records", model=model)
                self.assertIn("secrets", result["error"])
        found = _call(self.reader, "find_models", query="config_parameter")["models"]
        self.assertNotIn("ir.config_parameter", [row["model"] for row in found])

    def test_a_hidden_field_cannot_be_probed_through_a_filter(self):
        # a filter, an order or a grouping on a secret answers yes/no about
        # its value: each is refused like a read would be
        probes = [
            {"domain": [["credential_id.name", "=like", "a%"]]},
            {"domain": [["credential_id", "any", [["name", "=", "x"]]]]},
            {"order": "credential_id desc"},
        ]
        for probe in probes:
            with self.subTest(probe=probe):
                result = _call(
                    self.reader,
                    "search_records",
                    model="telegram.bot",
                    fields=["name"],
                    **probe,
                )
                self.assertIn("cannot be used here", result["error"])
        result = _call(
            self.reader,
            "aggregate_records",
            model="telegram.bot",
            groupby=["credential_id"],
            aggregates=["__count"],
        )
        self.assertIn("cannot be used here", result["error"])

    def test_mistakes_come_back_as_errors_the_model_can_read(self):
        result = _call(
            self.reader, "search_records", model="res.partner", fields=["no_such_field"]
        )
        self.assertIn("no_such_field", result["error"])
        result = _call(self.reader, "count_records", model="no.such.model")
        self.assertIn("find_models", result["error"])
        result = _call(self.reader, "drop_table", model="res.partner")
        self.assertIn("Unknown tool", result["error"])


@tagged("post_install", "-at_install")
class TestCatalog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = date.today()
        cls.reader = OdooReader(
            cls.registry, cls.env.ref("insight_telegram.user_reader").id
        )

    def _answer(self, key, **params):
        queries = catalog.available_queries(self.env)
        if key not in queries:
            self.skipTest(f"the {key} report needs a module not installed here")
        # the reader reads the database, not this environment's pending writes
        self.env.flush_all()
        with self.reader.env() as env:
            return catalog.answer(
                env, queries[key], params, tz="America/Mexico_City", today=self.today
            )

    def _confirmed_order(self, partner, amount):
        product = self.env["product.product"].create(
            {"name": "Ask Probe Product", "list_price": amount}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 1,
                            "price_unit": amount,
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        return order

    def test_sales_add_up_confirmed_orders_only(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        customer = self.env["res.partner"].create({"name": "Ask Probe Customer"})
        order = self._confirmed_order(customer, 1234.5)
        self.assertEqual(order.state, "done")
        self.env["sale.order"].create({"partner_id": customer.id})  # a quotation
        text = self._answer("sales", partner="Ask Probe Customer")
        self.assertIn("**$1,234.50", text)
        self.assertIn("(1 documents)", text)

    def test_sales_by_customer_rank_the_largest_first(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        small = self.env["res.partner"].create({"name": "Ask Probe Small"})
        large = self.env["res.partner"].create({"name": "Ask Probe Large"})
        self._confirmed_order(small, 10)
        self._confirmed_order(large, 900)
        text = self._answer("sales", partner="Ask Probe", group_by="partner")
        self.assertLess(text.index("Ask Probe Large"), text.index("Ask Probe Small"))
        self.assertIn("matched", text, "an ambiguous name says what it matched")

    def test_a_name_that_matches_nothing_says_so(self):
        text = self._answer("sales", partner="Nobody By This Name 9f3c")
        self.assertIn("Nobody By This Name 9f3c", text)

    def test_a_breakdown_the_report_does_not_have_is_ignored(self):
        text = self._answer("headcount", group_by="product")
        self.assertIn("Active employees", text)

    def test_stock_is_listed_per_product_never_added_up(self):
        if "stock.quant" not in self.env:
            self.skipTest("stock is not installed")
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        product = self.env["product.product"].create(
            {"name": "Ask Probe Stocked", "is_storable": True}
        )
        self.env["stock.quant"]._update_available_quantity(
            product, warehouse.lot_stock_id, 7
        )
        text = self._answer("stock", product="Ask Probe Stocked")
        self.assertIn("Ask Probe Stocked", text)
        self.assertIn("**7 ", text)

    def test_headcount_counts_active_employees(self):
        if "hr.employee" not in self.env:
            self.skipTest("hr is not installed")
        before = self.env["hr.employee"].search_count([])
        self.env["hr.employee"].create({"name": "Ask Probe Employee"})
        text = self._answer("headcount")
        self.assertIn(f"Total: **{before + 1}**", text)

    def test_salaries_read_the_current_contract(self):
        if "hr.version" not in self.env:
            self.skipTest("hr is not installed")
        employee = self.env["hr.employee"].create({"name": "Ask Probe Earner"})
        employee.current_version_id.wage = 23456
        text = self._answer("salaries", employee="Ask Probe Earner")
        self.assertIn("Ask Probe Earner", text)
        self.assertIn("$23,456.00", text)

    def test_a_statement_asks_whose_it_is(self):
        text = self._answer("statement")
        self.assertIn("customer's or supplier's name", text)

    def test_a_statement_lists_what_a_customer_owes(self):
        if "account.move" not in self.env:
            self.skipTest("account is not installed")
        journal = self.env["account.journal"].search([("type", "=", "sale")], limit=1)
        if not journal:
            self.skipTest("no sale journal: no chart of accounts on this database")
        customer = self.env["res.partner"].create({"name": "Ask Probe Debtor"})
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "journal_id": journal.id,
                "invoice_date": self.today,
                "invoice_line_ids": [
                    Command.create({"name": "Ask probe line", "price_unit": 500.0})
                ],
            }
        )
        invoice.action_post()
        text = self._answer("statement", partner="Ask Probe Debtor")
        # the summary comes first: totals, no document list
        self.assertIn("Account statement", text)
        self.assertIn("Ask Probe Debtor", text)
        self.assertIn("Receivable", text)
        self.assertIn("Invoiced", text)
        self.assertNotIn(invoice.name, text)
        self.assertIn("breakdown or the PDF", text)
        extras = {}
        with self.reader.env() as env:
            queries = catalog.available_queries(env)
            detail = catalog.answer(
                env,
                queries["statement"],
                {"partner": "Ask Probe Debtor", "detail": True},
                tz="America/Mexico_City",
                today=self.today,
                extras=extras,
            )
        self.assertIn(invoice.name, detail)
        self.assertIn("Not due yet", detail)
        self.assertEqual(extras["statement_partner_id"], customer.id)

    def test_summary_only_answers_the_total(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        first = self.env["res.partner"].create({"name": "Ask Probe Summary A"})
        second = self.env["res.partner"].create({"name": "Ask Probe Summary B"})
        self._confirmed_order(first, 100)
        self._confirmed_order(second, 200)
        text = self._answer(
            "sales", partner="Ask Probe Summary", group_by="partner", summary_only=True
        )
        self.assertIn("Total:", text)
        self.assertNotIn("• Ask Probe Summary", text)

    def test_payments_list_who_paid_today(self):
        if "account.payment" not in self.env:
            self.skipTest("account is not installed")
        journal = self.env["account.journal"].search([("type", "=", "bank")], limit=1)
        if not journal:
            self.skipTest("no bank journal on this database")
        customer = self.env["res.partner"].create({"name": "Ask Probe Payer"})
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": customer.id,
                "amount": 321.0,
                "journal_id": journal.id,
            }
        )
        payment.action_post()
        text = self._answer("payments")
        self.assertIn("Received from customers", text)
        self.assertIn("Ask Probe Payer", text)
        self.assertIn("$321.00", text)

    def test_the_agent_can_run_an_exact_report(self):
        tools = OdooTools(
            self.reader,
            catalog.available_queries(self.env),
            tz="America/Mexico_City",
            today=self.today,
        )
        self.assertEqual(tools.tools()[0]["name"], "run_report")
        self.env.flush_all()
        result = json_loads(tools.call("run_report", {"report": "headcount"}))
        self.assertIn("Active employees", result["report"])
        result = json_loads(tools.call("run_report", {"report": "weather"}))
        self.assertIn("No report", result["error"])

    def _guarantee_file(self, partner):
        kind = self.env["document.type"].create(
            {
                "name": "Garantía",
                "code": "ASK_PROBE_GUARANTEE",
                **(
                    {"has_collateral": True}
                    if "has_collateral" in self.env["document.type"]._fields
                    else {}
                ),
            }
        )
        release = self.env["document.type"].create(
            {"name": "Liberación de garantía", "code": "ASK_PROBE_RELEASE"}
        )
        document = self.env["document.document"].create(
            {
                "name": "Contrato de terreno.pdf",
                "partner_id": partner.id,
                "document_type_id": kind.id,
                "raw": TINY_PDF,
                "mimetype": "application/pdf",
            }
        )
        self.env["document.document"].create(
            {
                "name": "Acuse de liberación.pdf",
                "partner_id": partner.id,
                "document_type_id": release.id,
                "raw": TINY_PDF,
                "mimetype": "application/pdf",
            }
        )
        return document

    def test_the_credit_file_finds_the_guarantees(self):
        if "document.type" not in self.env:
            self.skipTest("document is not installed")
        customer = self.env["res.partner"].create({"name": "Ask Probe Borrower"})
        self._guarantee_file(customer)
        text = self._answer("credit", partner="Ask Probe Borrower")
        self.assertIn("Credit and guarantees of Ask Probe Borrower", text)
        self.assertIn("Garantía: Contrato de terreno.pdf", text)
        self.assertIn("guarantee release document", text)
        if "has_collateral" in self.env["document.type"]._fields:
            self.assertIn("guarantee without amount captured", text)

    def test_a_guarantee_file_is_collected(self):
        if "document.type" not in self.env:
            self.skipTest("document is not installed")
        customer = self.env["res.partner"].create({"name": "Ask Probe Pledger"})
        self._guarantee_file(customer)
        self.env.flush_all()
        files, names = documents.collect(
            self.env, "guarantee", {"partner": "Ask Probe Pledger"}
        )
        self.assertEqual(names, ["Contrato de terreno.pdf"])
        self.assertEqual(files, [("Contrato de terreno.pdf", TINY_PDF)])

    def test_a_printed_document_is_rendered(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        customer = self.env["res.partner"].create({"name": "Ask Probe Buyer"})
        order = self._confirmed_order(customer, 50)
        with patch.object(
            type(self.env["ir.actions.report"]),
            "_render_qweb_pdf",
            return_value=(b"%PDF-1.4 order", "pdf"),
        ) as render:
            files, names = documents.collect(
                self.env, "sale_order", {"reference": order.name}
            )
        self.assertEqual(render.call_count, 1)
        report = self.env["ir.actions.report"].browse(render.call_args.args[0])
        self.assertTrue(report.exists(), "the id rendered is a report action's")
        self.assertEqual(report.report_name, "sale.report_saleorder")
        self.assertEqual(names, [order.display_name])
        self.assertEqual(files[0][1], b"%PDF-1.4 order")
        self.assertTrue(files[0][0].endswith(".pdf"))

    def test_a_missing_partner_is_said(self):
        with self.assertRaises(catalog.NotFound):
            documents.collect(self.env, "guarantee", {"partner": "Nobody 7c1e"})

    def test_a_name_is_found_word_by_word_and_without_accents(self):
        victor = self.env["res.partner"].create(
            {"name": "Victor Hugo Juarez Hernandez Probe"}
        )
        self.env.flush_all()
        with self.reader.env() as env:
            self.assertEqual(
                catalog.find(env, "res.partner", "Victor Juárez Probe").ids, victor.ids
            )
            self.assertEqual(
                catalog.find(env, "res.partner", "juarez victor probe").ids, victor.ids
            )
            self.assertFalse(catalog.find(env, "res.partner", "Victor Ramirez Probe"))

    def test_every_report_runs_on_an_empty_period(self):
        # a report must answer, not crash, whatever the data
        for key in catalog.available_queries(self.env):
            with self.subTest(report=key):
                self.assertTrue(
                    self._answer(key, date_from="2001-01-01", date_to="2001-01-31")
                )


@tagged("post_install", "-at_install")
class TestInsightHandler(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.router = cls.env["telegram.router"]
        cls.handler = cls.env["telegram.handler.insight"]
        cls.company = cls.env.ref("base.main_company")
        cls.group = cls.env.ref("insight_telegram.group_insight_telegram")
        cls.test_bot.insight_ai_enabled = True
        cls.mock_ok = cls.mock_telegram_response(
            success=True, result={"message_id": 99}
        )

    def _insight_jobs(self):
        return self.env["ir.job"].search(
            [
                ("model_name", "=", "telegram.chat"),
                ("method_name", "=", "_insight_answer"),
            ]
        )

    def _send(self, message):
        with self.mock_api_gateway_post(self.mock_ok):
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

    def _run_job(self, question, interpretation):
        with (
            self.mock_api_gateway_post(self.mock_ok) as post,
            patch.object(
                InsightAssistant,
                "available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(InsightAssistant, "interpret", return_value=interpretation),
        ):
            self.test_chat._insight_answer(
                self.test_bot.id, {"text": question}, self.company.id
            )
        return str(post.call_args_list)

    def _classifier(self, data):
        model = self.env["integration.ml.model"].search([], limit=1)
        return (
            patch(
                "odoo.addons.integration_machine_learning.tools.router.MlRouter.run",
                autospec=True,
                return_value=SimpleNamespace(data=data),
            ),
            patch.object(InsightAssistant, "_chat_model", return_value=model),
        )

    def test_the_bot_defaults_to_the_reader_and_a_fast_provider(self):
        self.assertEqual(
            self.test_bot.insight_reader_user_id,
            self.env.ref("insight_telegram.user_reader"),
        )
        self.assertEqual(
            self.test_bot.insight_ai_provider_id,
            self.env.ref("integration_machine_learning.ai_provider_google"),
        )

    def test_only_group_members_on_an_enabled_bot_may_ask(self):
        may_ask = self.handler._may_ask
        self.assertFalse(may_ask(self.test_bot, self.test_user))
        self.test_user.group_ids = [Command.link(self.group.id)]
        self.assertTrue(may_ask(self.test_bot, self.test_user))
        self.test_bot.insight_ai_enabled = False
        self.assertFalse(may_ask(self.test_bot, self.test_user))

    def test_no_command_is_needed(self):
        self.assertFalse(self.handler._telegram_commands())
        self.assertFalse(self.test_bot.command_ids)

    def test_a_member_question_is_answered_by_a_job(self):
        self.test_user.group_ids = [Command.link(self.group.id)]
        self._send(
            self.mock_telegram_message(text="¿Cuántos clientes hay?", message_id=7)
        )
        job = self._insight_jobs()
        self.assertEqual(len(job), 1)
        self.assertEqual(job.args[0], self.test_bot.id)
        self.assertEqual(job.identity_key, f"telegram_insight:{self.test_chat.id}:7")

    def test_a_voice_note_is_a_question_too(self):
        self.test_user.group_ids = [Command.link(self.group.id)]
        message = self.mock_telegram_message(text="", message_id=8)
        del message["text"]
        message["voice"] = {"file_id": "voice-1", "duration": 3}
        self._send(message)
        self.assertEqual(len(self._insight_jobs()), 1)

    def test_a_stranger_question_queues_nothing(self):
        self._send(self.mock_telegram_message(text="¿Cuánto vendimos?"))
        self.assertFalse(self._insight_jobs())

    def test_a_bot_without_questions_queues_nothing(self):
        self.test_user.group_ids = [Command.link(self.group.id)]
        self.test_bot.insight_ai_enabled = False
        self._send(self.mock_telegram_message(text="¿Cuánto vendimos?"))
        self.assertFalse(self._insight_jobs())

    def test_an_answered_question_is_sent_logged_and_remembered(self):
        if "hr.employee" not in self.env:
            self.skipTest("hr is not installed")
        interpretation = {"query": "headcount", "group_by": None}
        sent = self._run_job("¿Cuántos empleados hay?", interpretation)
        self.assertIn("Active employees", sent)
        log = self.env["telegram.insight.log"].search(
            [("bot_id", "=", self.test_bot.id)]
        )
        self.assertEqual(len(log), 1)
        self.assertTrue(log.answered)
        self.assertEqual(log.query, "headcount")
        self.assertEqual(log.user_id, self.env.user)
        history = self.test_chat._insight_history()
        self.assertEqual(history[-1]["interpretation"], interpretation)

    def test_a_question_no_report_answers_is_declined_and_logged(self):
        sent = self._run_job("¿Quién ganó el partido?", {"query": "none"})
        self.assertIn("I did not find what you asked for.", sent)
        log = self.env["telegram.insight.log"].search(
            [("bot_id", "=", self.test_bot.id)]
        )
        self.assertFalse(log.answered)
        self.assertFalse(log.query)

    def test_the_classifier_is_one_structured_call(self):
        queries = catalog.available_queries(self.env)
        run, chat_model = self._classifier({"query": "headcount", "group_by": None})
        with run as mocked_run, chat_model:
            result = InsightAssistant(self.test_bot).interpret(
                "¿Cuánta gente trabaja aquí?", [], queries, today="2026-10-08"
            )
        expected = "headcount" if "headcount" in queries else "none"
        self.assertEqual(result["query"], expected)
        self.assertEqual(mocked_run.call_count, 1)
        request = mocked_run.call_args.args[2]
        self.assertEqual(request.response_schema, _schema(queries))
        self.assertIn("2026-10-08", request.system)

    def test_an_unknown_report_reads_as_none(self):
        run, chat_model = self._classifier({"query": "weather"})
        with run, chat_model:
            result = InsightAssistant(self.test_bot).interpret(
                "¿Va a llover?",
                [],
                catalog.available_queries(self.env),
                today="2026-10-08",
            )
        self.assertEqual(result["query"], "none")

    def test_long_answers_are_split_between_lines(self):
        text = "\n".join(f"• línea {n} con **{n}** & más" for n in range(400))
        chunks = _chunks(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= CHUNK_LIMIT for chunk in chunks))
        self.assertIn("<b>7</b> &amp; más", chunks[0])

    def test_the_bot_runs_no_agent_until_asked(self):
        self.assertFalse(self.test_bot.insight_agent_enabled)
        self.assertEqual(
            self.test_bot.insight_agent_provider_id,
            self.env.ref("integration_machine_learning.ai_provider_anthropic"),
        )
        self.assertEqual(
            self.test_bot.insight_agent_model_id,
            self.env.ref("integration_machine_learning.ai_model_claude_haiku_4_5"),
        )

    def test_a_greeting_gets_what_the_bot_answers(self):
        sent = self._run_job("Hola", {"query": "help"})
        self.assertIn("Ask me about the business", sent)
        log = self.env["telegram.insight.log"].search(
            [("bot_id", "=", self.test_bot.id)]
        )
        self.assertTrue(log.answered)
        self.assertEqual(log.query, "help")

    def test_a_question_no_report_answers_goes_to_the_agent(self):
        with (
            patch.object(
                InsightAgent, "available", new_callable=PropertyMock, return_value=True
            ),
            patch.object(
                InsightAgent, "answer", return_value="Hay **3** almacenes."
            ) as agent,
        ):
            sent = self._run_job("¿Cuántos almacenes hay?", {"query": "none"})
        self.assertEqual(agent.call_count, 1)
        self.assertIn("AI-consulted answer", sent)
        self.assertIn("Hay <b>3</b> almacenes.", sent)
        log = self.env["telegram.insight.log"].search(
            [("bot_id", "=", self.test_bot.id)]
        )
        self.assertTrue(log.answered)
        self.assertEqual(log.query, "agent")
        self.assertEqual(self.test_chat._insight_history()[-1]["answer"], log.answer)

    def test_the_agent_loop_reads_then_answers(self):
        responses = iter(
            [
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "count_records",
                            "input": {"model": "stock.warehouse"},
                        }
                    ]
                },
                {"content": [{"type": "text", "text": "Hay 3 almacenes."}]},
            ]
        )
        seen = []

        def turn(agent, model, system, messages, *, last):
            seen.append([dict(message) for message in messages])
            return next(responses)

        class FakeTools:
            def call(self, name, arguments):
                return json_dumps({"count": 3})

            def companies(self):
                return "Main (id 1, MXN)"

        model = self.env["integration.ml.model"].search([], limit=1)
        with (
            patch.object(InsightAgent, "_chat_model", return_value=model),
            patch.object(InsightAgent, "_turn", turn),
        ):
            answer = InsightAgent(self.test_bot).answer(
                "¿Cuántos almacenes?", [], FakeTools(), tz="UTC", today="2026-10-08"
            )
        self.assertEqual(answer, "Hay 3 almacenes.")
        tool_result = seen[1][-1]["content"][0]
        self.assertEqual(tool_result["tool_use_id"], "call_1")
        self.assertEqual(json_loads(tool_result["content"]), {"count": 3})

    def test_a_doubtful_report_goes_to_the_agent(self):
        with (
            patch.object(
                InsightAgent, "available", new_callable=PropertyMock, return_value=True
            ),
            patch.object(InsightAgent, "answer", return_value="Comparado.") as agent,
        ):
            sent = self._run_job(
                "¿Vendimos más de lo que cobramos?",
                {"query": "sales", "confidence": 0.3},
            )
        self.assertEqual(agent.call_count, 1)
        self.assertIn("Comparado.", sent)
        log = self.env["telegram.insight.log"].search(
            [("bot_id", "=", self.test_bot.id)]
        )
        self.assertEqual(log.query, "agent")

    def test_a_confident_report_answers_itself(self):
        if "hr.employee" not in self.env:
            self.skipTest("hr is not installed")
        with (
            patch.object(
                InsightAgent, "available", new_callable=PropertyMock, return_value=True
            ),
            patch.object(InsightAgent, "answer") as agent,
        ):
            sent = self._run_job(
                "¿Cuántos empleados hay?", {"query": "headcount", "confidence": 0.9}
            )
        self.assertFalse(agent.called)
        self.assertIn("Active employees", sent)

    def test_a_request_for_documents_sends_them(self):
        with (
            patch.object(
                InsightAssistant,
                "available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                InsightAssistant,
                "interpret",
                return_value={
                    "query": "send_document",
                    "document_kind": "guarantee",
                    "partner": "X",
                },
            ),
            patch(
                "odoo.addons.insight_telegram.services.documents.collect",
                return_value=([("garantia.pdf", b"%PDF")], ["garantia.pdf"]),
            ),
            patch.object(type(self.test_bot), "send_document") as send,
            self.mock_api_gateway_post(self.mock_ok),
        ):
            self.test_chat._insight_answer(
                self.test_bot.id, {"text": "mándame la garantía de X"}, self.company.id
            )
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1:3], (b"%PDF", "garantia.pdf"))
        log = self.env["telegram.insight.log"].search(
            [("bot_id", "=", self.test_bot.id)]
        )
        self.assertEqual(log.query, "send_document")
        self.assertIn("garantia.pdf", log.answer)


@tagged("post_install", "-at_install")
class TestWriteOperations(TransactionCase):
    def _sale(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        customer = self.env["res.partner"].create({"name": "Ask Probe Writer"})
        product = self.env["product.product"].create(
            {"name": "Ask Probe Writable", "list_price": 10}
        )
        return customer, product

    def test_the_technical_side_and_deleting_are_refused(self):
        for operation in (
            {"op": "create", "model": "res.users", "values": {"name": "x"}},
            {"op": "write", "model": "ir.ui.view", "ids": [1], "values": {"name": "x"}},
            {"op": "create", "model": "ir.cron", "values": {"name": "x"}},
            {"op": "unlink", "model": "res.partner", "ids": [1]},
            {"op": "action", "model": "res.partner", "ids": [1], "method": "unlink"},
            {
                "op": "action",
                "model": "res.partner",
                "ids": [1],
                "method": "action_delete",
            },
        ):
            with (
                self.subTest(operation=operation),
                self.assertRaises(write_ops.OperationError),
            ):
                write_ops.check(self.env, operation)

    def test_a_draft_line_may_be_removed_and_nothing_else(self):
        customer, product = self._sale()
        line = [0, 0, {"product_id": product.id, "product_qty": 1}]
        order = self.env["sale.order"].create(
            {"partner_id": customer.id, "line_ids": [line, line]}
        )
        other = self.env["sale.order"].create(
            {"partner_id": customer.id, "line_ids": [line]}
        )

        def remove(command, ids=None):
            return {
                "op": "write",
                "model": "sale.order",
                "ids": ids or [order.id],
                "values": {"line_ids": [command]},
            }

        removal = write_ops.check(self.env, remove([2, order.line_ids[0].id]))
        self.assertIn("Quitar:", "\n".join(write_ops.describe(self.env, [removal])))
        write_ops.apply(self.env(su=True), [removal], [], self.env.user)
        self.assertEqual(len(order.line_ids), 1, "a draft line is removed")
        for operation in (
            remove([5]),
            remove([2, other.line_ids.id]),
            remove([2, order.line_ids.id], ids=["ref:1"]),
            {
                "op": "create",
                "model": "sale.order",
                "values": {"partner_id": customer.id, "line_ids": [[2, 1]]},
            },
        ):
            with (
                self.subTest(operation=operation),
                self.assertRaises(write_ops.OperationError),
            ):
                write_ops.check(self.env, operation)
        order.action_confirm()
        with self.assertRaisesRegex(write_ops.OperationError, "draft"):
            write_ops.check(self.env, remove([2, order.line_ids.id]))

    def test_a_proposal_reads_as_the_screen_shows_it(self):
        customer, product = self._sale()
        operations = [
            {
                "op": "create",
                "model": "sale.order",
                "values": {
                    "partner_id": customer.id,
                    "line_ids": [
                        [
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "product_qty": 2080,
                                "price_unit": 260.0,
                            },
                        ],
                        [
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "product_qty": 416,
                                "price_unit": 0.0,
                            },
                        ],
                    ],
                },
            },
            {
                "op": "action",
                "model": "sale.order",
                "ids": ["ref:1"],
                "method": "action_confirm",
            },
        ]
        text = "\n".join(write_ops.describe(self.env, operations))
        self.assertIn(customer.display_name, text)
        self.assertIn(product.display_name, text)
        self.assertIn("2,080", text)
        self.assertIn("540,800.00", text, "line subtotal and order total")
        self.assertNotIn("partner_id", text)
        self.assertNotIn("product_id", text)
        self.assertNotIn(f"={customer.id}", text)
        self.assertIn("«confirm»", text)

    def test_an_unknown_field_is_explained(self):
        with self.assertRaisesRegex(write_ops.OperationError, "no field"):
            write_ops.check(
                self.env,
                {"op": "create", "model": "res.partner", "values": {"no_such": 1}},
            )

    def test_an_order_is_created_confirmed_noted_and_attached(self):
        customer, product = self._sale()
        operations = [
            {
                "op": "create",
                "model": "sale.order",
                "values": {
                    "partner_id": customer.id,
                    "line_ids": [[0, 0, {"product_id": product.id, "product_qty": 2}]],
                },
                "attach_files": True,
            },
            {
                "op": "action",
                "model": "sale.order",
                "ids": ["ref:1"],
                "method": "action_confirm",
            },
        ]
        operations = [write_ops.check(self.env, operation) for operation in operations]
        touched = write_ops.apply(
            self.env(su=True),
            operations,
            [("ticket.txt", b"ticket", "text/plain")],
            self.env.user,
        )
        order = touched[0]
        self.assertEqual(order.state, "done")
        self.assertEqual(order.line_ids.product_id, product)
        self.assertTrue(
            self.env["ir.attachment"].search(
                [("res_model", "=", "sale.order"), ("res_id", "=", order.id)]
            )
        )
        self.assertIn("a petición de", order.message_ids[:1].body)

    def test_a_failing_operation_changes_nothing(self):
        customer, _product = self._sale()
        before = self.env["sale.order"].search_count([])
        operations = [
            {
                "op": "create",
                "model": "sale.order",
                "values": {"partner_id": customer.id},
            },
            {
                "op": "action",
                "model": "sale.order",
                "ids": [999999999],
                "method": "action_confirm",
            },
        ]
        with self.assertRaises(write_ops.OperationError):
            write_ops.apply(self.env(su=True), operations, [], self.env.user)
        self.assertEqual(self.env["sale.order"].search_count([]), before)

    def test_proposals_write_nothing(self):
        reader = OdooReader(
            self.registry, self.env.ref("insight_telegram.user_reader").id
        )
        tools = OdooTools(reader, writable=True)
        self.assertIn("propose_create", [tool["name"] for tool in tools.tools()])
        result = json_loads(
            tools.call(
                "propose_create",
                {"model": "res.partner", "values": {"name": "Ask Probe Proposed"}},
            )
        )
        self.assertEqual(result["proposal"], 1)
        self.assertEqual(len(tools.proposals), 1)
        self.assertFalse(
            self.env["res.partner"].search([("name", "=", "Ask Probe Proposed")])
        )
        refused = json_loads(
            tools.call(
                "propose_create", {"model": "res.users", "values": {"name": "x"}}
            )
        )
        self.assertIn("cannot be changed", refused["error"])

    def test_any_odoo_pdf_can_be_queued(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        customer, _product = self._sale()
        order = self.env["sale.order"].create({"partner_id": customer.id})
        self.env.flush_all()
        reader = OdooReader(
            self.registry, self.env.ref("insight_telegram.user_reader").id
        )
        tools = OdooTools(reader)
        reports = json_loads(tools.call("pdf_reports", {"model": "sale.order"}))[
            "reports"
        ]
        self.assertTrue(reports)
        queued = json_loads(
            tools.call("send_pdf", {"report_id": reports[0]["id"], "ids": [order.id]})
        )
        self.assertIn(order.display_name, queued["records"])
        self.assertEqual(
            tools.pdf_requests, [(reports[0]["id"], "sale.order", [order.id])]
        )
        refused = json_loads(
            tools.call("send_pdf", {"report_id": 0, "ids": [order.id]})
        )
        self.assertIn("No such PDF report", refused["error"])

    def test_a_created_order_is_printed_with_its_main_report(self):
        customer, _product = self._sale()
        order = self.env["sale.order"].create({"partner_id": customer.id})
        report = documents.main_report(self.env, "sale.order")
        self.assertEqual(report.report_name, "sale.report_saleorder")
        with patch.object(
            type(self.env["ir.actions.report"]),
            "_render_qweb_pdf",
            return_value=(TINY_PDF, "pdf"),
        ) as render:
            files = documents.print_records(self.env, order)
        self.assertEqual(render.call_args.args[:2], (report.id, order.ids))
        self.assertEqual(files[0][1], TINY_PDF)
        self.assertFalse(
            documents.print_records(self.env, self.env["res.partner"].browse()),
            "nothing printed for no record",
        )

    def test_a_read_only_bot_offers_no_change(self):
        reader = OdooReader(
            self.registry, self.env.ref("insight_telegram.user_reader").id
        )
        names = [tool["name"] for tool in OdooTools(reader).tools()]
        self.assertNotIn("propose_create", names)


@tagged("post_install", "-at_install")
class TestFiles(TransactionCase):
    def test_each_kind_of_file_becomes_a_block(self):
        blocks = files.blocks(
            [
                ("photo.jpg", b"\xff\xd8jpeg", "image/jpeg"),
                ("factura.pdf", TINY_PDF, "application/pdf"),
                ("lista.csv", b"a,b\n1,2", "text/csv"),
                ("raro.bin", b"\x00\x01", "application/octet-stream"),
            ]
        )
        kinds = [block["type"] for block in blocks]
        self.assertEqual(kinds[0], "image")
        self.assertIn("document", kinds)
        texts = " ".join(block.get("text", "") for block in blocks)
        self.assertIn("a,b", texts)
        self.assertIn("not readable as text", texts)

    def test_a_word_document_is_read(self):
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hola contrato'
                "</w:t></w:r></w:p></w:body></w:document>",
            )
        blocks = files.blocks([("c.docx", buffer.getvalue(), "")])
        self.assertIn("Hola contrato", blocks[0]["text"])

    def test_authorizing_words(self):
        self.assertEqual(_decision("Autorizo"), "authorize")
        self.assertEqual(_decision("sí, autorízalo por favor"), "authorize")
        self.assertEqual(_decision("cancelar"), "cancel")
        self.assertEqual(_decision("no autorizo"), "cancel")
        self.assertIsNone(_decision("¿cuánto vendimos?"))


@tagged("post_install", "-at_install")
class TestSuperBotFlow(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.test_bot.insight_ai_enabled = True
        cls.mock_ok = cls.mock_telegram_response(success=True, result={"message_id": 9})

    def _job(self, message, interpretation=None, agent=None):
        patches = [
            self.mock_api_gateway_post(self.mock_ok),
            patch.object(
                InsightAssistant,
                "available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                InsightAssistant,
                "interpret",
                return_value=interpretation or {"query": "none"},
            ),
        ]
        if agent is not None:
            patches += [
                patch.object(
                    InsightAgent,
                    "available",
                    new_callable=PropertyMock,
                    return_value=True,
                ),
                patch.object(
                    type(self.test_chat), "_insight_ask_agent", return_value=agent
                ),
            ]
        with contextlib.ExitStack() as stack:
            post = stack.enter_context(patches[0])
            mocks = [stack.enter_context(p) for p in patches[1:]]
            self.test_chat._insight_answer(self.test_bot.id, message, self.company.id)
        return str(post.call_args_list), mocks

    def test_proposals_wait_for_authorization_then_apply(self):
        proposal = [
            {
                "op": "create",
                "model": "res.partner",
                "values": {"name": "Ask Probe Super"},
            }
        ]
        sent, _mocks = self._job(
            {"text": "da de alta al cliente Ask Probe Super"},
            agent=("Propongo crear el cliente.", proposal),
        )
        self.assertIn("ins_ok", sent)
        self.assertTrue(self.test_chat._insight_pending())
        self.assertFalse(
            self.env["res.partner"].search([("name", "=", "Ask Probe Super")])
        )
        with (
            patch(
                "odoo.addons.insight_telegram.services.documents.print_records",
                return_value=[("Ask Probe Super.pdf", TINY_PDF)],
            ) as printed,
            patch.object(type(self.test_bot), "send_document") as send,
        ):
            sent, _mocks = self._job({"text": "autorizo"})
        self.assertIn("/odoo/res.partner/", sent, "the answer links the record")
        self.assertEqual(printed.call_count, 1, "a created record is printed")
        self.assertEqual(send.call_args.args[1:3], (TINY_PDF, "Ask Probe Super.pdf"))
        partner = self.env["res.partner"].search([("name", "=", "Ask Probe Super")])
        self.assertTrue(partner)
        self.assertEqual(partner.create_uid, self.env.user)
        self.assertFalse(self.test_chat._insight_pending())

    def test_cancelling_discards_the_proposals(self):
        proposal = [
            {
                "op": "create",
                "model": "res.partner",
                "values": {"name": "Ask Probe Never"},
            }
        ]
        self._job({"text": "crea Ask Probe Never"}, agent=("Propongo.", proposal))
        sent, _mocks = self._job({"text": "cancelar"})
        self.assertIn("nothing was changed", sent)
        self.assertFalse(
            self.env["res.partner"].search([("name", "=", "Ask Probe Never")])
        )
        self.assertFalse(self.test_chat._insight_pending())

    def test_a_photo_goes_to_the_agent_with_its_file(self):
        message = {
            "photo": [{"file_id": "small"}, {"file_id": "big"}],
            "caption": "¿Qué es esto?",
        }
        with patch.object(
            type(self.test_chat),
            "_insight_download",
            return_value=[("photo.jpg", b"\xff\xd8jpeg", "image/jpeg")],
        ) as download:
            _sent, mocks = self._job(message, agent=("Es una factura.", []))
        self.assertEqual(
            download.call_args.args[1], [("big", "photo.jpg", "image/jpeg")]
        )
        ask_agent = mocks[-1]
        blocks = ask_agent.call_args.args[-1]
        self.assertEqual(blocks[0]["type"], "image")
        self.assertFalse(mocks[1].called, "a file skips the classifier")

    def test_queued_pdfs_are_printed_and_sent(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        customer = self.env["res.partner"].create({"name": "Ask Probe PDF"})
        order = self.env["sale.order"].create({"partner_id": customer.id})
        report = self.env.ref("sale.action_report_saleorder")
        reader = OdooReader(
            self.registry, self.env.ref("insight_telegram.user_reader").id
        )
        with (
            patch.object(
                type(self.env["ir.actions.report"]),
                "_render_qweb_pdf",
                return_value=(TINY_PDF, "pdf"),
            ) as render,
            patch.object(type(self.test_bot), "send_document") as send,
            self.mock_api_gateway_post(self.mock_ok),
        ):
            self.test_chat._insight_send_pdfs(
                self.test_bot,
                self.test_chat,
                [(report.id, "sale.order", order.ids)],
                reader,
            )
        self.assertEqual(render.call_args.args[:2], (report.id, order.ids))
        self.assertEqual(send.call_args.args[1], TINY_PDF)
        self.assertTrue(send.call_args.args[2].endswith(".pdf"))

    def test_a_statement_offers_its_breakdown_and_pdf(self):
        from odoo.addons.insight_telegram.models.telegram_chat import (
            _statement_buttons,
        )

        tr_env = self.env
        markup = _statement_buttons(
            tr_env, {"statement_partner_id": 7}, {"query": "statement"}
        )
        data = [button["callback_data"] for button in markup["inline_keyboard"][0]]
        self.assertEqual(data, ["ins_det:7", "ins_pdf:7"])
        markup = _statement_buttons(
            tr_env, {"statement_partner_id": 7}, {"query": "statement", "detail": True}
        )
        self.assertEqual(
            [b["callback_data"] for b in markup["inline_keyboard"][0]], ["ins_pdf:7"]
        )
        self.assertIsNone(_statement_buttons(tr_env, {}, {"query": "sales"}))

    def test_the_pdf_button_sends_the_statement(self):
        with (
            patch(
                "odoo.addons.insight_telegram.services.documents.collect",
                return_value=([("estado.pdf", TINY_PDF)], ["Cliente"]),
            ) as collect,
            patch.object(type(self.test_bot), "send_document") as send,
            patch.object(
                InsightAssistant,
                "available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            self.mock_api_gateway_post(self.mock_ok),
        ):
            self.test_chat._insight_answer(
                self.test_bot.id,
                {"insight_action": "statement_pdf", "partner_id": 7},
                self.company.id,
            )
        self.assertEqual(collect.call_args.args[1], "statement")
        self.assertEqual(collect.call_args.args[2]["partner_id"], 7)
        self.assertEqual(send.call_count, 1)

    def test_a_reply_to_the_agent_goes_back_to_it_with_the_files(self):
        from odoo.addons.insight_telegram.models.telegram_chat import (
            _answers_the_agent,
        )

        now = fields.Datetime.to_string(fields.Datetime.now())
        asked = [
            {
                "interpretation": {"query": "none"},
                "answer": "¿Confirmas que es Versa?",
                "at": now,
            }
        ]
        self.assertTrue(_answers_the_agent(asked))
        told = [{"interpretation": {"query": "none"}, "answer": "Listo.", "at": now}]
        self.assertFalse(_answers_the_agent(told))
        report = [
            {"interpretation": {"query": "sales"}, "answer": "¿Algo más?", "at": now}
        ]
        self.assertFalse(_answers_the_agent(report))
        applied = [
            {"interpretation": {"decision": "authorize"}, "answer": "Listo:", "at": now}
        ]
        self.assertTrue(_answers_the_agent(applied), "a correction follows a change")
        cancelled = [
            {"interpretation": {"decision": "cancel"}, "answer": "Cancelado", "at": now}
        ]
        self.assertFalse(_answers_the_agent(cancelled))
        self.test_chat._set_context(
            "telegram_insight_files",
            {"files": [["big", "photo.jpg", "image/jpeg"]], "at": now},
        )
        self.test_chat._set_context(
            "telegram_insight_history",
            [
                {
                    "question": "orden para versa",
                    "interpretation": {"query": "none"},
                    "answer": "¿Confirmas que es Agroquímicos Versa?",
                    "at": now,
                }
            ],
        )
        with patch.object(
            type(self.test_chat),
            "_insight_download",
            return_value=[("photo.jpg", b"\xff\xd8jpeg", "image/jpeg")],
        ) as download:
            _sent, mocks = self._job(
                {"text": "Sí, agroquímicos versa"}, agent=("Va.", [])
            )
        self.assertFalse(mocks[1].called, "the reply skips the classifier")
        self.assertEqual(
            download.call_args.args[1], [("big", "photo.jpg", "image/jpeg")]
        )
