import contextlib
import datetime
import io
import unittest
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, can_import, new_test_user

from odoo.addons.base_import.models.base_import import (
    EXTENSION_TO_READER,
    Base_ImportImport,
    ImportValidationError,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_OPTS = {"quoting": '"', "separator": ",", "has_headers": True, "encoding": "utf-8"}


def make_xlsx(headers, rows, date_columns=()):
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    for row_index in range(2, len(rows) + 2):
        for column in date_columns:
            sheet.cell(row=row_index, column=column).number_format = "yyyy-mm-dd"
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


class ImportAuditCommon(TransactionCase):
    def _wizard(self, res_model="import.char", **vals):
        vals.setdefault("res_model", res_model)
        return self.env["base_import.import"].create(vals)

    def _csv(self, content, res_model="import.char", **vals):
        return self._wizard(
            res_model, file=content, file_name="t.csv", file_type="text/csv", **vals
        )


class TestReaderDispatch(ImportAuditCommon):
    def test_extension_dispatch_is_allow_listed(self):
        calls = []
        real = Base_ImportImport._read_file
        self.patch(
            Base_ImportImport,
            "_read_file",
            lambda s, o: (calls.append(1), real(s, o))[1],
        )
        for name in ("payload.file", "payload.group", "payload.format"):
            wizard = self._wizard(
                file=b"\x00\x01junk", file_name=name, file_type="application/x-thing"
            )
            calls.clear()
            with self.assertRaises(UserError):
                wizard._read_file({"quoting": '"'})
            self.assertEqual(len(calls), 1, f"{name} re-entered _read_file")

    def test_allow_list_covers_the_extensions_the_ui_offers(self):
        self.assertEqual(
            set(EXTENSION_TO_READER),
            {"csv", "ods", "xls", "xlsm", "xlsx"},
        )

    def test_readers_return_rows_only(self):
        wizard = self._csv(b"value\nx\ny\n")
        self.assertEqual(wizard._read_file(dict(CSV_OPTS)), [["value"], ["x"], ["y"]])


class TestCleanErrors(ImportAuditCommon):
    def test_header_only_file_is_mappable_not_an_internal_error(self):
        result = self._csv(b"value\n").parse_preview(dict(CSV_OPTS))
        self.assertNotIn("error", result, result.get("error"))
        self.assertEqual(result["headers"], ["value"])
        self.assertEqual(result["preview"], [[""]])
        self.assertEqual(result["num_rows"], 0)

    def test_num_rows_counts_data_rows_only(self):
        self.assertEqual(
            self._csv(b"value\na\nb\n").parse_preview(dict(CSV_OPTS))["num_rows"], 2
        )

    def test_multi_character_text_delimiter_reports_a_clean_error(self):
        wizard = self._csv(b"a,b\n1,2\n")
        for options in ({"quoting": '""'}, {"quoting": '""', "separator": ","}):
            with self.assertRaises(ImportValidationError):
                wizard._read_csv(dict(options))

    def test_quoting_defaults_instead_of_raising_keyerror(self):
        self.assertEqual(
            self._csv(b"a,b\n1,2\n")._read_csv({"separator": ","}),
            [["a", "b"], ["1", "2"]],
        )

    def test_unexpected_errors_are_logged_and_not_shown_verbatim(self):
        wizard = self._csv(b"value\nx\n")
        self.patch(
            type(wizard),
            "_read_file",
            lambda self, options: (_ for _ in ()).throw(AttributeError("boom")),
        )
        with self.assertLogs(
            "odoo.addons.base_import.models.base_import", level="ERROR"
        ) as logs:
            result = wizard.parse_preview(dict(CSV_OPTS))
        self.assertNotIn("boom", result["error"])
        self.assertIn("could not be read", result["error"])
        self.assertTrue(any("Unexpected error" in line for line in logs.output))

    def test_expected_errors_still_reach_the_user_verbatim(self):
        wizard = self._csv(b"")
        result = wizard.parse_preview(dict(CSV_OPTS))
        self.assertIn("no content", result["error"])

    def test_ragged_rows_do_not_break_the_preview(self):
        result = self._csv(b"a,b,c\n1\n").parse_preview(dict(CSV_OPTS))
        self.assertNotIn("error", result, result.get("error"))
        self.assertEqual(len(result["preview"]), 3)


@unittest.skipUnless(can_import("openpyxl"), "openpyxl not available")
class TestSpreadsheetDateCells(ImportAuditCommon):
    def test_date_cell_in_a_float_column(self):
        wizard = self._wizard(
            "import.float",
            file=make_xlsx(["value"], [[datetime.date(2024, 1, 1)]], [1]),
            file_name="f.xlsx",
            file_type=XLSX_MIME,
        )
        result = wizard.execute_import(["value"], ["value"], {"has_headers": True})
        self.assertTrue(result.get("messages"), "expected a clean import error")

    def test_date_cell_in_a_multi_mapped_many2many_column(self):
        wizard = self._wizard(
            "res.partner",
            file=make_xlsx(
                ["a", "b"], [[datetime.date(2024, 1, 1), "Consulting"]], [1]
            ),
            file_name="m.xlsx",
            file_type=XLSX_MIME,
        )
        result = wizard.execute_import(
            ["category_id", "category_id"], ["a", "b"], {"has_headers": True}
        )
        self.assertIsInstance(result, dict)

    def test_date_cell_with_a_boolean_fallback_value(self):
        wizard = self._wizard(
            "res.partner",
            file=make_xlsx(["active"], [[datetime.date(2024, 1, 1)]], [1]),
            file_name="b.xlsx",
            file_type=XLSX_MIME,
        )
        result = wizard.execute_import(
            ["active"],
            ["active"],
            {
                "has_headers": True,
                "fallback_values": {
                    "active": {
                        "fallback_value": "true",
                        "field_model": "res.partner",
                        "field_type": "boolean",
                    }
                },
            },
        )
        self.assertIsInstance(result, dict)

    def test_selection_fallback_on_an_unknown_field_does_not_raise_keyerror(self):
        wizard = self._wizard("res.partner")
        data = wizard._handle_fallback_values(
            ["props.mysel"],
            [["bogus"]],
            {
                "props.mysel": {
                    "fallback_value": "a",
                    "field_model": "res.partner",
                    "field_type": "selection",
                    "selection": [("a", "A"), ("b", "B")],
                }
            },
        )
        self.assertEqual(data, [["a"]], "unmatched value should take the fallback")

    def test_a_stored_selection_value_is_not_treated_as_invalid(self):
        wizard = self._wizard("ir.sequence")
        data = wizard._handle_fallback_values(
            ["implementation"],
            [["no_gap"], ["Standard"], ["not_a_value"]],
            {
                "implementation": {
                    "fallback_value": "standard",
                    "field_model": "ir.sequence",
                    "field_type": "selection",
                }
            },
        )
        self.assertEqual(
            data,
            [["no_gap"], ["Standard"], ["standard"]],
            "a stored value and a label both stand; only the third is invalid",
        )

    def test_every_stored_selection_value_is_accepted_by_the_fallback_check(self):
        wizard = self._wizard("res.partner")
        converter = self.env["ir.fields.converter"]
        rejected = []
        for model_name in self.env.registry.models:
            model = self.env[model_name]
            if model._abstract or model._transient:
                continue
            for fname, field in model._fields.items():
                if field.type != "selection" or not field.store or field.readonly:
                    continue
                selection = None
                with contextlib.suppress(Exception):
                    selection = field._description_selection(self.env)
                if not selection:
                    continue
                values = [v for v, _l in selection if isinstance(v, str) and v]
                if not values:
                    continue
                accepted = frozenset(converter._get_selection_index(field))
                rejected += [
                    (model_name, fname, v) for v in values if v.lower() not in accepted
                ]
        self.assertFalse(
            rejected, f"stored values the fallback check would replace: {rejected[:10]}"
        )
        fallback = {
            "implementation": {
                "fallback_value": "standard",
                "field_model": "ir.sequence",
                "field_type": "selection",
            }
        }
        wizard._handle_fallback_values(["implementation"], [["no_gap"]], fallback)
        self.assertIn("no_gap", fallback["implementation"]["accepted_values"])

    def test_a_boolean_token_the_converter_accepts_is_not_replaced(self):
        wizard = self._wizard("res.partner")
        fallback = {
            "active": {
                "fallback_value": "false",
                "field_model": "res.partner",
                "field_type": "boolean",
            }
        }
        data = wizard._handle_fallback_values(
            ["active"],
            [["yes"], ["no"], ["1"], ["true"], ["maybe"]],
            fallback,
        )
        self.assertEqual(
            data,
            [["yes"], ["no"], ["1"], ["true"], ["false"]],
            "only the token the converter cannot read takes the fallback",
        )
        trues, falses = self.env["ir.fields.converter"]._get_boolean_tokens()
        self.assertEqual(fallback["active"]["accepted_values"], trues | falses)

    def test_a_fallback_on_a_third_field_type_leaves_the_cell_alone(self):
        wizard = self._wizard("res.partner")
        data = wizard._handle_fallback_values(
            ["name"],
            [["Acme"]],
            {
                "name": {
                    "fallback_value": "x",
                    "field_model": "res.partner",
                    "field_type": "char",
                }
            },
        )
        self.assertEqual(data, [["Acme"]])

    def test_skip_leaves_a_genuinely_invalid_cell_empty(self):
        wizard = self._wizard("ir.sequence")
        data = wizard._handle_fallback_values(
            ["implementation"],
            [["no_gap"], ["not_a_value"]],
            {
                "implementation": {
                    "fallback_value": "skip",
                    "field_model": "ir.sequence",
                    "field_type": "selection",
                }
            },
        )
        self.assertEqual(data, [["no_gap"], [None]])


class TestNameColumn(ImportAuditCommon):
    def test_name_is_read_from_the_merged_row(self):
        wizard = self._csv(
            b"city,region,partner\nParis,FR,ACME Corp\n", res_model="res.partner"
        )
        result = wizard.execute_import(
            ["city", "city", "name"], ["city", "region", "partner"], dict(CSV_OPTS)
        )
        self.assertFalse(result.get("messages"))
        self.assertEqual(result["name"], ["ACME Corp"])
        partner = self.env["res.partner"].browse(result["ids"])
        self.assertEqual(partner.city, "Paris FR")


class TestBatchWindow(ImportAuditCommon):
    def test_url_fetches_are_limited_to_the_batch(self):
        calls = []
        wizard = self._csv(
            (
                "image_1920\n"
                + "".join(f"http://example.invalid/{i}.png\n" for i in range(50))
            ).encode(),
            res_model="res.partner",
        )
        options = dict(CSV_OPTS, limit=5)
        with (
            patch.object(
                Base_ImportImport,
                "_import_file_by_url",
                lambda self, url, s, f, n: calls.append(url) or b"x",
            ),
            patch.object(
                type(self.env["res.users"]),
                "_can_import_remote_urls",
                lambda self: True,
            ),
        ):
            data, fields = wizard._convert_import_data(["image_1920"], dict(options))
            data = data[: wizard._batch_window(fields, data, 5)]
            wizard._parse_import_data(data, fields, dict(options))
        self.assertEqual(len(calls), 5)

    def test_window_keeps_one2many_continuation_rows(self):
        wizard = self._wizard("import.o2m")
        fields = ["name", "value/name"]
        data = [
            ["rec0", "line0"],
            ["", "line1"],
            ["", "line2"],
            ["rec1", "line3"],
        ]
        self.assertEqual(wizard._batch_window(fields, data, 1), 3)
        self.assertEqual(wizard._batch_window(fields, data, 4), 4)

    def test_window_is_exactly_the_limit_without_one2many_columns(self):
        wizard = self._wizard("res.partner")
        data = [[f"r{i}"] for i in range(10)]
        self.assertEqual(wizard._batch_window(["name"], data, 4), 4)
        self.assertEqual(wizard._batch_window(["name"], data, 0), 10)

    def test_one2many_import_across_a_batch_boundary(self):
        csv = b"name,value/name\nparent A,l1\n,l2\n,l3\nparent B,l4\n"
        wizard = self._csv(csv, res_model="import.o2m")
        result = wizard.execute_import(
            ["name", "value/name"], ["name", "value/name"], dict(CSV_OPTS, limit=1)
        )
        self.assertFalse(result.get("messages"))
        parent = self.env["import.o2m"].browse(result["ids"])
        self.assertEqual(parent.name, "parent A")
        self.assertEqual(sorted(parent.value.mapped("name")), ["l1", "l2", "l3"])


class TestMappingSuggestions(ImportAuditCommon):
    def test_empty_column_still_gets_a_fuzzy_suggestion(self):
        populated = self._csv(
            b"Functon,other\nboss,x\nlead,y\n", res_model="res.partner"
        )
        empty = self._csv(b"Functon,other\n,x\n,y\n", res_model="res.partner")
        self.assertEqual(
            populated.parse_preview(dict(CSV_OPTS))["matches"],
            empty.parse_preview(dict(CSV_OPTS))["matches"],
        )

    def test_stale_saved_mapping_is_ignored(self):
        self.env["base_import.mapping"].create(
            {
                "res_model": "import.char",
                "column_name": "value",
                "field_name": "gone_field",
            }
        )
        result = self._csv(b"value\nx\n").parse_preview(dict(CSV_OPTS))
        self.assertEqual(result["matches"], {0: ["value"]})

    def test_negative_integers_are_typed_as_integer(self):
        wizard = self.env["base_import.import"]
        self.assertEqual(
            wizard._extract_header_types(["-1", "2"], {}),
            ["integer", "float", "monetary"],
        )

    def test_non_ascii_digits_are_not_typed_as_integer(self):
        wizard = self.env["base_import.import"]
        self.assertNotIn("integer", wizard._extract_header_types(["٣", "٤"], {}))
        self.assertNotIn("integer", wizard._extract_header_types(["²"], {}))


class TestMappingStorage(ImportAuditCommon):
    def test_unmapped_columns_are_not_stored(self):
        wizard = self._csv(b"value,ignored\nhello,x\n")
        wizard.execute_import(["value", False], ["value", "ignored"], dict(CSV_OPTS))
        rows = self.env["base_import.mapping"].search(
            [("res_model", "=", "import.char")]
        )
        self.assertEqual(
            [(r.column_name, r.field_name) for r in rows], [("value", "value")]
        )

    def test_remapping_a_column_updates_in_place(self):
        wizard = self._csv(b"value\nhello\n")
        wizard.execute_import(["value"], ["value"], dict(CSV_OPTS))
        wizard2 = self._csv(b"value\nhello\n")
        wizard2.execute_import(["id"], ["value"], dict(CSV_OPTS))
        rows = self.env["base_import.mapping"].search(
            [("res_model", "=", "import.char")]
        )
        self.assertEqual(len(rows), 1, "the unique constraint must be respected")
        self.assertEqual(rows.field_name, "id")


class TestFieldsTree(ImportAuditCommon):
    def test_depth_is_clamped(self):
        wizard = self.env["base_import.import"]
        reference = wizard.get_fields_tree("res.partner")
        self.assertEqual(wizard.get_fields_tree("res.partner", depth=99), reference)

    def test_properties_subcolumns_are_still_published(self):
        tree = self.env["base_import.import"].get_fields_tree("import.properties")
        by_name = {f["name"]: f for f in tree}
        self.assertIn("properties", by_name)
        self.assertEqual(by_name["properties"]["type"], "properties")


class TestIsolation(ImportAuditCommon):
    def test_a_user_cannot_read_another_users_import(self):
        alice = new_test_user(self.env, login="audit_alice", groups="base.group_user")
        bob = new_test_user(self.env, login="audit_bob", groups="base.group_user")
        record = (
            self.env["base_import.import"]
            .with_user(alice)
            .create(
                {
                    "res_model": "res.partner",
                    "file": b"secret",
                    "file_name": "payroll.csv",
                }
            )
        )
        self.env.flush_all()
        self.assertFalse(
            self.env["base_import.import"]
            .with_user(bob)
            .search([("id", "=", record.id)])
        )

    def test_a_user_can_still_use_their_own_import(self):
        alice = new_test_user(self.env, login="audit_alice2", groups="base.group_user")
        wizard = (
            self.env["base_import.import"]
            .with_user(alice)
            .create(
                {
                    "res_model": "import.char",
                    "file": b"value\nx\n",
                    "file_name": "t.csv",
                    "file_type": "text/csv",
                }
            )
        )
        self.env.flush_all()
        result = wizard.parse_preview(dict(CSV_OPTS))
        self.assertNotIn("error", result, result.get("error"))
