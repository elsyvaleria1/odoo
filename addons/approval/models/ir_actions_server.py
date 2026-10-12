from collections.abc import Callable
from typing import Any

from odoo import models

from . import approval_trace as trace


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    def _gate_run(
        self,
        records: models.BaseModel,
        run: Callable[[models.BaseModel], dict[str, Any] | bool],
        replayable: bool = True,
    ) -> dict[str, Any] | bool:
        self.check_singleton()
        Binding = self.env["approval.binding"]
        if not Binding._enabled():
            return super()._gate_run(records, run, replayable)
        bindings = Binding._bindings_for_action(self.id)
        trace.BINDING.event(
            "action_run",
            action=self.id,
            bindings=bindings.ids,
            records=records.ids if bindings else None,
        )
        if not bindings or not records:
            return super()._gate_run(records, run, replayable)
        return Binding._gate(records, bindings, self.name, run, replayable=replayable)
