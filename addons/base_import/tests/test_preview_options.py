from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPreviewMode(TransactionCase):
    def test_preserved_preview_mode_is_always_boolean(self):
        importer = self.env["base_import.import"].create(
            {
                "res_model": "res.partner",
                "file": b"name\nExample\n",
                "file_name": "partners.csv",
                "file_type": "text/csv",
            }
        )
        for preserved, expected in (
            ({}, False),
            ({"advanced": None}, False),
            ({"advanced": False}, False),
            ({"advanced": True}, True),
        ):
            with self.subTest(preserved=preserved):
                preview = importer.parse_preview(
                    {"has_headers": True, "keep_matches": True, **preserved}
                )
                self.assertNotIn("error", preview)
                self.assertIs(preview["advanced_mode"], expected)

    def test_relational_headers_and_matches_select_advanced_mode(self):
        importer = self.env["base_import.import"]
        for headers, matches, expected in (
            (["name"], {0: ["name"]}, False),
            (["country_id/name"], {}, True),
            (["Country"], {0: ["country_id", "name"]}, True),
        ):
            with self.subTest(headers=headers, matches=matches):
                self.assertIs(
                    importer._is_advanced_mode(headers, matches, {}), expected
                )
