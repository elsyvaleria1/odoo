from typing import TYPE_CHECKING, Any, Literal, Self

from odoo import api, models
from odoo.api import ValuesType

from . import approval_trace as trace

if TYPE_CHECKING:
    from .approval_category import ApprovalCategory
    from odoo.addons.base.models.ir_model import IrModel


class ApprovalBinding(models.Model):
    _inherit = "approval.binding"

    @api.model
    def create_step_for_button(
        self,
        model: str,
        method: str | Literal[False] = False,
        action_id: int | str | Literal[False] = False,
    ) -> int:
        binding = self._get_or_create_binding_for_button(model, method, action_id)
        category = binding.category_id
        steps = category.step_ids
        sequence = min(max(steps.mapped("sequence"), default=0) + 1, 9)
        step = self.env["approval.category.step"].create(
            {
                "category_id": category.id,
                "name": self.env._("Step %(sequence)s", sequence=sequence),
                "sequence": sequence,
                "group_id": self.env.ref("base.group_user").id,
                "subject_model_id": binding.model_id.id,
            }
        )
        if not category.notify_sequentially:
            category.notify_sequentially = True
        trace.EDITOR.note(
            "step_created",
            binding=binding.id,
            category=category.id,
            step=step.id,
            sequence=sequence,
            existing=len(steps),
        )
        return step.id

    def action_open_button_steps(
        self,
        model: str,
        method: str | Literal[False] = False,
        action_id: int | str | Literal[False] = False,
    ) -> dict[str, Any]:
        binding = self._get_or_create_binding_for_button(model, method, action_id)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Approval Steps: %(binding)s", binding=binding.name),
            "res_model": "approval.category.step",
            "view_mode": "kanban,list,form",
            "domain": [("category_id", "=", binding.category_id.id)],
            "context": {
                "default_category_id": binding.category_id.id,
                "default_subject_model_id": binding.model_id.id,
                "default_group_id": self.env.ref("base.group_user").id,
            },
        }

    @api.model
    def _get_or_create_binding_for_button(
        self,
        model: str,
        method: str | Literal[False],
        action_id: int | str | Literal[False],
    ) -> Self:
        action = None if method else self._parse_button_action(action_id)
        binding = self.with_context(active_test=False).search(
            [
                ("model_name", "=", model),
                ("method", "=", method or False),
                ("action_id", "=", action),
                ("verb", "=", False),
                ("subject_domain", "=", False),
            ],
            limit=1,
        )
        if not binding:
            return self._create_binding_for_button(model, method, action_id)
        if binding.active and binding.mode != "advise" and binding.category_id:
            return binding
        trace.EDITOR.note(
            "binding_adopted",
            binding=binding.id,
            mode=binding.mode,
            active=binding.active,
        )
        vals: ValuesType = {"active": True}
        if binding.mode == "advise":
            vals.update(mode="request", approve_on_invoke=True, run_on_approval=False)
        if not binding.category_id:
            vals["category_id"] = self._create_button_category(
                binding.model_id, binding._get_operation_label()
            ).id
        binding.write(vals)
        return binding

    @api.model
    def _create_binding_for_button(
        self,
        model: str,
        method: str | Literal[False],
        action_id: int | str | Literal[False],
    ) -> Self:
        trace.EDITOR.note(
            "binding_created", model=model, method=method or None, action=action_id
        )
        ir_model = self.env["ir.model"]._get(model)
        action = None if method else self._parse_button_action(action_id)
        operation = method or self.env["ir.actions.actions"].browse(action).name
        return self.create(
            {
                "model_id": ir_model.id,
                "method": method or False,
                "action_id": action,
                "mode": "request",
                "approve_on_invoke": True,
                "run_on_approval": False,
                "category_id": self._create_button_category(ir_model, operation).id,
            }
        )

    @api.model
    def _create_button_category(
        self, ir_model: IrModel, operation: str
    ) -> ApprovalCategory:
        return self.env["approval.category"].create(
            {
                "name": self.env._(
                    "%(model)s: %(operation)s", model=ir_model.name, operation=operation
                ),
                "allow_self_approval": True,
            }
        )
