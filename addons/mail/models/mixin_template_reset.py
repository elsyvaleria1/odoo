from typing import Self

from lxml import etree

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.modules.module import get_resource_from_path
from odoo.tools.convert import xml_import
from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationImporter, get_po_paths

_debug = DebugLog(__name__)


class MixinTemplateReset(models.AbstractModel):
    _name = "mixin.template.reset"
    _description = "Template Reset Mixin"

    template_fs = fields.Char(
        string="Template Filename",
        copy=False,
        help="""File from where the template originates. Used to reset broken template.""",
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        context = self.env.context
        if "install_xmlid" in context and "install_filename" in context:
            path_info = get_resource_from_path(context["install_filename"])
            for vals in vals_list:
                if "template_fs" not in vals and path_info:
                    vals["template_fs"] = path_info.addons_path
        return super().create(vals_list)

    def _get_reset_preserved_fields(self) -> set[str]:
        return {*models.MAGIC_COLUMNS, "template_fs"}

    def _load_records_write(self, values: dict) -> None:
        if self.env.context.get("reset_template"):
            fields_not_to_touch = self._get_reset_preserved_fields() | values.keys()
            fields_to_empty = {
                name
                for name, field in self._fields.items()
                if field.store and not field.compute and name not in fields_not_to_touch
            }
            _debug.logic(
                "template_reset_fields",
                model=self._name,
                records=self.ids,
                emptied=sorted(fields_to_empty),
            )
            field_defaults = self.default_get(list(fields_to_empty))
            values.update(field_defaults)
            fields_to_empty -= set(field_defaults.keys())
            values.update(dict.fromkeys(fields_to_empty, False))
        return super()._load_records_write(values)

    def _override_translation_term(self, module_name: str, xml_ids: list[str]) -> None:
        translation_importer = TranslationImporter(self.env.cr)

        for lang, _name in self.env["res.lang"].get_installed():
            for po_path in get_po_paths(module_name, lang):
                translation_importer.load_file(po_path, lang, xmlids=xml_ids)

        translation_importer.save(overwrite=True, force_overwrite=True)

    def reset_template(self) -> None:
        expr = "//*[local-name() = $tag and (@id = $xml_id or @id = $external_id)]"
        templates_with_missing_source = []
        lang_false = {
            code: False
            for code, _ in self.env["res.lang"].get_installed()
            if code != "en_US"
        }
        external_ids = self.get_external_id()
        for template in self.filtered("template_fs"):
            external_id = external_ids.get(template.id)
            if not external_id:
                _debug.logic(
                    "template_reset_no_xmlid", model=self._name, record=template.id
                )
                templates_with_missing_source.append(template.display_name)
                continue
            module, xml_id = external_id.split(".")
            try:
                fullpath = file_path(template.template_fs)
            except FileNotFoundError, ValueError:
                fullpath = None
            _debug.lifecycle(
                "template_reset",
                model=self._name,
                record=template.id,
                xmlid=external_id,
                source_found=bool(fullpath),
            )
            if fullpath:
                for field_name, field in template._fields.items():
                    if field.translate is True:
                        template.update_field_translations(field_name, lang_false)
                doc = etree.parse(fullpath)
                for rec in doc.xpath(
                    expr, tag="record", xml_id=xml_id, external_id=external_id
                ):
                    rec.set("context", json_dumps({"reset_template": "True"}))
                    obj = xml_import(
                        template.env, module, {}, mode="init", xml_filename=fullpath
                    )
                    obj._tag_record(rec)
                    template._override_translation_term(module, [xml_id, external_id])
            else:
                templates_with_missing_source.append(template.display_name)
        if templates_with_missing_source:
            raise UserError(
                self.env._(
                    "The following email templates could not be reset because their related source files could not be found:\n- %s",
                    "\n- ".join(templates_with_missing_source),
                )
            )
