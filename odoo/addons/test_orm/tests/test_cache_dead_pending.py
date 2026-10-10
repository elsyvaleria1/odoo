from odoo.tests import TransactionCase
from odoo.tools.misc import PENDING


class TestDeadPendingMarkers(TransactionCase):
    def _record(self, mode):
        record = self.env["test_orm.partial.compute"].create({"mode": mode})
        self.env.flush_all()
        self.env.invalidate_all()
        return record

    def _marker(self, record, fname):
        field = record._fields[fname]
        return field._get_cache(self.env).get(record.id, "<absent>")

    def _queries(self, func):
        before = self.env.cr.sql_statement_count
        func()
        return self.env.cr.sql_statement_count - before

    def test_one_fetch_answers_every_unassigned_field(self):
        record = self.env["test_orm.partial.compute"].create({"mode": "leave"})
        self.assertIs(self._marker(record, "beta"), PENDING, "create seeds the marker")
        self.env.flush_all()
        self.assertIs(
            self._marker(record, "beta"),
            PENDING,
            "the compute ran and assigned nothing, so the marker is now stale: "
            "nothing is scheduled to replace it",
        )

        first = self._queries(lambda: record.alpha)
        second = self._queries(lambda: record.beta)

        self.assertEqual(first, 1, "the first read pays for the row")
        self.assertEqual(
            second,
            0,
            "the row that answered alpha carries beta too, so a second SELECT "
            "means the marker outlived the fetch that could have cleared it",
        )
        self.assertEqual((record.alpha, record.beta), (0, 0))

    def test_a_compute_that_assigns_owns_its_value(self):
        record = self.env["test_orm.partial.compute"].create({"mode": "force"})
        self.assertEqual((record.alpha, record.beta), (1, 2))
        self.assertEqual(
            self._queries(lambda: (record.alpha, record.beta)),
            0,
            "an assigned compute needs no row at all",
        )

    def test_a_rescheduled_compute_keeps_its_marker(self):
        record = self._record("leave")
        record.alpha
        record.mode = "force"
        self.assertEqual(record.alpha, 1, "the compute, not the row, is authority")
        self.assertEqual(record.beta, 2)

    def test_a_pending_write_survives_a_fetch(self):
        record = self._record("leave")
        record.alpha = 42
        record.beta
        self.assertEqual(
            record.alpha, 42, "an unflushed write must not be replaced by the row"
        )

    def test_the_row_wins_only_once_nothing_else_owns_the_field(self):
        record = self._record("leave")
        self.env.cr.execute(
            "UPDATE test_orm_partial_compute SET beta = 7 WHERE id = %s", (record.id,)
        )
        record.alpha
        self.assertEqual(record.beta, 7, "the value taken is the one in the row")

    def test_a_batch_left_unassigned_reads_in_one_select(self):
        records = self.env["test_orm.partial.compute"].create(
            [{"mode": "leave"} for _ in range(10)]
        )
        self.assertEqual(
            self._queries(lambda: [record.alpha for record in records]),
            1,
            "the batch the compute left unassigned is fetched together",
        )
        self.assertEqual(records.mapped("alpha"), [0] * 10)

    def test_a_flushed_batch_left_unassigned_reads_in_one_select(self):
        records = self.env["test_orm.partial.compute"].create(
            [{"mode": "leave"} for _ in range(10)]
        )
        self.env.flush_all()
        self.assertEqual(self._queries(lambda: [record.beta for record in records]), 1)
        self.assertEqual(records.mapped("beta"), [0] * 10)

    def test_a_mixed_batch_reads_the_rows_it_left_in_one_select(self):
        records = self.env["test_orm.partial.compute"].create(
            [{"mode": "force" if i % 2 else "leave"} for i in range(10)]
        )
        self.env.flush_all()
        self.assertEqual(self._queries(lambda: [record.alpha for record in records]), 1)
        self.assertEqual(records.mapped("alpha"), [0, 1] * 5)

    def test_a_term_translated_field_left_unassigned_reads_its_null_row(self):
        record = self.env["test_orm.partial.compute"].create({"mode": "leave"})
        self.assertFalse(record.notes)
        self.env.flush_all()
        self.assertFalse(record.notes)

    def test_a_term_translated_field_read_by_its_own_compute(self):
        record = self.env["test_orm.partial.compute"].create({"mode": "reread"})
        self.assertFalse(record.notes)
        forced = self.env["test_orm.partial.compute"].create({"mode": "force"})
        self.assertEqual(forced.notes, "<p>forced</p>")

    def test_a_term_translated_field_left_unassigned_reads_in_every_language(self):
        record = self.env["test_orm.partial.compute"].create({"mode": "leave"})
        self.env.flush_all()
        self.assertIs(record.with_context(prefetch_langs=True).notes, False)
        self.assertFalse(record.notes)
        read = self.env["test_orm.partial.compute"].create({"mode": "leave"})
        self.assertFalse(read.notes)
        self.assertIs(read.with_context(prefetch_langs=True).notes, False)

    def test_the_translations_of_a_term_translated_field_left_unassigned(self):
        unread = self.env["test_orm.partial.compute"].create({"mode": "leave"})
        self.assertEqual(unread.get_field_translations("notes")[0], [])
        read = self.env["test_orm.partial.compute"].create({"mode": "leave"})
        self.assertFalse(read.notes)
        self.assertEqual(read.get_field_translations("notes")[0], [])
