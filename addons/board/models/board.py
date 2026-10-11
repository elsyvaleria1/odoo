from lxml import etree

from odoo import api, fields, models

from odoo.addons.base.models.ir_ui_view_base import attach_ir


class BoardBoard(models.AbstractModel):
    _name = "board.board"
    _description = "Board"
    _auto = False

    id = fields.Id()

    @api.model_create_multi
    def create(self, vals_list):
        return self

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):

        res = super().get_view(view_id, view_type, **options)

        custom_view = (
            self.env["ir.ui.view.custom"]
            .sudo()
            .search([("user_id", "=", self.env.uid), ("ref_id", "=", view_id)], limit=1)
        )
        if custom_view:
            res.update({"custom_view_id": custom_view.id, "arch": custom_view.arch})
        res["arch"] = self._arch_preprocessing(res["arch"])
        return attach_ir(res)

    @api.model
    def _arch_preprocessing(self, arch):
        archnode = etree.fromstring(arch)
        archnode.set("js_class", "board")
        return etree.tostring(archnode, pretty_print=True, encoding="unicode")
