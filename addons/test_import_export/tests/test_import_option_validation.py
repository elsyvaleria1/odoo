import unittest
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import BaseCase, TransactionCase, can_import


class ImportOptionValidation(TransactionCase):
    _CSV = b"value\nA\nB\nC\nD\n"
    _OPTS = {"has_headers": True, "quoting": '"', "separator": ",", "encoding": "utf-8"}

    def _imp(self, res_model="import.char", **vals):
        vals.setdefault("res_model", res_model)
        vals.setdefault("file", self._CSV)
        vals.setdefault("file_name", "x.csv")
        vals.setdefault("file_type", "text/csv")
        return self.env["base_import.import"].create(vals)

    def _run(self, **options):
        return self._imp().execute_import(
            ["value"], ["Value"], dict(self._OPTS, **options), dryrun=True
        )

    def _message(self, result):
        self.assertTrue(
            result.get("messages"), "expected a reported error, got %s" % result
        )
        return result["messages"][0]["message"]

    def test_non_numeric_limit_is_reported_not_raised(self):
        self.assertIn("Batch limit", self._message(self._run(limit="abc")))

    def test_negative_limit_is_reported_not_raised(self):
        self.assertIn("Batch limit", self._message(self._run(limit=-5)))

    def test_numeric_string_limit_is_accepted(self):
        options = dict(self._OPTS, limit="2")
        result = self._imp().execute_import(["value"], ["Value"], options, dryrun=True)
        self.assertFalse(result.get("messages"), result)
        self.assertEqual(len(result["ids"]), 2)

    def test_non_numeric_limit_does_not_blame_the_file(self):
        result = self._imp().parse_preview(dict(self._OPTS, limit="abc"))
        self.assertIn("Batch limit", result["error"])
        self.assertNotIn("could not be read", result["error"])

    def test_every_falsy_limit_means_no_limit(self):
        for empty in (None, False, "", 0):
            with self.subTest(limit=empty):
                result = self._run(limit=empty)
                self.assertFalse(result.get("messages"), result)
                self.assertEqual(len(result["ids"]), 4)

    def test_an_absent_limit_is_left_absent(self):
        options = dict(self._OPTS)
        self.env["base_import.import"]._normalize_row_window_options(options)
        self.assertNotIn("limit", options)

    def test_an_empty_skip_is_zero(self):
        options = dict(self._OPTS, skip=None)
        self.env["base_import.import"]._normalize_row_window_options(options)
        self.assertEqual(options["skip"], 0)

    def test_negative_skip_is_refused_rather_than_silently_reversed(self):
        self.assertIn("Start at line", self._message(self._run(skip=-2)))

    def test_positive_skip_still_selects_from_the_front(self):
        result = self._imp().execute_import(
            ["value"], ["Value"], dict(self._OPTS, skip=2), dryrun=False
        )
        self.assertFalse(result.get("messages"), result)
        self.assertEqual(
            self.env["import.char"].browse(result["ids"]).mapped("value"), ["C", "D"]
        )

    def _run_named(self, **options):
        imp = self._imp("res.partner", file=b"name\nA\nB\nC\nD\n")
        return imp.execute_import(
            ["name"], ["Name"], dict(self._OPTS, **options), dryrun=True
        )

    def test_skip_past_end_of_file_does_not_allocate_per_skipped_row(self):
        result = self._run_named(skip=5_000_000)
        self.assertEqual(result["ids"], [])
        self.assertEqual(result["name"], [])

    def test_skip_within_the_file_still_pads_to_absolute_rows(self):
        self.assertEqual(self._run_named(skip=2)["name"], ["", "", "C", "D"])

    def test_non_string_field_mapping_is_reported_not_raised(self):
        result = self._imp().execute_import(
            [123, "value"], ["A", "Value"], dict(self._OPTS), dryrun=True
        )
        self.assertIn("Column 1", self._message(result))

    def test_unknown_res_model_is_a_user_error_not_a_key_error(self):
        for entry_point in (
            lambda imp: imp.parse_preview(dict(self._OPTS)),
            lambda imp: imp.execute_import(["value"], ["Value"], dict(self._OPTS)),
        ):
            with self.subTest(entry_point=entry_point), self.assertRaises(UserError):
                entry_point(self._imp("nope.nope"))

    def test_missing_res_model_is_a_user_error_not_a_key_error(self):
        imp = self.env["base_import.import"].create(
            {"file": self._CSV, "file_name": "x.csv", "file_type": "text/csv"}
        )
        with self.assertRaises(UserError):
            imp.parse_preview(dict(self._OPTS))

    def test_get_fields_tree_refuses_an_unknown_model(self):
        with self.assertRaises(UserError):
            self.env["base_import.import"].get_fields_tree("nope.nope")


@unittest.skipUnless(can_import("odf"), "odfpy not installed")
class ODSCellFidelity(BaseCase):
    def _sheet(self, rows):
        import io

        from odf.opendocument import OpenDocumentSpreadsheet
        from odf.table import Table, TableCell, TableRow
        from odf.text import P

        from odoo.addons.base_import.models.odf_ods_reader import ODSReader

        doc = OpenDocumentSpreadsheet()
        table = Table(name="Sheet1")
        for line in rows:
            row = TableRow()
            for text, repeat in line:
                cell = TableCell()
                if repeat != 1:
                    cell.setAttribute("numbercolumnsrepeated", str(repeat))
                if text:
                    cell.addElement(P(text=text))
                row.addElement(cell)
            table.addElement(row)
        doc.spreadsheet.addElement(table)
        buf = io.BytesIO()
        doc.write(buf)
        return ODSReader(file=io.BytesIO(buf.getvalue())).get_sheet("Sheet1")

    def test_a_cell_starting_with_hash_is_data_not_a_comment(self):
        self.assertEqual(
            self._sheet(
                [
                    [("name", 1), ("colour", 1), ("qty", 1)],
                    [("Alice", 1), ("#FF0000", 1), ("1", 1)],
                ]
            ),
            [["name", "colour", "qty"], ["Alice", "#FF0000", "1"]],
        )

    def test_repeated_cells_at_the_end_of_a_row_are_expanded(self):
        self.assertEqual(
            self._sheet([[("a", 1), ("b", 3)]]),
            [["a", "b", "b", "b"]],
        )

    def test_a_blank_last_cell_contributes_exactly_one_column(self):
        self.assertEqual(
            self._sheet([[("a", 1), ("b", 1), ("", 1013)]]),
            [["a", "b", ""]],
            "the used-range filler must not be expanded",
        )
        self.assertEqual(
            self._sheet(
                [[("h1", 1), ("h2", 1), ("h3", 1)], [("a", 1), ("b", 1), ("", 1)]]
            ),
            [["h1", "h2", "h3"], ["a", "b", ""]],
            "an ordinary trailing empty column must keep the row's width",
        )

    def test_repeat_count_is_still_capped(self):
        from odoo.addons.base_import.models.odf_ods_reader import MAX_CELL_REPEAT

        row = self._sheet([[("x", 10**8), ("", 1)]])[0]
        self.assertEqual(len(row), MAX_CELL_REPEAT + 1)


class ParsedFileCache(TransactionCase):
    _OPTS = {"has_headers": True, "quoting": '"', "separator": ",", "encoding": "utf-8"}

    def setUp(self):
        super().setUp()
        from odoo.addons.base_import.models.base_import import PARSED_FILE_CACHE

        self.cache = PARSED_FILE_CACHE
        self.cache.clear()
        self.addCleanup(self.cache.clear)

    def _imp(self, file):
        return self.env["base_import.import"].create(
            {
                "res_model": "import.char",
                "file": file,
                "file_name": "x.csv",
                "file_type": "text/csv",
            }
        )

    def _reader_calls(self):
        model = self.env["base_import.import"]
        return patch.object(
            type(model),
            "_read_file_uncached",
            autospec=True,
            side_effect=type(model)._read_file_uncached,
        )

    def test_the_same_file_is_parsed_once(self):
        imp = self._imp(b"value\nA\nB\n")
        with self._reader_calls() as reader:
            for _ in range(3):
                imp._read_file(dict(self._OPTS))
            self.assertEqual(reader.call_count, 1)

    def test_a_new_file_on_the_same_record_is_reparsed(self):
        imp = self._imp(b"value\nA\n")
        self.assertEqual(imp._read_file(dict(self._OPTS)), [["value"], ["A"]])
        imp.write({"file": b"value\nB\n"})
        self.assertEqual(imp._read_file(dict(self._OPTS)), [["value"], ["B"]])

    def test_options_a_reader_writes_are_replayed_on_a_hit(self):
        imp = self._imp("value;note\nA;caf\u00e9\n".encode("utf-8"))
        miss, hit = {"has_headers": True}, {"has_headers": True}
        imp._read_file(miss)
        imp._read_file(hit)
        self.assertEqual(hit, miss)
        self.assertEqual(hit["separator"], ";")

    def test_a_caller_cannot_corrupt_the_entry(self):
        imp = self._imp(b"value\nA\nB\n")
        first = imp._read_file(dict(self._OPTS))
        first.pop(0)
        self.assertEqual(imp._read_file(dict(self._OPTS)), [["value"], ["A"], ["B"]])

    def test_a_full_import_does_not_mutate_the_cached_rows(self):
        import copy

        imp = self._imp(b"name,image_1920\nA,photo.png\nB,other.png\nC,third.png\n")
        imp.res_model = "res.partner"
        self.cache.clear()
        options = dict(self._OPTS)
        pristine = copy.deepcopy(imp._read_file(dict(options)))
        key = imp._parsed_file_key(dict(options))

        imp.execute_import(
            ["name", "image_1920"],
            ["name", "image"],
            dict(options, limit=2),
            dryrun=True,
        )
        imp.execute_import(
            ["name", "image_1920"],
            ["name", "image"],
            dict(options, limit=2, skip=2),
            dryrun=True,
        )
        self.assertEqual(self.cache.get(key)[0], pristine)

    def test_a_caller_cannot_corrupt_the_replayed_options(self):
        imp = self._imp(b"value;note\nA;x\n")
        first = {"has_headers": True}
        imp._read_file(first)
        self.assertEqual(first["separator"], ";")
        first.setdefault("sheets", []).append("INJECTED")
        first["separator"] = "\t"

        second = {"has_headers": True}
        imp._read_file(second)
        self.assertNotIn("INJECTED", second.get("sheets", []))
        self.assertEqual(second["separator"], ";")

    def test_the_same_bytes_under_a_different_name_are_not_shared(self):
        payload = b"value\nA\n"
        as_csv = self._imp(payload)
        as_xlsx = self.env["base_import.import"].create(
            {
                "res_model": "import.char",
                "file": payload,
                "file_name": "x.xlsx",
                "file_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            }
        )
        self.assertEqual(as_csv._read_file(dict(self._OPTS)), [["value"], ["A"]])
        with self.assertRaises(UserError):
            as_xlsx._read_file(dict(self._OPTS))

    def test_a_file_over_the_cell_budget_is_not_kept(self):
        from odoo.addons.base_import.models.base_import import (
            PARSED_FILE_CACHE_MAX_CELLS,
        )

        rows = PARSED_FILE_CACHE_MAX_CELLS + 1
        imp = self._imp(b"value\n" + b"A\n" * rows)
        with self._reader_calls() as reader:
            imp._read_file(dict(self._OPTS))
            imp._read_file(dict(self._OPTS))
            self.assertEqual(reader.call_count, 2)


class SpreadsheetDateColumnTyping(TransactionCase):
    def test_native_dates_do_not_invent_a_date_format(self):
        import datetime

        options = {"has_headers": True}
        types = self.env["base_import.import"]._extract_header_types(
            [datetime.date(2024, 1, 15), datetime.date(2024, 2, 20)], options
        )
        self.assertEqual(types, ["date", "datetime"], "the typing must not change")
        self.assertNotIn("date_format", options)

    def test_a_textual_date_column_still_sets_the_format(self):
        options = {"has_headers": True}
        self.env["base_import.import"]._extract_header_types(
            ["2024-01-15", "2024-02-20"], options
        )
        self.assertEqual(options["date_format"], "%Y-%m-%d")
