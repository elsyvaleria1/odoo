from typing import Any, Self

from lxml import etree

from odoo import models

from odoo.addons.base.models.ir_qweb import (
    restricted_template_errors,
    template_trust_digest,
)
from odoo.addons.base.models.mixin_template_authoring import TemplateUnit


class IrUiView(models.Model):
    _name = "ir.ui.view"
    _inherit = ["ir.ui.view", "mixin.template.trust"]

    def _get_template_unit_fields(self) -> set[str]:
        return {"arch_db"}

    def _get_template_unit(self, fname: str, source: Any) -> TemplateUnit | None:
        if self.type != "qweb" or not source:
            return None
        try:
            root = etree.fromstring(source)
        except etree.XMLSyntaxError:
            return None
        return TemplateUnit(
            template_trust_digest(root),
            restricted_template_errors(
                root, directives=self.env["ir.qweb"]._get_authoring_directives()
            ),
        )

    def _get_template_name(self) -> str:
        return self.key or self.name

    def _get_template_unit_label(self, fname: str) -> str:
        return self._get_template_name()

    def _get_shipped_sources(self) -> dict[Self, dict[str, Any]]:
        return {
            view: {"arch_db": arch}
            for view in self
            if (arch := view._get_arch_from_file())
        }

    def _filter_module_records(self) -> Self:
        return self.filtered(lambda view: view.type == "qweb" and view.arch_fs)
