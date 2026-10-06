from typing import Any

from markupsafe import Markup, escape

from odoo import models


class MaintenanceOrder(models.Model):
    _inherit = "maintenance.order"

    def _get_maintenance_type_label(self) -> str:
        self.check_singleton()
        return "Preventivo" if self.maintenance_type == "preventive" else "Correctivo"

    def _get_approval_request_name(self) -> str:
        self.check_singleton()
        return (
            f"Mantenimiento {self._get_maintenance_type_label()} - "
            f"{', '.join(self.trace_ids.mapped('name')) or 'N/A'}"
        )

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

    def action_create_approval_request(self) -> dict[str, Any]:
        self.check_singleton()
        self.lock_for_update(wait=True)
        self.invalidate_recordset(["approval_request_id"])
        self._check_can_request_approval()
        category = self._get_approval_category()
        approval = self.env["approval.request"].create(
            self._prepare_approval_request_values(category)
        )
        self.write({"approval_request_id": approval.id})
        self.message_post(
            body=Markup(
                "<a href='#' data-oe-model='approval.request' data-oe-id='%s'>%s</a> %s"
            )
            % (
                approval.id,
                escape(approval.display_name),
                self.env._("created. Please attach documents and submit."),
            ),
            message_type="notification",
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "approval.request",
            "res_id": approval.id,
            "view_mode": "form",
            "target": "current",
        }
