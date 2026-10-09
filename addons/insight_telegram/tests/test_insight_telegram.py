from datetime import date
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from psycopg import errors as pg_errors

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged

from odoo.addons.insight_telegram.models.telegram_chat import CHUNK_LIMIT, _chunks
from odoo.addons.insight_telegram.services import catalog
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
        self.assertIn("Account statement of Ask Probe Debtor", text)
        self.assertIn("Receivable in", text)
        self.assertIn(invoice.name, text)
        self.assertIn("invoiced", text)

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
