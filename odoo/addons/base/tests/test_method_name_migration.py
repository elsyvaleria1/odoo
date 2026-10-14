import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from odoo.tests.common import BaseCase, TransactionCase, tagged
from odoo.tools import SQL
from odoo.tools.method_data import (
    rename_stored_model_methods,
    rewrite_model_method_references,
)


def _load_method_name_migration(version="1.157"):
    path = Path(__file__).parents[1] / f"migrations/{version}/pre-method-names.py"
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

    def test_rebinding_does_not_reuse_a_previous_model_alias(self):
        bindings = (
            "records: object = unknown\nrecords._find()\n",
            "records, other = unknown, 1\nrecords._find()\n",
            "for records in unknown:\n    pass\nrecords._find()\n",
            "try:\n    fail()\nexcept Exception as records:\n    records._find()\n",
            "[(records := unknown) for item in [1]]\nrecords._find()\n",
            "with unknown as records:\n    records._find()\n",
            "def records():\n    pass\nrecords._find()\n",
            "match unknown:\n    case records:\n        records._find()\n",
            'condition and (records := env["ir.access.exception"])\nrecords._find()\n',
            "def replace():\n    global records\n    records = unknown\nreplace()\nrecords._find()\n",
            'def outer():\n    records = env["ir.access.drift"]\n    def replace():\n        nonlocal records\n        records = unknown\n    replace()\n    records._find()\nouter()\n',
        )
        for binding in bindings:
            code = 'records = env["ir.access.drift"]\n' + binding
            unresolved = set()
            with self.subTest(binding=binding):
                rewritten = self.migration._rewrite_generic_method_bindings(
                    code, None, {}, unresolved
                )
                self.assertEqual(rewritten, code)
                self.assertTrue(unresolved)

    def test_an_annotated_model_alias_can_be_resolved(self):
        code = 'records: object = env["ir.access.drift"]\nrecords._find()\n'
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(code, None, {}),
            code.replace("records._find", "records._get_findings_by_identity"),
        )

    def test_aliases_use_the_last_unconditional_assignment(self):
        code = (
            "records = records.sudo()\n"
            "snapshot = records\n"
            'records = env["ir.access.exception"]\n'
            "snapshot._find()\nrecords._find()\n"
        )
        expected = code.replace(
            "snapshot._find", "snapshot._get_findings_by_identity"
        ).replace("records._find", "records._get_exception_active")
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, "ir.access.drift", {}
            ),
            expected,
        )
        code = 'method = "_find"\nmethod = "other"\ngetattr(records, method)()'
        unresolved = set()
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, "ir.access.drift", {}, unresolved
            ),
            code,
        )
        self.assertFalse(unresolved)

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

    def test_getattr_resolves_method_name_aliases_without_changing_other_uses(self):
        code = 'method = "_find"\ntext = method\ngetattr(records, method)()\n'
        expected = code.replace(
            "getattr(records, method)", "getattr(records, '_get_exception_active')"
        )
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, "ir.access.exception", {}
            ),
            expected,
        )

    def test_a_conditional_getattr_name_needs_review(self):
        code = 'condition and (method := "_find")\ngetattr(records, method)()\n'
        unresolved = set()
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, "ir.access.exception", {}, unresolved
            ),
            code,
        )
        self.assertEqual(unresolved, {("_find", 2)})

    def test_indirect_getattr_names_cannot_silently_keep_removed_methods(self):
        for code in (
            'method, = ("_find",)\ngetattr(records, method)()',
            'method = "_find"\ndef helper():\n    return getattr(records, method)()\nhelper()',
            'method = "_find" if condition else "other"\ngetattr(records, method)()',
            'method = ["_find"][0]\ngetattr(records, method)()',
        ):
            unresolved = set()
            with self.subTest(code=code):
                self.assertEqual(
                    self.migration._rewrite_generic_method_bindings(
                        code, "ir.access.drift", {}, unresolved
                    ),
                    code,
                )
                self.assertTrue(unresolved)

        code = 'method = ["_find"][0]\ngetattr(records, method)()'
        unresolved = set()
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, "unrelated.model", {}, unresolved
            ),
            code,
        )
        self.assertFalse(unresolved)

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

    def test_specialized_names_only_rewrite_their_own_model(self):
        for model, old, new in (
            ("res.users", "_check_uid_passwd", "_authenticate_rpc_credentials"),
            ("ir.access.changeset", "_check_review", "_get_impact_reviewed"),
            ("ir.ui.view", "_refuse_recombination", "_handle_recombination_error"),
            ("resource.resource", "_find_free_window", "_get_window_free"),
        ):
            code = f'env["{model}"].{old}()\nenv["unrelated.model"].{old}()\n'
            expected = code.replace(f'"{model}"].{old}', f'"{model}"].{new}')
            with self.subTest(model=model, old=old):
                self.assertEqual(
                    self.migration._rewrite_generic_method_bindings(code, None, {}),
                    expected,
                )

    def test_method_names_follow_ordinary_inheritance(self):
        parents = {
            "custom.drift": {"ir.access.drift"},
            "custom.child": {"custom.drift"},
            "custom.users": {"res.users"},
        }
        code = (
            'env["custom.child"]._find()\n'
            'env["custom.users"]._check_uid_passwd(db, uid, passwd)\n'
        )
        expected = code.replace("._find", "._get_findings_by_identity").replace(
            "._check_uid_passwd", "._authenticate_rpc_credentials"
        )
        self.assertEqual(
            self.migration._rewrite_generic_method_bindings(
                code, None, {}, model_parents=parents
            ),
            expected,
        )

    def test_conflicting_inherited_contracts_need_review(self):
        parents = {"custom.credentials": {"res.users", "res.users.apikeys"}}
        with self.assertRaisesRegex(ValueError, "conflicting inherited methods"):
            self.migration._rewrite_generic_method_bindings(
                'env["custom.credentials"]._check_credentials(credential)',
                None,
                {},
                model_parents=parents,
            )

    def test_error_calls_follow_ordinary_inheritance(self):
        code = "record._raise_currently_executing()\n"
        rewritten = self.migration._rewrite_error_method_calls(
            code, "custom.cron", {}, model_parents={"custom.cron": {"ir.cron"}}
        )
        self.assertEqual(
            rewritten, "raise record._prepare_cron_running_error() from None\n"
        )
        with self.assertRaisesRegex(ValueError, "Cannot migrate _deny_login"):
            self.migration._rewrite_error_method_calls(
                'getattr(record, "_deny_login")(credential)',
                "custom.users",
                {},
                model_parents={"custom.users": {"res.users"}},
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
            'method = "_deny_login"\ngetattr(record, method)(credential)',
            'method, = ("_deny_login",)\ngetattr(record, method)(credential)',
            'method = "_deny_login"\ndef helper():\n    getattr(record, method)(credential)\nhelper()',
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
class TestSharedMethodReferenceRewrite(TestMethodNameMigration):
    allow_inherited_tests_method = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        migration = cls.migration

        def rewrite(
            code,
            model,
            relations,
            unresolved=None,
            *,
            context_models=None,
            model_parents=None,
        ):
            result = rewrite_model_method_references(
                code,
                model,
                relations,
                model_method_renames=migration.MODEL_METHOD_RENAMES,
                shared_method_renames=migration.SHARED_MODEL_METHOD_RENAMES,
                context_models=context_models,
                model_parents=model_parents,
            )
            if unresolved is not None:
                unresolved.update(result.unresolved)
            return result.code

        migration._rewrite_generic_method_bindings = rewrite


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
                        "CREATE TABLE ir_model_inherit (model_id integer, parent_id integer, parent_field_id integer)"
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

    def test_inherited_methods_exclude_delegated_models(self):
        with self._use_migration_schema() as cr:
            cr.execute(
                "INSERT INTO ir_model VALUES (4, 'custom.drift'), (5, 'custom.child'), (6, 'custom.delegated')"
            )
            cr.execute(
                "INSERT INTO ir_model_inherit VALUES (4, 1, NULL), (5, 4, NULL), (6, 1, 1)"
            )
            cr.execute(
                "INSERT INTO ir_model_fields VALUES (1, 6, 'drift_id', 'ir.access.drift', NULL)"
            )
            cr.execute(
                "INSERT INTO ir_act_server VALUES (1, 4, 'records._find()'), (2, 5, 'records._find()'), (3, 6, 'records._find()'), (4, 6, 'records.drift_id._find()')"
            )
            self.migration.migrate(cr, "1.152")
            cr.execute("SELECT code FROM ir_act_server ORDER BY id")
            self.assertEqual(
                cr.fetchall(),
                [
                    ("records._get_findings_by_identity()",),
                    ("records._get_findings_by_identity()",),
                    ("records._find()",),
                    ("records.drift_id._get_findings_by_identity()",),
                ],
            )

    def test_failed_upgrade_rolls_back_earlier_rewrites(self):
        for history_code in (
            "unknown._find()",
            'records = env["ir.access.drift"]\nrecords, other = unknown, 1\nrecords._find()',
            'method = ["_find"][0]\ngetattr(records, method)()',
        ):
            with (
                self.subTest(history_code=history_code),
                self._use_migration_schema() as cr,
            ):
                code = "records._find()"
                cr.execute("INSERT INTO ir_act_server VALUES (1, 1, %s)", [code])
                cr.execute(
                    "INSERT INTO ir_actions_server_history VALUES (1, 1, %s)",
                    [history_code],
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


@tagged("post_install", "-at_install")
class TestSharedStoredMethodRename(TestMethodNameMigrationDatabase):
    allow_inherited_tests_method = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        migration = cls.migration

        def migrate(cr, version):
            if version:
                rename_stored_model_methods(
                    cr,
                    model_method_renames=migration.MODEL_METHOD_RENAMES,
                    shared_method_renames=migration.SHARED_MODEL_METHOD_RENAMES,
                )

        migration.migrate = migrate

    def test_egress_methods_upgrade_with_source_and_unrelated_owners_preserved(self):
        migration = _load_method_name_migration("1.162")
        with self._use_migration_schema() as cr:
            cr.execute(
                "INSERT INTO ir_model VALUES (4, 'ir.egress'), (5, 'custom.egress')"
            )
            code = (
                "# café: keep check_url in comments\n"
                'text = "check_host"\n'
                'guard = env["ir.egress"].sudo()\n'
                'destination = guard.check_url("https://1.1.1.1")\n'
                'addresses = getattr(guard, "check_host")("1.1.1.1", 443)\n'
            )
            cr.execute(
                "INSERT INTO ir_act_server VALUES (1, 2, %s), (2, 5, 'records.check_url()')",
                [code],
            )
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 1, %s)", [code]
            )
            cr.execute(
                "INSERT INTO ir_model_fields VALUES (1, 2, 'egress_id', 'ir.egress', 'self.egress_id.check_host()')"
            )
            edge_sources = (
                ("records.ｃｈｅｃｋ_host()", "records.get_permitted_host_addresses()"),
                (
                    r'getattr(records, "\x63heck_host")()',
                    "getattr(records, 'get_permitted_host_addresses')()",
                ),
            )
            for row_id, (source, _) in enumerate(edge_sources, 3):
                cr.execute(
                    "INSERT INTO ir_act_server VALUES (%s, 4, %s)", [row_id, source]
                )
            migration.migrate(cr, "1.160")
            expected = code.replace(
                "guard.check_url", "guard.get_permitted_url_destination"
            ).replace('"check_host")', "'get_permitted_host_addresses')")
            for table in ("ir_act_server", "ir_actions_server_history"):
                cr.execute(
                    SQL("SELECT code FROM %s WHERE id = 1", SQL.identifier(table))
                )
                self.assertEqual(cr.fetchone()[0], expected)
            cr.execute("SELECT code FROM ir_act_server WHERE id = 2")
            self.assertEqual(cr.fetchone()[0], "records.check_url()")
            cr.execute("SELECT compute FROM ir_model_fields WHERE id = 1")
            self.assertEqual(
                cr.fetchone()[0], "self.egress_id.get_permitted_host_addresses()"
            )
            cr.execute("SELECT code FROM ir_act_server WHERE id >= 3 ORDER BY id")
            self.assertEqual(
                cr.fetchall(), [(expected,) for _, expected in edge_sources]
            )
            migration.migrate(cr, "1.160")
            cr.execute("SELECT code FROM ir_actions_server_history WHERE id = 1")
            self.assertEqual(cr.fetchone()[0], expected)

    def test_shared_verb_methods_upgrade_every_stored_code_owner_and_column(self):
        self._check_shared_stored_method_upgrade("1.163")

    def test_shared_anchor_methods_upgrade_every_stored_code_owner_and_column(self):
        self._check_shared_stored_method_upgrade("1.164")

    def _check_shared_stored_method_upgrade(self, version):
        migration = _load_method_name_migration(version)
        renames = migration.SHARED_MODEL_METHOD_RENAMES
        old_names = list(renames)
        code = f"# café: keep {old_names[0]}\ntext = {old_names[1]!r}\n"
        expected = code
        for old, new in renames.items():
            code += f"records.{old}\ngetattr(records, {old!r})\n"
            expected += f"records.{new}\ngetattr(records, {new!r})\n"
        with self._use_migration_schema() as cr:
            for row_id, model_id in enumerate((1, 2, 3), 1):
                cr.execute(
                    "INSERT INTO ir_act_server VALUES (%s, %s, %s)",
                    [row_id, model_id, code],
                )
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 2, %s)", [code]
            )
            cr.execute(
                "INSERT INTO ir_model_fields VALUES (1, 2, 'computed', NULL, %s)",
                [
                    code.replace("records.", "self.").replace(
                        "getattr(records,", "getattr(self,"
                    )
                ],
            )
            payroll_code = code.replace("records", 'env["res.partner"]')
            cr.execute(
                "INSERT INTO hr_salary_rule VALUES (1, %s, %s, %s, %s)",
                [payroll_code] * 4,
            )
            cr.execute(
                "INSERT INTO hr_payroll_dashboard_warning VALUES (1, %s)",
                [payroll_code],
            )
            migration.migrate(cr, None)
            cr.execute("SELECT code FROM ir_act_server ORDER BY id")
            self.assertEqual(cr.fetchall(), [(code,)] * 3)
            for _ in range(2):
                migration.migrate(cr, "1.162")
                cr.execute("SELECT code FROM ir_act_server ORDER BY id")
                self.assertEqual(cr.fetchall(), [(expected,)] * 3)
                cr.execute("SELECT code FROM ir_actions_server_history")
                self.assertEqual(cr.fetchone()[0], expected)
                cr.execute("SELECT compute FROM ir_model_fields")
                self.assertEqual(
                    cr.fetchone()[0],
                    expected.replace("records.", "self.").replace(
                        "getattr(records,", "getattr(self,"
                    ),
                )
                cr.execute(
                    "SELECT amount_python_compute, condition_python, amount_percentage_base, quantity FROM hr_salary_rule"
                )
                self.assertEqual(
                    cr.fetchone(),
                    (expected.replace("records", 'env["res.partner"]'),) * 4,
                )
                cr.execute("SELECT evaluation_code FROM hr_payroll_dashboard_warning")
                self.assertEqual(
                    cr.fetchone()[0], expected.replace("records", 'env["res.partner"]')
                )

    def test_unresolved_shared_verb_owner_rolls_back_the_upgrade(self):
        migration = _load_method_name_migration("1.163")
        with self._use_migration_schema() as cr:
            cr.execute(
                "INSERT INTO ir_act_server VALUES (1, 2, 'records._verb_checkpoint()')"
            )
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 1, 'unknown._check_verb_creations()')"
            )
            with (
                self.assertRaisesRegex(ValueError, "Cannot resolve method owners"),
                cr.savepoint(flush=False),
            ):
                migration.migrate(cr, "1.162")
            cr.execute("SELECT code FROM ir_act_server")
            self.assertEqual(cr.fetchone()[0], "records._verb_checkpoint()")

    def test_unresolved_shared_anchor_owner_rolls_back_the_upgrade(self):
        migration = _load_method_name_migration("1.164")
        with self._use_migration_schema() as cr:
            cr.execute(
                "INSERT INTO ir_act_server VALUES (1, 2, 'records._access_company_anchor()')"
            )
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 1, 'unknown._anchors_before_write()')"
            )
            with (
                self.assertRaisesRegex(ValueError, "Cannot resolve method owners"),
                cr.savepoint(flush=False),
            ):
                migration.migrate(cr, "1.163")
            cr.execute("SELECT code FROM ir_act_server")
            self.assertEqual(cr.fetchone()[0], "records._access_company_anchor()")

    def test_unresolved_egress_owner_rolls_back_the_upgrade(self):
        migration = _load_method_name_migration("1.162")
        with self._use_migration_schema() as cr:
            cr.execute("INSERT INTO ir_model VALUES (4, 'ir.egress')")
            cr.execute("INSERT INTO ir_act_server VALUES (1, 4, 'records.check_url()')")
            cr.execute(
                "INSERT INTO ir_actions_server_history VALUES (1, 1, 'unknown.check_host()')"
            )
            with (
                self.assertRaisesRegex(ValueError, "Cannot resolve method owners"),
                cr.savepoint(flush=False),
            ):
                migration.migrate(cr, "1.160")
            cr.execute("SELECT code FROM ir_act_server WHERE id = 1")
            self.assertEqual(cr.fetchone()[0], "records.check_url()")
