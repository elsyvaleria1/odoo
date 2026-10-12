from collections.abc import Callable
from typing import Any

from odoo import models

from . import approval_trace as trace


class IrAccessObligation(models.AbstractModel):
    _inherit = "ir.access.obligation"

    def _at_door(
        self,
        records: models.BaseModel,
        verb: str,
        call: Callable[[models.BaseModel], Any],
    ) -> Any:
        Binding = self.env["approval.binding"]
        own, configured = Binding._split_verb_bindings(records._name, verb)
        if not own and not configured:
            return super()._at_door(records, verb, call)
        if set(records._ids) <= Binding._get_admitted_ids(records, verb):
            trace.BINDING.event(
                "verb_door_admitted", model=records._name, verb=verb, records=records
            )
            return super()._at_door(records, verb, call)
        trace.BINDING.event(
            "verb_door",
            model=records._name,
            verb=verb,
            records=records.ids,
            own=own.ids,
            configured=configured.ids,
        )
        run = call
        if configured:

            def run(
                runnable: models.BaseModel,
                call: Callable[[models.BaseModel], Any] = call,
            ) -> Any:
                return Binding._gate(
                    runnable,
                    configured,
                    verb,
                    lambda ready: Binding._run_admitted(ready, verb, call),
                )

        if own:
            return own._hold_document_at_door(records, verb, run)
        return run(records)

    def _at_checkpoint(self, records: models.BaseModel, verb: str) -> None:
        Binding = self.env["approval.binding"]
        own, configured = Binding._split_verb_bindings(records._name, verb)
        if configured:
            Binding._enforce_at_checkpoint(records, configured, verb)
        if own:
            own._hold_document_at_checkpoint(records, verb)
        return super()._at_checkpoint(records, verb)

    def _get_held(self, records: models.BaseModel, verb: str) -> models.BaseModel:
        Binding = self.env["approval.binding"]
        own, configured = Binding._split_verb_bindings(records._name, verb)
        held = records.browse()
        if own and own._enforces():
            held |= records._get_approval_held(verb)
        admitted = Binding._get_admitted_ids(records, verb)
        pending = records.filtered(lambda record: record.id not in admitted)
        elevation = Binding._elevation()
        for binding in configured:
            if binding.mode == "advise" or binding._passes_on_elevation(elevation):
                continue
            selected = binding._get_selected(pending)
            held |= selected - selected.browse(binding._get_covered_ids(selected))
        trace.BINDING.event("held", model=records._name, verb=verb, held=held)
        return held

    def _after_move(self, records: models.BaseModel, verb: str) -> None:
        if self.env["approval.binding"]._move_decides(records._name, verb):
            records._approval_move_decided(verb)
        return super()._after_move(records, verb)

    def _explain_obligations(
        self, record: models.BaseModel, verb: str
    ) -> list[dict[str, Any]]:
        result = super()._explain_obligations(record, verb)
        for binding in self.env["approval.binding"]._bindings_for_verb(
            record._name, verb
        ):
            selected = binding._get_selected(record)
            entry = {
                "binding": binding.id,
                "name": binding.name,
                "mode": binding.mode,
                "category": binding.category_id.display_name or False,
                "applies": bool(selected),
            }
            if selected and binding.mode != "act_decides":
                entry["covered"] = record.id in binding._get_covered_ids(selected)
            result.append(entry)
        return result
