from psycopg.errors import NumericValueOutOfRange

from odoo.db import schema as sql
from odoo.libs.sql import INT4_MAX, SQL
from odoo.orm.runtime._backend_memory_constraints import _check_column_values
from odoo.tests import common
from odoo.tools import mute_logger

PAST_INT4 = INT4_MAX + 6
FIVE_GB = 5_000_000_000


class TestBigintField(common.TransactionCase):
    def _column_types(self, table):
        return {
            name: column["udt_name"]
            for name, column in sql.get_table_columns(self.env.cr, table).items()
        }

    def _raw(self, record, column):
        self.env.flush_all()
        return self.env.execute_query(
            SQL(
                "SELECT %s FROM test_orm_bigint WHERE id = %s",
                SQL.identifier(column),
                record.id,
            )
        )[0][0]

    def test_a_bigint_field_has_an_int8_column_and_a_plain_one_keeps_int4(self):
        columns = self._column_types("test_orm_bigint")
        self.assertEqual(columns["amount"], "int8")
        self.assertEqual(columns["count"], "int4")

    def test_a_value_past_int4_is_stored_and_read_back_exactly(self):
        record = self.env["test_orm.bigint"].create({"amount": FIVE_GB})
        self.assertEqual(self._raw(record, "amount"), FIVE_GB)
        record.invalidate_recordset()
        self.assertEqual(record.amount, FIVE_GB)
        self.assertIs(type(record.amount), int)

    def test_a_search_compares_past_int4(self):
        Bigint = self.env["test_orm.bigint"]
        small = Bigint.create({"amount": 1})
        large = Bigint.create({"amount": FIVE_GB})
        found = Bigint.search(
            [("amount", ">", INT4_MAX), ("id", "in", (small | large).ids)]
        )
        self.assertEqual(found, large)

    def test_read_answers_a_value_past_int4_as_a_float_as_for_every_integer(self):
        record = self.env["test_orm.bigint"].create({"amount": FIVE_GB})
        self.assertEqual(record.read(["amount"])[0]["amount"], float(FIVE_GB))

    def test_a_stored_related_field_takes_the_width_of_its_target(self):
        self.assertEqual(self._column_types("test_orm_bigint")["parent_amount"], "int8")
        Bigint = self.env["test_orm.bigint"]
        child = Bigint.create({"parent_id": Bigint.create({"amount": FIVE_GB}).id})
        self.assertEqual(self._raw(child, "parent_amount"), FIVE_GB)

    @mute_logger("odoo.db.cursor")
    def test_an_int4_field_still_refuses_a_value_past_its_range(self):
        with self.assertRaises(NumericValueOutOfRange), self.env.cr.savepoint():
            self.env["test_orm.bigint"].create({"count": PAST_INT4})
            self.env.flush_all()

    def test_an_int4_column_of_an_existing_database_widens_and_keeps_its_values(self):
        Bigint = self.env["test_orm.bigint"]
        record = Bigint.create({"amount": 123})
        self.env.flush_all()
        self.env.cr.execute(
            SQL("ALTER TABLE test_orm_bigint ALTER COLUMN amount TYPE int4")
        )
        column = sql.get_table_columns(self.env.cr, "test_orm_bigint")["amount"]
        self.assertEqual(column["udt_name"], "int4")
        Bigint._fields["amount"].update_db_column(Bigint, column)
        self.assertEqual(self._column_types("test_orm_bigint")["amount"], "int8")
        self.assertEqual(self._raw(record, "amount"), 123)
        record.amount = FIVE_GB
        self.assertEqual(self._raw(record, "amount"), FIVE_GB)

    def test_the_memory_backend_bounds_each_width_as_postgresql_does(self):
        Bigint = self.env["test_orm.bigint"]
        _check_column_values(Bigint, [{"amount": FIVE_GB, "count": INT4_MAX}])
        with self.assertRaisesRegex(NumericValueOutOfRange, "^integer out of range$"):
            _check_column_values(Bigint, [{"count": PAST_INT4}])
        with self.assertRaisesRegex(NumericValueOutOfRange, "^bigint out of range$"):
            _check_column_values(Bigint, [{"amount": 2**63}])


class TestAttachmentFileSize(common.TransactionCase):
    def test_an_attachment_records_a_size_past_int4(self):
        columns = sql.get_table_columns(self.env.cr, "ir_attachment")
        self.assertEqual(columns["file_size"]["udt_name"], "int8")
        attachment = self.env["ir.attachment"].create({"name": "big", "raw": b"x"})
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE ir_attachment SET file_size = %s WHERE id = %s",
                FIVE_GB,
                attachment.id,
            )
        )
        attachment.invalidate_recordset(["file_size"])
        self.assertEqual(attachment.file_size, FIVE_GB)
