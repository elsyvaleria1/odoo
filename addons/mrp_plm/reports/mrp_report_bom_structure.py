from odoo import models


class ReportMrpReport_Bom_Structure(models.AbstractModel):
    _inherit = "report.mrp.report_bom_structure"

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
        if self.env.user.has_group("mrp_plm.group_plm_user"):
            product_tmpl_id = (
                res["product"] and res["product"].product_tmpl_id.id
            ) or (res["bom"] and res["bom"].product_tmpl_id.id)
            res["ecos"] = (
                self.env["mrp.eco"].search_count(
                    [("product_tmpl_id", "=", product_tmpl_id), ("state", "!=", "done")]
                )
                or ""
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
        if self.env.user.has_group("mrp_plm.group_plm_user"):
            res["ecos"] = (
                self.env["mrp.eco"].search_count(
                    [
                        ("product_tmpl_id", "=", res["product"].product_tmpl_id.id),
                        ("state", "!=", "done"),
                    ]
                )
                or ""
            )
        return res
