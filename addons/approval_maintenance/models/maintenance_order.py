from typing import Any

from markupsafe import Markup, escape

from odoo import models


class MaintenanceOrder(models.Model):
    _inherit = "maintenance.order"

    def _get_maintenance_type_label(self) -> str:
        self.check_singleton()
        return "Preventivo" if self.maintenance_type == "preventive" else "Correctivo"

    def _prepare_approval_request_values(self, category) -> dict[str, Any]:
        vals = super()._prepare_approval_request_values(category)
        vals["reason"] = self._get_maintenance_approval_reason_html()
        return vals

    def _get_maintenance_approval_reason_html(self) -> Markup:
        self.check_singleton()
        parts = [
            Markup("<h4>Solicitud de Mantenimiento %s</h4>")
            % escape(self._get_maintenance_type_label()),
            Markup("<p><strong>Equipo:</strong> %s</p>")
            % escape(", ".join(self.trace_ids.mapped("name")) or "N/A"),
            Markup("<p><strong>Producto:</strong> %s</p>")
            % escape(", ".join(self.trace_ids.product_id.mapped("name")) or "N/A"),
        ]
        if self.name:
            parts.append(
                Markup("<p><strong>Asunto:</strong> %s</p>") % escape(self.name)
            )
        if self.duration:
            parts.append(
                Markup("<p><strong>Duración estimada:</strong> %s horas</p>")
                % self.duration
            )
        if self.vendor_id:
            parts.append(
                Markup("<p><strong>Proveedor:</strong> %s</p>")
                % escape(self.vendor_id.name)
            )
        return Markup("").join(parts)

    def _submits_approval_request_on_raise(self) -> bool:
        return False

    def _get_approval_raised_note(self, approval) -> Markup:
        return Markup(
            "<a href='#' data-oe-model='approval.request' data-oe-id='%s'>%s</a> %s"
        ) % (
            approval.id,
            escape(approval.display_name),
            self.env._("created. Please attach documents and submit."),
        )

    def _get_approval_submitted_action(self, approval) -> dict[str, Any]:
        return {
            "type": "ir.actions.act_window",
            "res_model": "approval.request",
            "res_id": approval.id,
            "view_mode": "form",
            "target": "current",
        }
