import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from odoo.tests.common import BaseCase, TransactionCase, tagged
from odoo.tools import SQL


def _load_method_name_migration():
    path = Path(__file__).parents[1] / "migrations/1.153/pre-method-names.py"
    spec = importlib.util.spec_from_file_location("method_name_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


class TestMethodNameMigration(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration = _load_method_name_migration()

    def test_model_aliases_relations_and_unicode_preserve_source(self):
        code = (
            "# café: keep _find in comments\n"
            'links = env["access.link"].sudo()\n'
            "result = links._find_reusable(record)\n"
            "for link in records.link_ids:\n"
            "    getter = link._find_reusable\n"
            'text = "_find_reusable"\n'
        )
        expected = code.replace(
            "links._find_reusable", "links._get_link_and_token_reusable"
        ).replace("link._find_reusable", "link._get_link_and_token_reusable")
        actual = self.migration._rewrite_generic_method_bindings(
            code, "project.project", {("project.project", "link_ids"): "access.link"}
        )
        self.assertEqual(actual, expected)
        compile(actual, "stored code", "exec")

    def test_unrelated_and_unknown_owners_keep_identical_names(self):
        code = (
            'env["calendar.sync"]._find()\n'
            "unknown._find()\n"
            "unknown._find_reusable(record)\n"
            "unknown._validate()\n"
            'env["calendar.sync"]._sweep()\n'
            'value = env["ir.access.drift"]\n'
            'value = env["calendar.sync"]\n'
            "value._find()\n"
        )
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, None, {}), code
        )

    def test_scope_shadowing_and_execution_order_do_not_guess_owners(self):
        cases = (
            (
                'def other():\n    records = env["ir.access.drift"]\nrecords._find()\n',
                "calendar.sync",
            ),
            ("def helper(records):\n    return records._find()\n", "ir.access.drift"),
            ('external.env["ir.access.drift"]._find()\n', None),
            (
                'getter = records._find\nrecords = env["ir.access.drift"]\n',
                "calendar.sync",
            ),
            ('def helper(env):\n    return env["ir.access.drift"]._find()\n', None),
        )
        cases += (
            (
                'if condition:\n    records = env["ir.access.drift"]\nrecords._find()\n',
                "calendar.sync",
            ),
            (
                'for records in env["ir.access.drift"]:\n    pass\nrecords._find()\n',
                "calendar.sync",
            ),
            ("import module as records\nrecords._find()\n", "ir.access.drift"),
            ("values = [records._find() for records in unknown]\n", "ir.access.drift"),
        )
        cases += (
            (
                'env = unknown\ndef helper():\n    return env["ir.access.drift"]._find()\n',
                None,
            ),
            (
                "records = unknown\ndef helper():\n    return records._find()\n",
                "ir.access.drift",
            ),
            (
                'records = env["ir.access.drift"]\nif condition:\n    records = unknown\nrecords._find()\n',
                None,
            ),
        )
        cases += (
            ('def env():\n    pass\nenv["ir.access.drift"]._find()\n', None),
            (
                "def helper():\n    global records\n    return records._find()\n",
                "ir.access.drift",
            ),
            (
                "match unknown:\n    case records:\n        records._find()\n",
                "ir.access.drift",
            ),
        )
        for code, model in cases:
            with self.subTest(code=code):
                self.assertEqual(
                    self.migration._rewrite_generic_method_bindings(code, model, {}),
                    code,
                )

    def test_unique_names_preserve_literals_comments_and_unknown_objects(self):
        code = (
            "# _check_company_domain stays in this comment\n"
            'text = "_check_company_domain"\n'
            "unknown._check_company_domain()\n"
            "record._check_company_domain()\n"
        )
        expected = code.replace(
            "record._check_company_domain", "record._get_domain_company_compatible"
        )
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, "res.partner", {}),
            expected,
        )

    def test_history_reads_model_context_from_its_server_action(self):
        statements = []
        rows = iter(([(7, "ir.access.drift")], [], [(11, "records._find()", 7)]))
        cursor = SimpleNamespace(
            execute=statements.append,
            fetchall=lambda: next(rows),
        )
        self.migration._rename_generic_model_methods(
            cursor,
            {
                ("ir_actions_server_history", "code"),
                ("ir_actions_server_history", "action_id"),
            },
        )
        self.assertIn(
            "SELECT model_id FROM ir_act_server WHERE id = action_id",
            statements[-2].code,
        )

        self.assertEqual(
            statements[-1].params, ("records._get_findings_by_identity()", 11)
        )

    def test_context_model_bound_methods_and_getattr(self):
        code = 'result = records._find(*args)\ngetter = getattr(model, "_find")\n'
        expected = "result = records._get_exception_active(*args)\ngetter = getattr(model, '_get_exception_active')\n"
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, "ir.access.exception", {}
            ),
            expected,
        )

    def test_unknown_owner_is_reported_for_manual_review(self):
        unresolved = set()
        code = 'unknown._find()\nenv["unrelated.model"]._find()\n'
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, None, {}, unresolved),
            code,
        )
        self.assertEqual(unresolved, {("_find", 1)})

    def test_same_spelling_selects_each_model_contract(self):
        code = (
            'env["ir.access.drift"]._find()\n'
            'env["ir.access.exception"]._find(user, kind, scope)\n'
            'env["ir.asset.build"]._find_reusable(kind, bundle, variant, source_key)\n'
            'env["access.link"]._find_reusable(record)\n'
        )
        expected = (
            'env["ir.access.drift"]._get_findings_by_identity()\n'
            'env["ir.access.exception"]._get_exception_active(user, kind, scope)\n'
            'env["ir.asset.build"]._get_build_reusable(kind, bundle, variant, source_key)\n'
            'env["access.link"]._get_link_and_token_reusable(record)\n'
        )
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, None, {}), expected
        )

    def test_credentials_resolve_by_owner_instead_of_shared_method_name(self):
        code = 'env["res.users"]._check_credentials(credential, context)\nenv["res.users.apikeys"]._check_credentials(scope="rpc", key=key)\n'
        expected = 'env["res.users"]._authenticate_credentials(credential, context)\nenv["res.users.apikeys"]._get_user_id_for_key(scope="rpc", key=key)\n'
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, None, {}), expected
        )

    def test_inherited_access_getter_preserves_a_local_validator_with_same_name(self):
        code = 'def _check_access(operation):\n    return None\nrecord._check_access("read")\n_check_access("read")\n'
        expected = code.replace(
            "record._check_access", "record._get_records_forbidden_and_error_factory"
        )
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, "res.partner", {}),
            expected,
        )

    def test_login_error_keeps_password_cost_and_receiver_evaluated_once(self):
        events = []
        error = RuntimeError("denied")
        owner = SimpleNamespace(
            _spend_password_cost=lambda credential: events.append(("cost", credential)),
            _prepare_login_denied_error=lambda: error,
        )

        def get_owner():
            events.append("owner")
            return owner

        record = SimpleNamespace(sudo=get_owner)
        code = "record.sudo()._deny_login(credential())\n"
        rewritten = self.migration._rewrite_error_method_calls(code, "res.users", {})

        def credential():
            events.append("credential")
            return {"password": "test"}

        with self.assertRaises(RuntimeError) as raised:
            exec(rewritten, {"record": record, "credential": credential})  # noqa: S102 -- Execute the migration's fixed test fixture to verify preserved control flow.
        self.assertIs(raised.exception, error)
        self.assertEqual(
            events, ["owner", "credential", ("cost", {"password": "test"})]
        )

    def test_cron_error_still_raises_and_suppresses_context(self):
        error = RuntimeError("running")
        owner = SimpleNamespace(_prepare_cron_running_error=lambda: error)
        code = "record._raise_currently_executing()\n"
        rewritten = self.migration._rewrite_error_method_calls(code, "ir.cron", {})
        with self.assertRaises(RuntimeError) as raised:
            exec(rewritten, {"record": owner})  # noqa: S102 -- Verify that the rewritten fixture raises the original error.
        self.assertIs(raised.exception, error)
        self.assertTrue(error.__suppress_context__)

    def test_unsupported_error_bindings_fail_without_silently_removing_raise(self):
        for code in (
            "unknown._deny_login(credential)",
            "callback = record._deny_login",
            "result = record._deny_login(credential)",
            'getattr(record, "_deny_login")(credential)',
            'callback = getattr(record, "_deny_login")',
        ):
            with (
                self.subTest(code=code),
                self.assertRaisesRegex(ValueError, "Cannot migrate _deny_login"),
            ):
                self.migration._rewrite_error_method_calls(code, "res.users", {})
        code = 'env["unrelated.model"]._deny_login(credential)'
        self.assertEqual(
            self.migration._rewrite_error_method_calls(code, "res.users", {}), code
        )

    def test_unresolved_rows_stop_the_upgrade_with_their_identity(self):
        for code in ("unknown._find()", 'getattr(unknown, "_find")', "record._find("):
            with self.subTest(code=code):
                rows = iter(([(7, "ir.access.drift")], [], [(11, code, 7)]))
                statements = []
                cursor = SimpleNamespace(
                    execute=statements.append, fetchall=lambda rows=rows: next(rows)
                )
                with self.assertRaisesRegex(ValueError, r"ir_act_server.code, row 11:"):
                    self.migration._rename_generic_model_methods(
                        cursor,
                        {("ir_act_server", "code"), ("ir_act_server", "model_id")},
                    )
                self.assertFalse(
                    any(
                        statement.code.startswith("UPDATE")
                        for statement in statements[2:]
                    )
                )

    def test_payroll_contexts_use_the_models_in_their_execution_context(self):
        for table, code, expected in (
            (
                "hr_salary_rule",
                "employee._check_company_domain()\npayslip._check_access('read')",
                "employee._get_domain_company_compatible()\npayslip._get_records_forbidden_and_error_factory('read')",
            ),
            (
                "hr_payroll_dashboard_warning",
                "self.env['ir.access.drift']._find()",
                "self.env['ir.access.drift']._get_findings_by_identity()",
            ),
        ):
            with self.subTest(table=table):
                self.assertEqual(
                    self.migration._rewrite_generic_method_bindings(
                        code,
                        None,
                        {},
                        context_models=self.migration.CODE_CONTEXT_MODELS[table],
                    ),
                    expected,
                )


@tagged("post_install", "-at_install")
class TestMethodNameMigrationDatabase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration = _load_method_name_migration()

    @contextmanager
    def _use_migration_schema(self):
        cr = self.env.cr
        self.env.flush_all()
        schema = f"method_name_migration_{uuid4().hex}"
        with cr.savepoint():
            cr.execute("SELECT current_setting('search_path')")
            search_path = cr.fetchone()[0]
            cr.execute(SQL("CREATE SCHEMA %s", SQL.identifier(schema)))
            cr.execute(SQL("SET LOCAL search_path TO %s", SQL.identifier(schema)))
            try:
                with cr.savepoint(flush=False):
                    cr.execute(
                        "CREATE TABLE ir_model (id integer PRIMARY KEY, model text)"
                    )
                    cr.execute(
                        "CREATE TABLE ir_model_fields (id integer PRIMARY KEY, model_id integer, name text, relation text, compute text)"
                    )
                    cr.execute(
                        "CREATE TABLE ir_act_server (id integer PRIMARY KEY, model_id integer, code text)"
                    )
                    cr.execute(
                        "CREATE TABLE ir_actions_server_history (id integer PRIMARY KEY, action_id integer, code text)"
                    )
                    cr.execute(
                        "INSERT INTO ir_model VALUES (1, 'ir.access.drift'), (2, 'res.partner'), (3, 'res.users')"
                    )
                    cr.execute(
                        "CREATE TABLE hr_salary_rule (id integer PRIMARY KEY, amount_python_compute text, condition_python text, amount_percentage_base text, quantity text)"
                    )
                    cr.execute(
                        "CREATE TABLE hr_payroll_dashboard_warning (id integer PRIMARY KEY, evaluation_code text)"
                    )
                    yield cr
            finally:
                cr.execute("SELECT set_config('search_path', %s, true)", [search_path])
                cr.execute(SQL("DROP SCHEMA %s CASCADE", SQL.identifier(schema)))

    def test_stored_code_and_history_upgrade_is_idempotent(self):
        with self._use_migration_schema() as cr:
            code = 'records._find()\ntext = "_find"\n# _find\n'
            cr.execute(
                "INSERT INTO ir_act_server VALUES (1, 1, %s), (2, 2, NULL)", [code]
            )
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 1, %s)", [code]
            )
            cr.execute(
                "INSERT INTO ir_model_fields VALUES (1, 2, 'link_ids', 'ir.access.drift', %s)",
                ["self.link_ids._find()"],
            )
            payroll_code = 'env["ir.access.drift"]._find()'
            cr.execute(
                "INSERT INTO hr_salary_rule VALUES (1, %s, %s, %s, %s)",
                [payroll_code] * 4,
            )
            cr.execute(
                "INSERT INTO hr_payroll_dashboard_warning VALUES (1, %s)",
                [payroll_code],
            )
            self.migration.migrate(cr, "1.152")
            for table in ("ir_act_server", "ir_actions_server_history"):
                cr.execute(
                    SQL("SELECT code FROM %s WHERE id = 1", SQL.identifier(table))
                )
                self.assertEqual(
                    cr.fetchone()[0],
                    code.replace("records._find", "records._get_findings_by_identity"),
                )
            cr.execute("SELECT compute FROM ir_model_fields WHERE id = 1")
            self.assertEqual(
                cr.fetchone()[0], "self.link_ids._get_findings_by_identity()"
            )
            cr.execute(
                "SELECT amount_python_compute, condition_python, amount_percentage_base, quantity FROM hr_salary_rule WHERE id = 1"
            )
            expected_payroll = payroll_code.replace(
                "._find", "._get_findings_by_identity"
            )
            self.assertEqual(cr.fetchone(), (expected_payroll,) * 4)
            cr.execute(
                "SELECT evaluation_code FROM hr_payroll_dashboard_warning WHERE id = 1"
            )
            self.assertEqual(cr.fetchone()[0], expected_payroll)
            self.migration.migrate(cr, "1.152")
            cr.execute("SELECT code FROM ir_actions_server_history WHERE id = 1")
            self.assertEqual(
                cr.fetchone()[0],
                code.replace("records._find", "records._get_findings_by_identity"),
            )

    def test_failed_upgrade_rolls_back_earlier_rewrites(self):
        with self._use_migration_schema() as cr:
            code = "records._find()"
            cr.execute("INSERT INTO ir_act_server VALUES (1, 1, %s)", [code])
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 1, 'unknown._find()')"
            )
            with (
                self.assertRaisesRegex(
                    ValueError, r"ir_actions_server_history.code, row 1:"
                ),
                cr.savepoint(flush=False),
            ):
                self.migration.migrate(cr, "1.152")
            cr.execute("SELECT code FROM ir_act_server WHERE id = 1")
            self.assertEqual(cr.fetchone()[0], code)
