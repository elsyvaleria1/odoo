from unittest import mock

from odoo import Command
from odoo.orm.models.mixins import unlink as unlink_mixin
from odoo.orm.models.mixins._metadata import _ModelMetadataMixin
from odoo.orm.primitives import MODULE_UNINSTALL_FLAG
from odoo.tests import common

_VIEW = "test_orm.custom.table_query_sql"


class TestDependsFlushMemo(common.TransactionCase):
    def _create_child(self, quantity):
        parent = self.env["test_orm.any.parent"].create({"name": "parent"})
        child = self.env["test_orm.any.child"].create(
            {
                "parent_id": parent.id,
                "quantity": quantity,
                "tag_ids": [Command.create({"name": "memo tag"})],
            }
        )
        return child, child.tag_ids

    def test_repeated_searches_walk_the_depends_closure_once(self):
        self.registry.__dict__.pop("_depends_flush_fields_by_model", None)
        calls = []
        original = _ModelMetadataMixin._get_depends_closure

        def counted(model):
            calls.append(model._name)
            return original(model)

        with mock.patch.object(_ModelMetadataMixin, "_get_depends_closure", counted):
            for _ in range(5):
                self.env[_VIEW].search([])
        self.assertEqual(calls, [_VIEW])

    def test_a_search_flushes_a_dependency_written_in_the_transaction(self):
        child, tag = self._create_child(10)
        view = self.env[_VIEW]
        self.assertEqual(view.search([("tag_id", "=", tag.id)]).sum_quantity, 10)
        view.invalidate_model()
        child.quantity = 25
        self.assertEqual(view.search([("tag_id", "=", tag.id)]).sum_quantity, 25)

    def test_a_view_flushes_the_manual_field_its_setup_replaced(self):
        view = self.env[_VIEW]
        view.search([])
        self.assertIn(_VIEW, self.registry._depends_flush_fields_by_model)
        child_model = self.env["ir.model"]._get("test_orm.any.child")
        view_cls = self.registry[_VIEW]
        query = property(
            lambda self: (
                "SELECT child.id AS id, child.x_memo_qty AS sum_quantity, "
                "NULL::integer AS tag_id FROM test_orm_any_child AS child"
            )
        )
        with (
            mock.patch.object(
                view_cls, "_depends", {"test_orm.any.child": ["x_memo_qty"]}
            ),
            mock.patch.object(view_cls, "_table_query", query),
        ):
            self.env["ir.model.fields"].create(
                {"model_id": child_model.id, "name": "x_memo_qty", "ttype": "integer"}
            )
            child, _tag = self._create_child(0)
            child.x_memo_qty = 3
            self.assertEqual(view.search([("id", "=", child.id)]).sum_quantity, 3)
            before = self.env["test_orm.any.child"]._fields["x_memo_qty"]
            self.assertIn(before, self.registry.depends_flush_fields(view))

            self.env["ir.model.fields"].create(
                {"model_id": child_model.id, "name": "x_memo_other", "ttype": "char"}
            )
            after = self.env["test_orm.any.child"]._fields["x_memo_qty"]
            self.assertIsNot(after, before)

            view.invalidate_model()
            child.x_memo_qty = 7
            self.assertEqual(view.search([("id", "=", child.id)]).sum_quantity, 7)
            flushed = self.registry.depends_flush_fields(view)
            self.assertIn(after, flushed)
            self.assertNotIn(before, flushed)


class TestPathColumnMemo(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.registry.__dict__.pop("_paths_in_database", None)

    def _catalog_queries(self, func):
        with self.capturedQueries() as queries:
            func()
        return sum("pg_attribute" in query for query in queries)

    def _server_action(self, **values):
        return self.env["ir.actions.server"].create(
            {
                "name": "memo",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "code": "",
                **values,
            }
        )

    def test_the_second_unlink_asks_no_catalog(self):
        first, second = self._server_action(), self._server_action()
        self.assertGreater(self._catalog_queries(first.unlink), 0)
        self.assertEqual(self._catalog_queries(second.unlink), 0)

    def _manual_cascade(self):
        field = self.env["ir.model.fields"].create(
            {
                "model_id": self.env["ir.model"]._get_id("ir.actions.server"),
                "name": "x_memo_partner_id",
                "ttype": "many2one",
                "relation": "res.partner",
                "on_delete": "cascade",
            }
        )
        self.assertIn(
            ("ir.actions.server", "x_memo_partner_id"),
            self.registry.cascades_into_inheritance_trees["res.partner"],
        )
        return field

    def test_a_column_dropped_on_uninstall_is_asked_again(self):
        field = self._manual_cascade()
        first, second = self.env["res.partner"].create(
            [{"name": "first"}, {"name": "second"}]
        )
        action = self._server_action(x_memo_partner_id=first.id)
        first.unlink()
        self.assertFalse(action.exists())
        key = ("ir.actions.server", "x_memo_partner_id")
        self.assertIn(key, self.registry._paths_in_database)

        field.with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()
        self.assertNotIn(key, self.registry._paths_in_database)
        with mock.patch.object(
            unlink_mixin, "column_exists", wraps=unlink_mixin.column_exists
        ) as asked:
            second.unlink()
        self.assertIn(
            mock.call(mock.ANY, "ir_act_server", "x_memo_partner_id"),
            asked.call_args_list,
        )
        self.assertNotIn(key, self.registry._paths_in_database)

    def test_a_deleted_field_leaves_the_memo(self):
        field = self._manual_cascade()
        first = self.env["res.partner"].create({"name": "first"})
        self._server_action(x_memo_partner_id=first.id)
        first.unlink()
        key = ("ir.actions.server", "x_memo_partner_id")
        self.assertIn(key, self.registry._paths_in_database)
        field.unlink()
        self.assertNotIn(key, self.registry._paths_in_database)
        self.assertNotIn(
            key, self.registry.cascades_into_inheritance_trees.get("res.partner", ())
        )
