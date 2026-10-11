from lxml import etree

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import BaseCase, HttpCase, TransactionCase

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.web_studio.controllers.export import StudioExporter
from odoo.addons.web_studio.wizards.wizard_ir_module_module_export_customization import (
    FIELDS_TO_EXPORT,
    _find_circular_dependencies,
)


class TestExport(HttpCase):
    def setUp(self):
        super().setUp()
        self.exporter = StudioExporter()

    def test_export_currency_field(self):
        base_currency_field = self.env["res.partner"]._fields.get("currency_id")
        IrModelFields = self.env["ir.model.fields"].with_context(studio=True)
        if not base_currency_field or not (
            base_currency_field.type == "many2one"
            and base_currency_field.comodel_name == "res.currency"
        ):
            IrModelFields.create(
                {
                    "state": "base",
                    "name": "x_currency" if base_currency_field else "currency_id",
                    "model_id": self.env["ir.model"]._get("res.partner").id,
                    "ttype": "many2one",
                    "relation": "res.currency",
                }
            )

        currency_field = IrModelFields.create(
            {
                "name": "x_test_currency",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "ttype": "many2one",
                "relation": "res.currency",
            }
        )
        monetary = IrModelFields.create(
            {
                "name": "x_test_monetary",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "ttype": "monetary",
                "currency_field": currency_field.name,
            }
        )

        studio_module = self.env["ir.module.module"].get_or_create_studio_module()
        data = self.env["ir.model.data"].search(
            [
                ("studio", "=", True),
                ("model", "=", "ir.model.fields"),
                ("res_id", "in", (currency_field | monetary).ids),
            ]
        )
        data = self.env["wizard.ir.module.module.export.customization.line"].create(
            [{"model": d.model, "res_id": d.res_id, "studio": d.studio} for d in data]
        )
        wizard = self.env["wizard.ir.module.module.export.customization"].create(
            {
                "default_export_data": [Command.set(data.ids)],
                "additional_models": [],
            }
        )
        export_info = wizard.get_export_info()
        content_iter = iter(
            self.exporter.generate_module_files(studio_module, export_info)
        )

        file_name = content = None
        with MockRequest(self.env):
            while file_name != "data/ir_model_fields.xml":
                file_name, content = next(content_iter)

        arch_fields = etree.fromstring(content)
        records = arch_fields.findall("record")
        currency_field = records[0]
        self.assertEqual(
            currency_field.find("./field[@name='name']").text, "x_test_currency"
        )
        self.assertEqual(currency_field.find("./field[@name='currency_field']"), None)

        monetary_field = records[1]
        self.assertEqual(
            monetary_field.find("./field[@name='name']").text, "x_test_monetary"
        )
        self.assertEqual(
            monetary_field.find("./field[@name='currency_field']").text,
            "x_test_currency",
        )

        monetary.currency_field = False
        export_info = wizard.get_export_info()
        content_iter = iter(
            self.exporter.generate_module_files(studio_module, export_info)
        )

        file_name = content = None
        with MockRequest(self.env):
            while file_name != "data/ir_model_fields.xml":
                file_name, content = next(content_iter)

        arch_fields = etree.fromstring(content)
        records = arch_fields.findall("record")
        currency_field = records[0]
        self.assertEqual(
            currency_field.find("./field[@name='name']").text, "x_test_currency"
        )
        self.assertEqual(currency_field.find("./field[@name='currency_field']"), None)

        monetary_field = records[1]
        self.assertEqual(
            monetary_field.find("./field[@name='name']").text, "x_test_monetary"
        )
        self.assertEqual(monetary_field.find("./field[@name='currency_field']"), None)

    def test_export_automation(self):
        ba = (
            self.env["automation.rule"]
            .with_context(studio=True)
            .create(
                {
                    "name": "Cron BaseAuto",
                    "trigger": "on_time",
                    "model_id": self.env.ref("base.model_res_users").id,
                }
            )
        )
        data = self.env["ir.model.data"].search(
            [
                ("studio", "=", True),
                ("model", "=", "automation.rule"),
                ("res_id", "=", ba.id),
            ]
        )

        studio_module = self.env["ir.module.module"].get_or_create_studio_module()
        data = self.env["wizard.ir.module.module.export.customization.line"].create(
            [{"model": d.model, "res_id": d.res_id, "studio": d.studio} for d in data]
        )
        wizard = self.env["wizard.ir.module.module.export.customization"].create(
            {
                "default_export_data": [Command.set(data.ids)],
            }
        )
        export_info = wizard.get_export_info()
        content_iter = iter(
            self.exporter.generate_module_files(studio_module, export_info)
        )
        file_name = content = None
        with MockRequest(self.env):
            while file_name != "data/automation_rule.xml":
                file_name, content = next(content_iter)

        arch = etree.fromstring(content)
        records = arch.findall("record")
        self.assertEqual(len(records), 1)
        record = records[0]
        field_names = {field.get("name") for field in record.findall("./field")}
        self.assertEqual(
            field_names, {"model_id", "name", "trg_date_range_type", "trigger"}
        )

    def test_export_unarchived_records(self):
        IrFilter = self.env["ir.filters"].with_context(studio=True)
        filter_1 = IrFilter.create(
            {
                "name": "Filter 1",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "domain": "[]",
            }
        )

        filter_2 = IrFilter.create(
            {
                "name": "Filter 2",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "domain": "[]",
            }
        )

        self.assertTrue(filter_1.active, "Filter 1 should be active initially")
        self.assertTrue(filter_2.active, "Filter 2 should be active initially")

        filter_1.active = False
        self.assertFalse(filter_1.active, "Filter should be archived")

        filter_data = self.env["ir.model.data"].search(
            [
                ("studio", "=", True),
                ("model", "=", "ir.filters"),
            ]
        )
        self.assertEqual(
            len(filter_data),
            2,
            "Should have two ir.model.data records: one archived and one active filter",
        )

        wizard = self.env["wizard.ir.module.module.export.customization"].create({})
        default_data = wizard._default_studio_export_data()
        wizard.default_export_data = [Command.set(default_data.ids)]
        export_info = wizard.get_export_info()

        studio_module = self.env["ir.module.module"].get_or_create_studio_module()
        content_iter = iter(
            self.exporter.generate_module_files(studio_module, export_info)
        )

        file_name = content = None
        with MockRequest(self.env):
            while file_name != "data/ir_filters.xml":
                file_name, content = next(content_iter)

            arch_filters = etree.fromstring(content)
            records = arch_filters.findall("record")
            self.assertEqual(
                len(records), 1, "Only the active filter should be exported."
            )

    def test_fields_renamed_by_the_fork_are_still_excluded(self):
        for model, field_name in (("res.partner", "tag_ids"), ("sale.order", "notes")):
            if model not in self.env:
                continue
            export_model = self.env["studio.export.model"].create(
                {"model_id": self.env["ir.model"]._get(model).id}
            )
            self.assertIn(
                field_name, export_model.excluded_fields.mapped("name"), model
            )

    def test_fields_to_export_are_not_excluded(self):
        for model, fields_to_export in FIELDS_TO_EXPORT.items():
            export_model = self.env["studio.export.model"].create(
                {
                    "model_id": self.env["ir.model"]._get(model).id,
                }
            )
            excluded_fields = export_model.excluded_fields.mapped("name")
            self.assertEqual(
                set(fields_to_export), set(fields_to_export) - set(excluded_fields)
            )


class TestExportedAccessRows(TransactionCase):
    def test_every_field_deciding_what_a_row_grants_is_exported(self):
        Access = self.env["ir.access"]
        deciding = {
            name
            for name, field in Access._fields.items()
            if field.store
            and not field.compute
            and name
            not in (
                "id",
                "note",
                "create_uid",
                "create_date",
                "write_uid",
                "write_date",
            )
        }
        self.assertLessEqual(deciding, set(FIELDS_TO_EXPORT["ir.access"]))


@tagged("post_install", "-at_install")
class TestExportTours(HttpCase):
    def test_can_export_new_module(self):
        self.start_tour("/odoo?debug=tests", "can_export_new_module", login="admin")
        wizard = self.env["wizard.ir.module.module.export.customization"].search(
            [], limit=1, order="id desc"
        )
        data, files, circular_dependencies = wizard.get_export_info()
        self.assertEqual(circular_dependencies, [])
        self.assertEqual(data, wizard.default_export_data)
        self.assertEqual(len(wizard.additional_export_data), 0)
        exported_models = {f[0] for f in files}
        self.assertEqual(
            exported_models,
            {
                "ir.actions.act_window",
                "ir.default",
                "ir.model",
                "ir.model.fields",
                "ir.access",
                "ir.ui.view",
                "ir.ui.menu",
            },
        )
        self.assertEqual(len(data.filtered(lambda r: r.model == "ir.model")), 1)
        self.assertEqual(
            self.env["ir.model"]
            .browse(data.filtered(lambda r: r.model == "ir.model").res_id)
            .name,
            "My App Records",
        )
        created_menus = (
            self.env["ir.ui.menu"]
            .browse(data.filtered(lambda r: r.model == "ir.ui.menu").mapped("res_id"))
            .mapped("name")
        )
        self.assertEqual(len(created_menus), 2)
        self.assertTrue("My New App" in created_menus)
        self.assertTrue("My App Records" in created_menus)


class TestCircularDependencies(BaseCase):
    def test_circular_dependencies(self):
        self.assertEqual(_find_circular_dependencies({}), [])
        self.assertEqual(_find_circular_dependencies({1: []}), [])
        self.assertEqual(_find_circular_dependencies({1: [1]}), [])
        self.assertEqual(_find_circular_dependencies({1: [2]}), [])
        self.assertEqual(_find_circular_dependencies({1: [2], 2: [3]}), [])
        self.assertEqual(_find_circular_dependencies({1: [2, 3], 2: [3], 3: [4]}), [])
        self.assertEqual(
            _find_circular_dependencies({1: [2], 2: [3], 3: [1]}), [[1, 2, 3, 1]]
        )
        self.assertEqual(
            _find_circular_dependencies({1: [2, 3], 2: [3], 3: [1]}), [[1, 2, 3, 1]]
        )
        self.assertEqual(
            _find_circular_dependencies({1: [2], 2: [3], 3: [4], 4: [1]}),
            [[1, 2, 3, 4, 1]],
        )
        self.assertEqual(
            _find_circular_dependencies({1: [2], 2: [1], 3: [4], 4: [5], 5: [3]}),
            [[1, 2, 1], [3, 4, 5, 3]],
        )
