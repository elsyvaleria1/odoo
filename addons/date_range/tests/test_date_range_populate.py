from odoo.tests.common import TransactionCase
from odoo.tools import SQL
from odoo.tools.populate import populate_models


class TestDateRangePopulate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DateRange = cls.env["date.range"]
        cls.DateRange.search([]).unlink()

    def _range(self, allow_overlap):
        date_range_type = self.env["date.range.type"].create(
            {"name": f"Populated {allow_overlap}", "allow_overlap": allow_overlap}
        )
        return self.DateRange.create(
            {
                "name": "FY2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
                "type_id": date_range_type.id,
            }
        )

    def _overlapping_pairs(self):
        [(pairs,)] = self.env.execute_query(
            SQL(
                """
                SELECT count(*)
                  FROM date_range a
                  JOIN date_range b
                    ON a.id < b.id
                   AND a.type_id = b.type_id
                   AND COALESCE(a.company_id, 0) = COALESCE(b.company_id, 0)
                   AND COALESCE(a.parent_id, 0) = COALESCE(b.parent_id, 0)
                   AND daterange(a.date_start, a.date_end, '[]')
                       && daterange(b.date_start, b.date_end, '[]')
                 WHERE NOT COALESCE(a.allow_overlap, FALSE)
                """
            )
        )
        return pairs

    def test_populate_does_not_commit_ranges_that_overlap(self):
        self._range(allow_overlap=False)
        self.env.flush_all()

        with self.assertLogs("odoo.tools.populate", "WARNING") as logs:
            populate_models({self.DateRange: 2}, ord("_"))
        self.env.cr.execute(SQL("SET CONSTRAINTS ALL IMMEDIATE"))

        self.assertIn("date_range_date_range_no_overlap", logs.output[-1])
        self.assertEqual(self._overlapping_pairs(), 0)
        self.assertEqual(self.DateRange.search_count([]), 1)

    def test_populate_copies_ranges_of_a_type_that_allows_overlap(self):
        self._range(allow_overlap=True)
        self.env.flush_all()

        populate_models({self.DateRange: 2}, ord("_"))
        self.env.cr.execute(SQL("SET CONSTRAINTS ALL IMMEDIATE"))
        self.env.invalidate_all()

        self.assertEqual(self.DateRange.search_count([]), 3)
        [(constraints,)] = self.env.execute_query(
            SQL(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid = 'date_range'::regclass AND contype = 'x'"
            )
        )
        self.assertEqual(constraints, 1)
