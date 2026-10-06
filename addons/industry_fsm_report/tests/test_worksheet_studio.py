from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWorksheetStudio(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.worksheet = cls.env["worksheet.template"].create(
            {"name": "Studio service worksheet", "res_model": "project.task"}
        )
        cls.form_view = cls.env["ir.ui.view"].search(
            [("model", "=", cls.worksheet.model_id.model), ("type", "=", "form")],
            limit=1,
        )

    def _edit_view(self, view, arch, **params):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/web_studio/edit_view",
            json=self.prepare_rpc_payload(
                {"view_id": view.id, "studio_view_arch": arch, **params}
            ),
        )
        response.raise_for_status()
        payload = response.json()
        self.assertNotIn("error", payload)
        self.assertIn("result", payload)

    def test_worksheet_edit_regenerates_report_once(self):
        template_class = self.env.registry["worksheet.template"]
        regenerate = template_class._create_qweb_report_template
        calls = []

        def record_regeneration(templates, *args, **kwargs):
            calls.append(templates.ids)
            return regenerate(templates, *args, **kwargs)

        with patch.object(
            template_class, "_create_qweb_report_template", record_regeneration
        ):
            for params, label in (
                ({}, "Service notes"),
                ({"model": self.form_view.model}, "Inspection notes"),
            ):
                with self.subTest(params=params):
                    calls.clear()
                    self._edit_view(
                        self.form_view,
                        "<data><xpath expr=\"//field[@name='x_comments']\" "
                        'position="attributes"><attribute name="string">'
                        f"{label}</attribute></xpath></data>",
                        **params,
                    )
                    self.assertEqual(calls, [self.worksheet.ids])
                    self.worksheet.report_view_id.invalidate_recordset(["arch_db"])
                    self.assertIn(label, self.worksheet.report_view_id.arch_db)

    def test_non_worksheet_edit_does_not_regenerate_reports(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "Studio contact form",
                "model": "res.partner",
                "type": "form",
                "arch": '<form><field name="name"/></form>',
            }
        )
        with patch.object(
            self.env.registry["worksheet.template"],
            "_create_qweb_report_template",
            side_effect=AssertionError("A contact edit must not regenerate worksheets"),
        ):
            self._edit_view(view, "<data/>")
