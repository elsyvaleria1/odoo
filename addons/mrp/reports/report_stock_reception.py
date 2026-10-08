from odoo import models
from odoo.tools import format_date


class ReportStockReport_Reception(models.AbstractModel):
    _inherit = "report.stock.report_reception"

    def _get_docs(self, docids):
        if self.env.context.get("default_production_ids"):
            return self.env["mrp.production"].search(
                [
                    ("id", "in", self.env.context.get("default_production_ids")),
                    ("state", "!=", "cancel"),
                ]
            )
        return super()._get_docs(docids)

    def _get_doc_model(self):
        if self.env.context.get("default_production_ids"):
            return "mrp.production"
        return super()._get_doc_model()

    def _get_doc_types_label(self):
        return super()._get_doc_types_label() + " or manufacturing orders"

    def _get_moves(self, docs):
        if self.env.context.get("default_production_ids"):
            return docs.move_finished_ids.filtered(
                lambda m: m.product_id.is_storable and m.state != "cancel"
            )
        return super()._get_moves(docs)

    def _get_domain_extra(self, docs) -> list:
        if self.env.context.get("default_production_ids"):
            return [("raw_material_production_id", "not in", docs.ids)]
        return super()._get_domain_extra(docs)

    def _get_formatted_scheduled_date(self, source):
        if source._name == "mrp.production":
            return format_date(self.env, source.date_start)
        return super()._get_formatted_scheduled_date(source)

    def _share_source_references(self, in_move, out_move) -> None:
        super()._share_source_references(in_move, out_move)
        if groups := self._get_production_groups(in_move, out_move):
            parent, child = groups
            parent.child_ids |= child

    def _unshare_source_references(self, in_move, out_move) -> None:
        super()._unshare_source_references(in_move, out_move)
        if in_move.production_id:
            in_move.production_id.move_dest_ids -= out_move
        if groups := self._get_production_groups(in_move, out_move):
            parent, child = groups
            if not (
                child.production_ids.move_finished_ids.move_dest_ids
                & parent.production_ids.move_raw_ids
            ):
                parent.child_ids -= child

    def _get_production_groups(self, in_move, out_move) -> tuple | None:
        parent = out_move._get_source_document()
        child = in_move._get_source_document()
        if not (
            parent
            and child
            and parent._name == child._name == "mrp.production"
            and parent != child
        ):
            return None
        return parent.production_group_id, child.production_group_id
