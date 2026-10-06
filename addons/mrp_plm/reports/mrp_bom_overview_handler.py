from odoo import models


class MrpBomOverviewReportHandler(models.AbstractModel):
    _inherit = "mrp.bom.overview.report.handler"

    def _bom_row_values(self, row) -> dict:
        return {**super()._bom_row_values(row), "ecos": row.get("ecos") or 0}

    def _caret_options_initializer(self):
        caret_options = super()._caret_options_initializer()
        open_ecos = {
            "name": self.env._("Open ECOs"),
            "action": "caret_option_open_ecos",
        }
        for key in ("product.product", "product.product.route"):
            caret_options[key].append(open_ecos)
        return caret_options

    def caret_option_open_ecos(self, options, params) -> dict:
        report = self.env["report.formula"].browse(options["report_id"])
        _model, product_id = report._get_model_info_from_id(params["line_id"])
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("ECOs"),
            "res_model": "mrp.eco",
            "domain": [("product_tmpl_id.product_variant_ids", "in", [product_id])],
            "views": [(False, "kanban"), (False, "list"), (False, "form")],
            "target": "current",
        }
