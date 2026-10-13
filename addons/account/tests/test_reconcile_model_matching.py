from psycopg import IntegrityError

from odoo import Command
from odoo.modules.module import get_module_path, load_script
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestReconcileModelMatching(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.counterpart = cls.company_data["default_account_expense"]

    def _model(self, name, **kw):
        kw.setdefault(
            "line_ids",
            [
                Command.create(
                    {
                        "account_id": self.counterpart.id,
                        "amount_type": "percentage",
                        "amount_string": "100",
                    }
                )
            ],
        )
        return self.env["account.reconcile.model"].create({"name": name, **kw})

    def _st_line(self, ref, amount=100.0, **kw):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "payment_ref": ref,
                "amount": amount,
                "date": "2026-08-01",
                **kw,
            }
        )

    def _offered(self, st_line):
        available = self.env[
            "account.reconcile.model"
        ].get_available_reconcile_model_per_statement_line(st_line.ids)
        return {entry["display_name"] for entry in available.get(st_line.id, [])}

    def test_control_plain_matching_works(self):
        self._model("CTL", match_label="contains", match_label_param="COFFEE")
        self.assertIn("CTL", self._offered(self._st_line("MONTHLY COFFEE BILL")))
        self.assertNotIn("CTL", self._offered(self._st_line("MONTHLY TEA BILL")))

    def test_control_an_active_auto_model_reconciles_on_create(self):
        line = self._st_line("OKPROBE PAYMENT", amount=400.0)
        self.env.flush_all()
        self._model(
            "OK",
            match_label="contains",
            match_label_param="OKPROBE",
            trigger="auto_reconcile",
        )
        line.invalidate_recordset()
        self.assertTrue(line.is_reconciled)

    def test_contains_is_a_literal_substring(self):
        self._model("PCT", match_label="contains", match_label_param="%")
        self.assertNotIn("PCT", self._offered(self._st_line("NOTHING RELEVANT")))

    def test_underscore_is_not_a_wildcard(self):
        self._model("US", match_label="contains", match_label_param="_NVOICE")
        self.assertNotIn("US", self._offered(self._st_line("INVOICE 2026")))

    def test_a_literal_percent_still_matches_itself(self):
        self._model("LIT", match_label="contains", match_label_param="5% FEE")
        self.assertIn("LIT", self._offered(self._st_line("MONTHLY 5% FEE CHARGED")))

    def test_transaction_detail_keys_are_not_matched(self):
        line = self._st_line(
            "PLAIN",
            transaction_details={"counterpartyNumber": "BE001", "communication": "hi"},
        )
        self._model("JK", match_label="contains", match_label_param="communication")
        self.assertNotIn("JK", self._offered(line))

    def test_transaction_detail_values_are_matched(self):
        line = self._st_line(
            "PLAIN",
            transaction_details={
                "communication": "ACME INVOICE",
                "nested": {"r": "XY"},
            },
        )
        self._model("JV", match_label="contains", match_label_param="ACME")
        self._model("JN", match_label="contains", match_label_param="XY")
        self.assertEqual({"JV", "JN"}, self._offered(line) & {"JV", "JN"})

    def test_narration_is_searched_by_every_path(self):
        line = self._st_line("PLAIN LABEL")
        line.move_id.narration = "<p>NARRATIONONLY marker</p>"
        self._model("NAR", match_label="contains", match_label_param="NARRATIONONLY")
        self.assertIn("NAR", self._offered(line))

    def test_a_direction_set_after_creation_still_matches(self):
        model = self._model("BOUND")
        model.write({"match_direction": "outgoing"})
        self.assertIn("BOUND", self._offered(self._st_line("ANY", amount=-100.0)))
        self.assertNotIn("BOUND", self._offered(self._st_line("ANY", amount=100.0)))

    def test_the_amount_condition_compares_the_absolute_amount(self):
        self._model("ABS", match_amount="lower", match_amount_max=100.0)
        self.assertIn("ABS", self._offered(self._st_line("ANY", amount=-50.0)))
        self.assertIn("ABS", self._offered(self._st_line("ANY", amount=50.0)))
        self.assertNotIn("ABS", self._offered(self._st_line("ANY", amount=-150.0)))
        self.assertNotIn("ABS", self._offered(self._st_line("ANY", amount=150.0)))

    def test_the_direction_applies_beside_an_amount_condition(self):
        self._model(
            "INB",
            match_direction="incoming",
            match_amount="greater",
            match_amount_min=100.0,
        )
        self.assertIn("INB", self._offered(self._st_line("ANY", amount=150.0)))
        self.assertNotIn("INB", self._offered(self._st_line("ANY", amount=-150.0)))
        self.assertNotIn("INB", self._offered(self._st_line("ANY", amount=50.0)))

    def test_a_direction_alone_makes_a_model_proposable(self):
        self.assertTrue(self._model("DIR", match_direction="incoming").can_be_proposed)

    def test_a_negative_amount_bound_is_refused(self):
        for field in ("match_amount_min", "match_amount_max"):
            with (
                self.subTest(field=field),
                self.assertRaises(IntegrityError),
                mute_logger("odoo.db.cursor"),
            ):
                self._model("NEG", match_amount="between", **{field: -1.0})
                self.env.flush_all()

    def test_between_accepts_its_bounds_in_either_order(self):
        model = self._model("BTW")
        model.write(
            {
                "match_amount": "between",
                "match_amount_min": 500,
                "match_amount_max": 100,
            }
        )
        self.assertIn("BTW", self._offered(self._st_line("ANY", amount=300.0)))
        self.assertNotIn("BTW", self._offered(self._st_line("ANY", amount=900.0)))

    def test_renaming_a_model_does_not_reconcile(self):
        model = self._model(
            "REN",
            match_label="contains",
            match_label_param="RENPROBE",
            trigger="auto_reconcile",
        )
        lines = self.env["account.bank.statement.line"].create(
            [
                {
                    "journal_id": self.bank_journal.id,
                    "payment_ref": f"RENPROBE {index}",
                    "amount": 10.0 + index,
                    "date": "2026-08-01",
                }
                for index in range(5)
            ]
        )
        self.env.flush_all()
        self.assertFalse(any(lines.mapped("is_reconciled")))
        model.write({"name": "REN renamed"})
        lines.invalidate_recordset()
        self.assertFalse(any(lines.mapped("is_reconciled")))

    def test_changing_the_label_filter_reevaluates_the_backlog(self):
        model = self._model(
            "LBL",
            match_label="contains",
            match_label_param="NOMATCHYET",
            trigger="auto_reconcile",
        )
        line = self._st_line("LBLPROBE PAYMENT", amount=400.0)
        self.env.flush_all()
        self.assertFalse(line.is_reconciled)
        model.write({"match_label_param": "LBLPROBE"})
        line.invalidate_recordset()
        self.assertTrue(line.is_reconciled)

    def test_renaming_does_not_reevaluate_the_backlog(self):
        model = self._model(
            "NAMEONLY", match_label="contains", match_label_param="NAMEPROBE"
        )
        line = self._st_line("NAMEPROBE PAYMENT", amount=400.0)
        self.env.flush_all()
        model.write({"name": "NAMEONLY renamed", "next_activity_type_id": False})
        line.invalidate_recordset()
        self.assertFalse(line.is_reconciled)

    def test_archiving_a_model_does_not_reconcile(self):
        model = self._model(
            "ARCH",
            match_label="contains",
            match_label_param="ARCHPROBE",
            trigger="auto_reconcile",
        )
        line = self._st_line("ARCHPROBE PAYMENT", amount=500.0)
        self.env.flush_all()
        self.assertFalse(line.is_reconciled)
        model.action_archive()
        line.invalidate_recordset()
        self.assertFalse(line.is_reconciled)

    def test_creating_an_archived_model_does_not_reconcile(self):
        line = self._st_line("CAFPROBE PAYMENT", amount=400.0)
        self.env.flush_all()
        self._model(
            "CAF",
            active=False,
            match_label="contains",
            match_label_param="CAFPROBE",
            trigger="auto_reconcile",
        )
        line.invalidate_recordset()
        self.assertFalse(line.is_reconciled)

    def test_an_archived_model_is_not_offered(self):
        model = self._model("OFF", match_label="contains", match_label_param="OFFPROBE")
        line = self._st_line("OFFPROBE PAYMENT")
        self.assertIn("OFF", self._offered(line))
        model.action_archive()
        self.assertNotIn("OFF", self._offered(line))


@tagged("post_install", "-at_install")
class TestReconcileModelDirectionMigration(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = load_script(
            f"{get_module_path('account')}/migrations/1.48/post-10-reconcile_model_direction.py",
            "odoo.addons.account.migrations.post_10_reconcile_model_direction_1_48",
        )

    def test_one_sided_and_same_side_conditions_convert_exactly(self):
        convert = self.script._signed_condition_to_absolute
        cases = {
            ("lower", 0.0, -500.0): ("outgoing", "greater", 500.0, 0.0, True),
            ("lower", 0.0, 0.0): ("outgoing", False, 0.0, 0.0, True),
            ("lower", 0.0, None): ("outgoing", False, 0.0, 0.0, True),
            ("greater", 200.0, 0.0): ("incoming", "greater", 200.0, 0.0, True),
            ("greater", 0.0, 0.0): ("incoming", False, 0.0, 0.0, True),
            ("between", -1000.0, -2000.0): (
                "outgoing",
                "between",
                1000.0,
                2000.0,
                True,
            ),
            ("between", -2000.0, 0.0): ("outgoing", "lower", 0.0, 2000.0, True),
            ("between", 500.0, 100.0): ("incoming", "between", 100.0, 500.0, True),
            ("between", 0.0, 300.0): ("incoming", "lower", 0.0, 300.0, True),
            ("between", 0.0, 0.0): ("both", "lower", 0.0, 0.0, True),
            (False, -5.0, -7.0): ("both", False, 0.0, 0.0, True),
        }
        for old, new in cases.items():
            with self.subTest(old=old):
                self.assertEqual(convert(*old), new)

    def test_a_condition_straddling_zero_keeps_its_size_bound_on_both_sides(self):
        convert = self.script._signed_condition_to_absolute
        cases = {
            ("lower", 0.0, 100.0): ("both", "lower", 0.0, 100.0, False),
            ("greater", -300.0, 0.0): ("both", "lower", 0.0, 300.0, False),
            ("between", -400.0, 100.0): ("both", "lower", 0.0, 400.0, False),
        }
        for old, new in cases.items():
            with self.subTest(old=old):
                self.assertEqual(convert(*old), new)

    def test_migration_rewrites_legacy_rows_and_logs_each(self):
        legacy = {
            "outgoing_only": {"match_amount": "lower", "match_amount_max": 0.0},
            "large_payments": {
                "match_amount": "between",
                "match_amount_min": -1000.0,
                "match_amount_max": -2000.0,
            },
            "straddling": {"match_amount": "lower", "match_amount_max": 100.0},
            "stale_bound": {"match_amount_min": -3.0},
            "incoming_only": {"match_amount": "greater", "match_amount_min": 0.0},
        }
        models = {
            name: self.env["account.reconcile.model"].create(
                {
                    "name": name,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.company_data[
                                    "default_account_expense"
                                ].id
                            }
                        )
                    ],
                }
            )
            for name in legacy
        }
        self.env.flush_all()
        self.env.cr.execute(
            "ALTER TABLE account_reconcile_model"
            " DROP CONSTRAINT account_reconcile_model_match_amount_min_match_amount_max_check"
        )
        for name, vals in legacy.items():
            self.env.cr.execute(
                "UPDATE account_reconcile_model SET match_amount = %s,"
                " match_amount_min = %s, match_amount_max = %s WHERE id = %s",
                [
                    vals.get("match_amount"),
                    vals.get("match_amount_min"),
                    vals.get("match_amount_max"),
                    models[name].id,
                ],
            )
        with self.assertLogs(self.script.__name__, "INFO") as logs:
            self.script.migrate(self.env.cr, "1.47")
        self.env.invalidate_all()

        def state(model):
            return (
                model.match_direction,
                model.match_amount,
                model.match_amount_min,
                model.match_amount_max,
            )

        self.assertEqual(state(models["outgoing_only"]), ("outgoing", False, 0.0, 0.0))
        self.assertEqual(
            state(models["large_payments"]), ("outgoing", "between", 1000.0, 2000.0)
        )
        self.assertEqual(state(models["straddling"]), ("both", "lower", 0.0, 100.0))
        self.assertEqual(state(models["stale_bound"]), ("both", False, 0.0, 0.0))
        self.assertEqual(state(models["incoming_only"]), ("incoming", False, 0.0, 0.0))
        messages = {
            name: [
                rec.levelname
                for rec in logs.records
                if rec.getMessage().startswith(f"account.reconcile.model {model.id}:")
            ]
            for name, model in models.items()
        }
        self.assertEqual(
            messages,
            {
                "outgoing_only": ["INFO"],
                "large_payments": ["INFO"],
                "straddling": ["WARNING"],
                "stale_bound": ["INFO"],
                "incoming_only": ["INFO"],
            },
        )
