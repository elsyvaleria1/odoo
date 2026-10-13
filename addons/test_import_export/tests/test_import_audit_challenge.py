
import base64
import contextlib
import io
import time
import unittest
import zipfile
from pathlib import Path

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, can_import


class ImportAuditChallenge(TransactionCase):
    def _imp(self, data=b"", name="t.csv", ftype="text/csv", model="res.partner"):
        return self.env["base_import.import"].create(
            {
                "res_model": model,
                "file": data,
                "file_name": name,
                "file_type": ftype,
            }
        )

    _OPTS = {"has_headers": True, "quoting": '"', "separator": ","}

    def test_c3_short_row_reports_import_error_not_indexerror(self):
        imp = self._imp(b"name,function\nBob,CEO\nAlice\n")
        try:
            result = imp.execute_import(
                ["name", "function"],
                ["name", "function"],
                dict(self._OPTS),
                dryrun=True,
            )
        except IndexError:
            self.fail("C3 CONFIRMED: short row raised IndexError out of execute_import")
        self.assertTrue(result.get("messages"), "expected a clean import message")

    def test_c4_relational_path_on_scalar_field_is_rejected_cleanly(self):
        imp = self._imp(b"a\nx\n")
        try:
            result = imp.execute_import(
                ["name/foo"], ["a"], dict(self._OPTS), dryrun=True
            )
        except KeyError as e:
            self.fail(f"C4 CONFIRMED: KeyError({e}) escaped execute_import")
        self.assertTrue(result.get("messages"), "the bad mapping must be reported")
        self.assertIn("not a relation", result["messages"][0]["message"])
        self.assertFalse(
            result.get("ids"), "nothing may be created from an unusable mapping"
        )

    def test_c4_unknown_leaf_is_still_left_to_load(self):
        imp = self._imp(b"a\nx\n")
        result = imp.execute_import(["nope"], ["a"], dict(self._OPTS), dryrun=True)
        self.assertIn("does not exist", result["messages"][0]["message"])

    def test_c5_header_only_file_still_suggests_mappings(self):
        types = self.env["base_import.import"]._extract_header_types([], {})
        self.assertEqual(
            types, ["all"], "C5 CONFIRMED: empty preview typed as %r" % (types,)
        )

        imp = self._imp(b"Functon,Displai Name\n")
        result = imp.parse_preview({"has_headers": True})
        self.assertFalse(result.get("error"))
        self.assertTrue(
            result.get("matches"),
            "C5 CONFIRMED: header-only file produced no suggestions at all",
        )

    def test_c5_control_same_file_with_data_does_suggest(self):
        imp = self._imp(b"Functon,Displai Name\nCEO,Bob\n")
        result = imp.parse_preview({"has_headers": True})
        self.assertEqual(result["matches"].get(0), ["function"])

    def test_c6_batch_flag_matches_row_count_vs_limit(self):
        imp = self._imp(b"name\n" + b"".join(b"r%d\n" % i for i in range(30)))
        wrong = []
        for limit in (5, 10, 20, 29, 30, 31, 40, 50, 100):
            preview = imp.parse_preview({"has_headers": True, "limit": limit}, count=10)
            self.assertEqual(preview["num_rows"], 30)
            expected = limit < 30
            if preview["batch"] is not expected:
                wrong.append((limit, preview["batch"], expected))
        self.assertFalse(
            wrong, "C6 CONFIRMED, wrong for (limit, got, expected): %r" % (wrong,)
        )

    def test_c7_saved_mapping_matches_padded_header(self):
        self.env["base_import.mapping"].search(
            [("res_model", "=", "res.partner")]
        ).unlink()
        self.env["base_import.mapping"].create(
            {"res_model": "res.partner", "column_name": "kunde nr", "field_name": "ref"}
        )
        imp = self._imp(b'" Kunde Nr ",name\nA,Bob\n')
        result = imp.parse_preview({"has_headers": True})
        self.assertEqual(
            result["matches"].get(0),
            ["ref"],
            "C7 CONFIRMED: padded header missed its saved mapping",
        )

    def test_c7_control_unpadded_header_matches(self):
        self.env["base_import.mapping"].search(
            [("res_model", "=", "res.partner")]
        ).unlink()
        self.env["base_import.mapping"].create(
            {"res_model": "res.partner", "column_name": "kunde nr", "field_name": "ref"}
        )
        imp = self._imp(b"Kunde Nr,name\nA,Bob\n")
        self.assertEqual(
            imp.parse_preview({"has_headers": True})["matches"].get(0), ["ref"]
        )

    def test_c8_savepoint_is_released_when_conversion_crashes(self):
        imp = self._imp(b"name,function\nBob,CEO\nAlice\n")
        depth_before = self.env.cr._savepoint_depth
        with contextlib.suppress(Exception):
            imp.execute_import(
                ["name", "function"],
                ["name", "function"],
                dict(self._OPTS),
                dryrun=True,
            )
        self.assertEqual(
            self.env.cr._savepoint_depth,
            depth_before,
            "C8 CONFIRMED: savepoint depth %d -> %d, never released after the crash"
            % (depth_before, self.env.cr._savepoint_depth),
        )

    def test_d2_unique_constraint_exists_so_dedup_loop_is_dead(self):
        self.env.cr.execute("""
            SELECT 1 FROM pg_constraint
             WHERE conrelid = 'base_import_mapping'::regclass
               AND contype = 'u'
               AND pg_get_constraintdef(oid) ILIKE '%%res_model, column_name%%'
        """)
        self.assertTrue(
            self.env.cr.fetchone(),
            "D2 WITHDRAWN: no unique constraint, the dedup loop is live",
        )

    def test_d3_type_filter_keeps_relations_and_drops_mismatched_scalars(self):
        Imp = self.env["base_import.import"]
        tree = Imp.get_fields_tree("res.partner")
        kept = Imp._filter_fields_by_types(tree, ["integer"])

        relational = {"many2one", "one2many", "many2many"}
        scalars = [f for f in kept if f["type"] not in relational]
        self.assertTrue(
            all(f["type"] in ("integer", "id") for f in scalars),
            "mismatched scalar kept: %r" % ([f["name"] for f in scalars],),
        )
        self.assertEqual(
            len([f for f in kept if f["type"] in relational]),
            len([f for f in tree if f["type"] in relational]),
        )

    def test_d3_all_sentinel_keeps_everything(self):
        Imp = self.env["base_import.import"]
        tree = Imp.get_fields_tree("res.partner")
        self.assertEqual(len(Imp._filter_fields_by_types(tree, ["all"])), len(tree))

    def test_a1_get_fields_tree_checks_access_on_the_entry_model(self):
        user = self.env["res.users"].create(
            {
                "name": "audit probe",
                "login": "audit_probe_user",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        model = "ir.mail_server"
        self.assertFalse(self.env[model].with_user(user).has_access("read"))
        with self.assertRaises(AccessError):
            self.env["base_import.import"].with_user(user).get_fields_tree(model)

    def test_a1_readable_model_still_works_and_recursion_is_not_checked(self):
        user = self.env["res.users"].create(
            {
                "name": "audit probe 2",
                "login": "audit_probe_user_2",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        Imp = self.env["base_import.import"].with_user(user)
        tree = Imp.get_fields_tree("res.partner")
        self.assertTrue(tree)
        reached = set()

        def walk(nodes):
            for node in nodes:
                if node.get("comodel_name"):
                    reached.add(node["comodel_name"])
                walk(node.get("fields") or [])

        walk(tree)
        unreadable = [
            m
            for m in reached
            if m in self.env and not self.env[m].with_user(user).has_access("read")
        ]
        self.assertTrue(
            unreadable,
            "expected the tree to still descend into models the user cannot read",
        )


class ImportAuditChallengePerf(TransactionCase):
    def test_p1_encoding_detection_is_not_linear_in_file_size(self):
        import chardet

        from odoo.libs.documents import guess_encoding

        data = (
            b"name,ref\n"
            + b"".join(b"Row %d,R%d\n" % (i, i) for i in range(150000))
            + "café déjà,R\n".encode()
        )

        start = time.perf_counter()
        detected = guess_encoding(data)
        elapsed = time.perf_counter() - start

        self.assertEqual(detected.lower(), chardet.detect(data)["encoding"].lower())
        self.assertTrue(data.decode(detected).endswith("café déjà,R\n"))
        self.assertLess(
            elapsed,
            1.0,
            "P1 REGRESSED: detection took %.1fs on %.1f MiB"
            % (elapsed, len(data) / 2**20),
        )

    def test_p2_multi_mapping_does_not_resolve_types_per_row(self):
        imp = self.env["base_import.import"].create({"res_model": "res.partner"})
        rows = [["a%d" % i, "b%d" % i, "c%d" % i] for i in range(20000)]
        start = time.perf_counter()
        imp.with_context(import_options={})._handle_multi_mapping(
            ["name", "comment", "ref"], rows
        )
        elapsed = time.perf_counter() - start
        self.assertLess(
            elapsed,
            0.08,
            "P2 CONFIRMED: %.3fs for 20k rows x 3 fields; hoisting the type "
            "resolution out of the loop measures ~7x faster" % elapsed,
        )


@unittest.skipUnless(can_import("odf"), "odfpy not installed")
class ODSReaderChallenge(TransactionCase):
    _CSV = b"name,note,qty\nAlice,plain text,1\nBob,dup row,2\nCarol,cafe deja,3\n"

    def _ods(self, transform=None):
        from odf.opendocument import OpenDocumentSpreadsheet
        from odf.table import Table, TableCell, TableRow
        from odf.text import P

        doc = OpenDocumentSpreadsheet()
        table = Table(name="Sheet1")
        for line in self._CSV.decode().strip().split("\n"):
            row = TableRow()
            for cell_text in line.split(","):
                cell = TableCell()
                cell.addElement(P(text=cell_text))
                row.addElement(cell)
            row.addElement(TableCell())
            table.addElement(row)
        doc.spreadsheet.addElement(table)

        buf = io.BytesIO()
        doc.write(buf)
        raw = buf.getvalue()
        if transform is None:
            return raw

        zin = zipfile.ZipFile(io.BytesIO(raw))
        content = transform(zin.read("content.xml").decode("utf-8"))
        out = io.BytesIO()
        zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
        for item in zin.infolist():
            payload = zin.read(item.filename)
            if item.filename == "content.xml":
                payload = content.encode("utf-8")
            zout.writestr(item, payload)
        zout.close()
        return out.getvalue()

    def _read(self, raw):
        from odoo.addons.base_import.models import odf_ods_reader

        reader = odf_ods_reader.ODSReader(file=io.BytesIO(raw))
        return reader.get_sheet(next(iter(reader.sheets)))

    def test_c1_cell_with_styled_span_is_readable(self):
        raw = self._ods(
            lambda c: c.replace(
                "<text:p>plain text</text:p>",
                '<text:p>plain <text:span text:style-name="T1">bold</text:span> tail</text:p>',
                1,
            )
        )
        try:
            rows = self._read(raw)
        except AttributeError as e:
            self.fail("C1 CONFIRMED: styled span raises AttributeError(%s)" % e)
        flat = [cell for row in rows for cell in row]
        self.assertIn(
            "plain bold tail",
            flat,
            "C1 PARTIAL: no crash, but the span text was lost: %r" % (rows,),
        )

    def test_c1_end_to_end_user_sees_unreadable_file(self):
        raw = self._ods(
            lambda c: c.replace(
                "<text:p>plain text</text:p>",
                '<text:p>plain <text:span text:style-name="T1">bold</text:span> tail</text:p>',
                1,
            )
        )
        imp = self.env["base_import.import"].create(
            {
                "res_model": "res.partner",
                "file": raw,
                "file_name": "span.ods",
                "file_type": "application/vnd.oasis.opendocument.spreadsheet",
            }
        )
        result = imp.parse_preview({"has_headers": True})
        self.assertFalse(
            result.get("error"),
            "C1 CONFIRMED end to end, user sees: %s" % result.get("error"),
        )

    def test_c2_repeated_content_rows_are_expanded(self):
        raw = self._ods(
            lambda c: c.replace(
                "<table:table-row>",
                '<table:table-row table:number-rows-repeated="4">',
                1,
            )
        )
        rows = self._read(raw)
        self.assertEqual(
            len(rows),
            len(self._CSV.decode().strip().split("\n")) + 3,
            "C2 CONFIRMED: repeated row collapsed, got %d rows" % len(rows),
        )

    def test_c2_control_libreoffice_does_not_collapse_identical_rows(self):
        path = Path("/home/marin/bimp_lo/src.ods")
        if not path.exists():
            self.skipTest("reference LibreOffice file not present")
        raw = path.read_bytes()
        content = zipfile.ZipFile(io.BytesIO(raw)).read("content.xml").decode()
        self.assertNotIn("number-rows-repeated", content)


class BinaryFilenameAlignment(TransactionCase):
    _OPTS = {"has_headers": True, "quoting": '"', "separator": ","}

    def _imp(self, data):
        return self.env["base_import.import"].create(
            {
                "res_model": "res.partner",
                "file": data,
                "file_name": "t.csv",
                "file_type": "text/csv",
            }
        )

    def test_b1_filenames_are_per_record_not_per_row(self):
        imp = self._imp(
            b"name,child_ids/name,image_1920\n"
            b"Parent,Kid1,parent.png\n"
            b",Kid2,continuation.png\n"
            b"Other,Kid3,other.png\n"
        )
        result = imp.execute_import(
            ["name", "child_ids/name", "image_1920"],
            ["name", "child_ids/name", "image_1920"],
            dict(self._OPTS),
            dryrun=True,
        )

        ids = result.get("ids") or []
        filenames = (result.get("binary_filenames") or {}).get("image_1920") or []
        self.assertEqual(len(ids), 2, "3 rows, 2 records")
        self.assertEqual(
            filenames,
            ["parent.png", "other.png"],
            "each record must get its own file, not the next row's",
        )
        self.assertEqual(len(filenames), len(ids))

    def test_b1_names_are_per_record_too(self):
        imp = self._imp(b"name,child_ids/name\nParent,Kid1\n,Kid2\nOther,Kid3\n")
        result = imp.execute_import(
            ["name", "child_ids/name"],
            ["name", "child_ids/name"],
            dict(self._OPTS),
            dryrun=True,
        )
        self.assertEqual(result["name"], ["Parent", "Other"])
        self.assertEqual(len(result["name"]), len(result["ids"]))

    def test_b1_plain_file_still_aligns(self):
        imp = self._imp(b"name,image_1920\nA,a.png\nB,b.png\nC,c.png\n")
        result = imp.execute_import(
            ["name", "image_1920"],
            ["name", "image_1920"],
            dict(self._OPTS),
            dryrun=True,
        )
        self.assertEqual(
            result["binary_filenames"]["image_1920"], ["a.png", "b.png", "c.png"]
        )
        self.assertEqual(len(result["ids"]), 3)

    def test_b1_continuation_file_fills_an_empty_parent(self):
        imp = self._imp(
            b"name,child_ids/name,image_1920\nParent,Kid1,\n,Kid2,late.png\n"
        )
        result = imp.execute_import(
            ["name", "child_ids/name", "image_1920"],
            ["name", "child_ids/name", "image_1920"],
            dict(self._OPTS),
            dryrun=True,
        )
        self.assertEqual(result["binary_filenames"]["image_1920"], ["late.png"])

    def test_b2_load_accepts_null_and_empty_in_a_binary_column(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, "PNG")
        image = base64.b64encode(buffer.getvalue()).decode()

        for placeholder in (None, ""):
            partner = self.env["res.partner"].create({"name": "binary holes"})
            result = (
                self.env["res.partner"]
                .with_context(import_file=True)
                .load(
                    [".id", "image_1920", "image_128"],
                    [[str(partner.id), image, placeholder]],
                )
            )
            self.assertTrue(
                result["ids"],
                "placeholder %r rejected: %r" % (placeholder, result["messages"]),
            )
            self.assertFalse(result["messages"])


class LoadFieldPathValidation(TransactionCase):
    def test_load_rejects_subpath_on_scalar_field(self):
        for path in ("name/foo", "name/id", "name/foo/bar"):
            result = (
                self.env["res.partner"]
                .with_context(import_file=True)
                .load([path], [["Zeta"]])
            )
            self.assertFalse(result["ids"], "%s silently imported" % path)
            self.assertIn("is not a relation", result["messages"][0]["message"])
            self.assertEqual(result["messages"][0]["field_path"], path.split("/"))

    def test_load_still_accepts_real_relational_paths(self):
        country = self.env["res.country"].search([("code", "=", "BE")], limit=1)
        result = (
            self.env["res.partner"]
            .with_context(import_file=True)
            .load(["name", "country_id/id"], [["Rel path", "base.be"]])
        )
        self.assertTrue(result["ids"], result["messages"])
        self.assertEqual(
            self.env["res.partner"].browse(result["ids"]).country_id, country
        )

    def test_load_leaves_unknown_leaf_names_to_the_converter(self):
        result = (
            self.env["res.partner"]
            .with_context(import_file=True)
            .load(["nope"], [["x"]])
        )
        self.assertIn("does not exist", result["messages"][0]["message"])


class SelectionLabelLanguage(TransactionCase):
    def test_source_labels_are_indexed_alongside_translated_ones(self):
        from odoo.tools.translate import code_translations

        self.env["res.lang"]._activate_lang("fr_FR")
        code_translations.python_translations[("test_import_export", "fr_FR")] = {
            "Corge": "toto",
            "Grault": "titi",
            "Wheee": "tete",
            "Moog": "tutu",
        }
        self.addCleanup(
            code_translations.python_translations.pop, ("test_import_export", "fr_FR")
        )

        converter = self.env["ir.fields.converter"].with_context(lang="fr_FR")
        field = self.env["export.selection.function"]._fields["value"]
        index = converter._get_selection_index(field)

        for label in ("wheee", "corge", "grault", "moog"):
            self.assertIn(label, index, "source label %r not importable" % label)
        for label in ("tete", "toto", "titi", "tutu"):
            self.assertIn(label, index, "translated label %r not importable" % label)
