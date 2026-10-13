from odoo.db import schema as sql
from odoo.libs.sql import get_index_name
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestIndexMethodMigration(TransactionCase):
    def _index_method(self, indexname):
        self.cr.execute(
            """
            SELECT am.amname
              FROM pg_class idx
              JOIN pg_am am ON am.oid = idx.relam
             WHERE idx.relname = %s
            """,
            [indexname],
        )
        row = self.cr.fetchone()
        return row[0] if row else None

    def test_index_rebuilt_when_method_changes(self):
        registry = self.registry
        if not registry.has_trigram:
            self.skipTest("pg_trgm extension is required for trigram indexes")

        cr = self.cr
        field = registry["res.partner"]._fields["ref"]
        indexname = get_index_name("res_partner", "ref")

        sql.drop_index(cr, indexname, "res_partner")
        sql.create_index(cr, indexname, "res_partner", ['"ref"'], "btree")
        self.assertEqual(self._index_method(indexname), "btree")

        original_index = field.index
        field.index = "trigram"
        self.addCleanup(setattr, field, "index", original_index)

        registry.update_declared_field_indexes(cr, ["res.partner"])

        self.assertEqual(self._index_method(indexname), "gin")

    def test_a_disabled_declaration_keeps_an_existing_index(self):
        field = self.registry["res.partner"]._fields["ref"]
        indexname = get_index_name("res_partner", "ref")
        sql.drop_index(self.cr, indexname, "res_partner")
        sql.create_index(self.cr, indexname, "res_partner", ['"ref"'], "btree")
        original_index = field.index
        field.index = False
        self.addCleanup(setattr, field, "index", original_index)

        self.registry.update_declared_field_indexes(self.cr, ["res.partner"])

        self.assertEqual(self._index_method(indexname), "btree")

    def test_a_translated_unique_declaration_warns_and_keeps_the_index(self):
        field = self.registry["res.partner"]._fields["ref"]
        indexname = get_index_name("res_partner", "ref")
        sql.drop_index(self.cr, indexname, "res_partner")
        sql.create_index(self.cr, indexname, "res_partner", ['"ref"'], "btree")
        original_index, original_translate = field.index, field.translate
        field.index, field.translate = "unique", True
        self.addCleanup(setattr, field, "index", original_index)
        self.addCleanup(setattr, field, "translate", original_translate)

        with self.assertLogs("odoo.schema", level="WARNING") as logged:
            self.registry.update_declared_field_indexes(self.cr, ["res.partner"])

        self.assertIn("unique index is not supported", "\n".join(logged.output))
        self.assertEqual(self._index_method(indexname), "btree")
