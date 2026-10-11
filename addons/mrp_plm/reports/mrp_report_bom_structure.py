from typing import Self

from odoo import models
from odoo.tools import frozendict

OPEN_ECOS_KEY = "bom_report_open_ecos"


class ReportMrpReport_Bom_Structure(models.AbstractModel):
    _inherit = "report.mrp.report_bom_structure"

    def _shows_ecos(self) -> bool:
        return not self.env.context.get("minimized") and self.env.user.has_group(
            "mrp_plm.group_plm_user"
        )

    def _prepare_tree(self, bom, product, ignore_stock=False) -> Self:
        report = super()._prepare_tree(bom, product, ignore_stock=ignore_stock)
        if not report._shows_ecos():
            return report
        templates = (
            report._bom_tree_products(bom, product).product_tmpl_id
            | bom.product_tmpl_id
        )
        counts = report.env["mrp.eco"]._read_group(
            [("product_tmpl_id", "in", templates.ids), ("state", "!=", "done")],
            ["product_tmpl_id"],
            ["__count"],
        )
        return report.with_context(
            {OPEN_ECOS_KEY: frozendict((tmpl.id, n) for tmpl, n in counts)}
        )

    def _open_ecos(self, template):
        counts = self.env.context.get(OPEN_ECOS_KEY)
        if counts is None:
            count = self.env["mrp.eco"].search_count(
                [("product_tmpl_id", "=", template.id), ("state", "!=", "done")]
            )
        else:
            count = counts.get(template.id, 0)
        return count or ""

    def _get_bom_data(
        self,
        bom,
        warehouse,
        product=False,
        line_qty=False,
        bom_line=False,
        level=0,
        parent_bom=False,
        parent_product=False,
        index=0,
        product_info=False,
        ignore_stock=False,
        simulated_leaves_per_workcenter=False,
    ):
        res = super()._get_bom_data(
            bom,
            warehouse,
            product,
            line_qty,
            bom_line,
            level,
            parent_bom,
            parent_product,
            index,
            product_info,
            ignore_stock,
            simulated_leaves_per_workcenter,
        )
        if self._shows_ecos():
            res["ecos"] = self._open_ecos(
                (res["product"] and res["product"].product_tmpl_id)
                or (res["bom"] and res["bom"].product_tmpl_id)
                or self.env["product.template"]
            )
        return res

    def _get_component_data(
        self,
        parent_bom,
        parent_product,
        warehouse,
        bom_line,
        line_quantity,
        level,
        index,
        product_info,
        ignore_stock=False,
    ):
        res = super()._get_component_data(
            parent_bom,
            parent_product,
            warehouse,
            bom_line,
            line_quantity,
            level,
            index,
            product_info,
            ignore_stock,
        )
        if self._shows_ecos():
            res["ecos"] = self._open_ecos(res["product"].product_tmpl_id)
        return res
