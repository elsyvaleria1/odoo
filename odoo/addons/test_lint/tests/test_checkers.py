from pathlib import Path

from odoo.modules import Manifest
from odoo.tests.common import BaseCase, no_retry

from . import _pretty_xml, lint_case


@no_retry
class TestCorePathScoping(BaseCase):
    def test_a_sibling_checkout_is_not_core(self):
        root = lint_case.core_root()
        self.assertTrue(lint_case.is_core_path(root))
        self.assertTrue(lint_case.is_core_path(str(Path(root) / "addons" / "x.py")))
        for sibling in (f"{root}-companion", f"{root}_legacy", f"{root}2"):
            with self.subTest(sibling=sibling):
                self.assertFalse(
                    lint_case.is_core_path(str(Path(sibling) / "x.py")),
                    "a separately-versioned checkout is not this repository",
                )

    def test_the_real_siblings_on_this_addons_path_are_excluded(self):
        roots = [manifest.path for manifest in Manifest.get_all_addon_manifests()]
        self.assertTrue(roots, "no addon roots at all")
        core = [path for path in roots if lint_case.is_core_path(str(path))]
        self.assertTrue(core, "no core addon roots -- the scoping reached nothing")
        self.assertTrue(
            all(Path(lint_case.core_root()) in Path(path).parents for path in core),
            "is_core_path admitted a root outside this repository",
        )


@no_retry
class TestScanScope(BaseCase):
    def test_a_data_file_is_xml(self):
        from pathlib import Path

        self.assertTrue(_pretty_xml.is_formattable(Path("/a/account/views/x.xml")))
        for path in ("/a/account/views/x.py", "/a/account/README.md"):
            with self.subTest(path=path):
                self.assertFalse(_pretty_xml.is_formattable(Path(path)))

    def test_the_shared_data_file_selection_is_reused_not_rebuilt(self):
        self.assertIs(lint_case._core_data_files(), lint_case._core_data_files())
        self.assertIsNot(
            lint_case.core_data_files(),
            lint_case.core_data_files(),
            "callers get their own list; the cache holds an immutable tuple",
        )

    def test_this_repositorys_modules_are_a_subset_of_the_addons_path(self):
        names = lint_case.core_module_names()
        self.assertIn("base", names)
        self.assertIn("web", names)
        self.assertTrue(
            names <= {m.name for m in Manifest.get_all_addon_manifests()},
            "core modules must be modules the addons path actually carries",
        )


@no_retry
class TestLeadingIndexColumns(BaseCase):
    class _FakeModel:
        pool = None

        def __init__(self, table_objects):
            self._table_objects = table_objects

    def _columns(self, *definitions, unique=False):
        from odoo.orm import models as orm_models

        from .test_index import leading_index_columns

        build = orm_models.UniqueIndex if unique else orm_models.Index
        return leading_index_columns(
            self._FakeModel(
                {str(i): build(definition) for i, definition in enumerate(definitions)}
            )
        )

    def test_a_composite_index_answers_its_leading_column(self):
        self.assertEqual(self._columns("(product_id, location_id)"), {"product_id"})
        self.assertEqual(
            self._columns("(product_id, location_id, trace_id, package_id)"),
            {"product_id"},
        )

    def test_a_trailing_column_is_not_answered(self):
        self.assertNotIn("location_id", self._columns("(product_id, location_id)"))

    def test_a_sort_direction_changes_nothing(self):
        self.assertEqual(self._columns("(date desc, move_name desc, id)"), {"date"})

    def test_a_not_null_partial_index_counts(self):
        self.assertEqual(
            self._columns("(user_id) WHERE user_id IS NOT NULL"), {"user_id"}
        )

    def test_any_other_partial_index_does_not(self):
        for definition in (
            "(channel) WHERE state = 'started'",
            "(id) WHERE state = 'outgoing'",
            "(channel_id, end_dt) WHERE end_dt IS NULL",
            "(has_crm_lead) WHERE has_crm_lead IS TRUE",
        ):
            with self.subTest(definition=definition):
                self.assertEqual(
                    self._columns(definition),
                    set(),
                    "a partial index only answers the rows it covers",
                )

    def test_a_non_btree_index_does_not_answer_equality(self):
        self.assertEqual(self._columns("USING gin (barcode jsonb_path_ops)"), set())

    def test_an_expression_index_has_no_leading_column(self):
        self.assertEqual(self._columns("(lower(name))"), set())

    def test_a_unique_index_counts_like_any_other(self):
        self.assertEqual(
            self._columns("(guest_id) WHERE guest_id IS NOT NULL", unique=True),
            {"guest_id"},
        )

    def _constraint_columns(self, definition):
        from odoo.orm import models as orm_models

        from .test_index import leading_index_columns

        return leading_index_columns(
            self._FakeModel({"c": orm_models.Constraint(definition, "message")})
        )

    def test_a_unique_constraint_answers_its_leading_column(self):
        self.assertEqual(
            self._constraint_columns("unique(account_move_line_id)"),
            {"account_move_line_id"},
        )
        self.assertEqual(
            self._constraint_columns("UNIQUE (employee_id, bank_account_id)"),
            {"employee_id"},
        )
        self.assertEqual(
            self._constraint_columns("UNIQUE NULLS NOT DISTINCT (code, company_id)"),
            {"code"},
        )

    def test_a_check_or_exclusion_constraint_answers_nothing(self):
        for definition in (
            "CHECK (amount >= 0)",
            "EXCLUDE USING gist (resource_id WITH =, period WITH &&)",
        ):
            with self.subTest(definition=definition):
                self.assertEqual(self._constraint_columns(definition), set())
