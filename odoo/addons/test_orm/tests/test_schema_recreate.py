from odoo.tests.common import TransactionCase
from odoo.tools import SQL


class TestRecreatedTableSchema(TransactionCase):
    def _foreign_keys(self, table):
        self.env.cr.execute(
            """
            SELECT conrelid::regclass::text, conname
              FROM pg_constraint
             WHERE contype = 'f' AND (conrelid = %s::regclass OR confrelid = %s::regclass)
            """,
            [table, table],
        )
        return set(self.env.cr.fetchall())

    def _indexes(self, table):
        self.env.cr.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s", [table]
        )
        return {row[0] for row in self.env.cr.fetchall()}

    def _recreate(self, table):
        before = self._foreign_keys(table), self._indexes(table)
        self.env.flush_all()
        self.env.cr.execute(SQL("DROP TABLE %s CASCADE", SQL.identifier(table)))
        self.env.registry.check_tables_exist(self.env.cr)
        return before, (self._foreign_keys(table), self._indexes(table))

    def test_a_recreated_table_gets_back_its_foreign_keys_and_indexes(self):
        (fks, indexes), (fks_after, indexes_after) = self._recreate(
            "test_orm_order_line"
        )
        self.assertTrue(fks)
        self.assertEqual(fks_after, fks)
        self.assertEqual(indexes_after, indexes)

    def test_foreign_keys_into_a_recreated_table_are_restored(self):
        (fks, indexes), (fks_after, indexes_after) = self._recreate("test_orm_order")
        self.assertIn("test_orm_order_line", {table for table, _name in fks})
        self.assertEqual(fks_after, fks)
        self.assertEqual(indexes_after, indexes)
