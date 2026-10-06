from odoo.tests import common

from .test_read_grouping_sets import _create_mario_luigi_tasks


class TestGroupingSetsAnyValue(common.TransactionCase):
    def test_any_value_over_many2many_sets_reads_in_one_query(self):
        _create_mario_luigi_tasks(self.env)
        Task = self.env["test_read_group.task"]
        grouping_sets = [["user_ids"], ["customer_ids"], []]
        aggregates = ["integer:any_value", "__count"]
        expected = [
            Task._read_group([], grouping_set, ["integer:array_agg", "__count"])
            for grouping_set in grouping_sets
        ]

        with self.assertQueryCount(1):
            result = Task._read_grouping_sets([], grouping_sets, aggregates)

        for rows, expected_rows in zip(result, expected, strict=True):
            self.assertEqual(len(rows), len(expected_rows))
            for row, expected_row in zip(rows, expected_rows, strict=True):
                *keys, value, count = row
                *expected_keys, values, expected_count = expected_row
                self.assertEqual(keys, expected_keys)
                self.assertEqual(count, expected_count)
                self.assertIn(value, [False if v is None else v for v in values])
