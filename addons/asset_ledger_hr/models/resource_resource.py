from collections import Counter

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.resource.models.utils import OPERATOR_ROLE
from odoo.addons.resource_asset.models.resource_resource import CUSTODY_SILENT


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    def action_view_logs_assignation(self):
        return self._action_view_logs(
            [("log_type", "=", "operator")],
            {
                **self._get_log_type_context("operator"),
                "default_operator_id": self.operator_employee_id.id,
            },
        )

    def _on_custody_changed(self, role, changes, planned=False):
        super()._on_custody_changed(role, changes, planned=planned)
        if (
            role == OPERATOR_ROLE
            and not planned
            and not self.env.context.get(CUSTODY_SILENT)
        ):
            self.filtered("kind_id")._book_operator_assignment()

    def action_accept_operator_change(self):
        assets = self.filtered("future_operator_id")
        incoming = Counter(
            (asset.kind_id.id, asset.future_operator_id.id) for asset in assets
        )
        conflicting = self.env["resource.resource"].browse(
            {holder for (_kind, holder), times in incoming.items() if times > 1}
        )
        if conflicting:
            raise UserError(
                self.env._(
                    "An operator can only take over one asset of each kind at a "
                    "time. Scheduled on several assets of the same kind in this "
                    "operation: %(operators)s",
                    operators=", ".join(conflicting.mapped("name")),
                )
            )
        return super().action_accept_operator_change()

    def _get_assets_released_by_operator_change(self):
        released = super()._get_assets_released_by_operator_change()
        return released.filtered(lambda asset: asset.kind_id in self.kind_id)

    def _get_product_operator_assignment(self):
        product = self.env.ref(
            "asset_ledger.product_product_operator_assignment",
            raise_if_not_found=False,
        )
        return product or self.env["product.product"]

    def _prepare_operator_assignment_data(self) -> dict:
        self.check_singleton()
        return {
            "asset_id": self.id,
            "operator_id": self.operator_employee_id.id,
            "asset_manager_id": self.manager_employee_id.id,
            "product_id": self._get_product_operator_assignment().id or False,
            "date_start": fields.Date.context_today(self),
            # No odometer: the asset's current figure is the last reading
            # someone took, not a measurement made at handover. Stamped with
            # today's date it read as one, and the ledger took it as a reading.
            "log_type": "operator",
            "source": "assignment",
            "state": "done",
        }

    def _book_operator_assignment(self):
        if not self:
            return self.env["resource.log"]
        return (
            self.env["resource.log"]
            .sudo()
            .create([asset._prepare_operator_assignment_data() for asset in self])
        )
