from typing import Any, Self

from odoo import api, models

from . import approval_trace as trace


class ApprovalBinding(models.Model):
    _inherit = "approval.binding"

    @api.model
    def create_step_for_button(self, model: str, method=False, action_id=False) -> int:
        """Add an approval step to a button, binding the button first if it has none.

        The binding takes the shape a Studio approval rule always had: Request mode,
        approved on invoke, and the operation left to the next call.
        """
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
        self, model: str, method=False, action_id=False
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
    def _get_or_create_binding_for_button(self, model: str, method, action_id) -> Self:
        """The button's request binding: its own, made one if it only observed or was
        archived (the unique key holds those too), or a new one."""
        action = False if method else self._parse_button_action(action_id)
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
        vals = {"active": True}
        if binding.mode == "advise":
            vals.update(mode="request", approve_on_invoke=True, run_on_approval=False)
        if not binding.category_id:
            vals["category_id"] = self._create_button_category(
                binding.model_id, binding._get_operation_label()
            ).id
        binding.write(vals)
        return binding

    @api.model
    def _create_binding_for_button(self, model: str, method, action_id) -> Self:
        trace.EDITOR.note(
            "binding_created", model=model, method=method or None, action=action_id
        )
        ir_model = self.env["ir.model"]._get(model)
        action = False if method else self._parse_button_action(action_id)
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
    def _create_button_category(self, ir_model, operation: str):
        # A button's approval restricts who may press it; the person pressing is
        # the one whose approval is recorded. That is self-approval by design.
        return self.env["approval.category"].create(
            {
                "name": self.env._(
                    "%(model)s: %(operation)s", model=ir_model.name, operation=operation
                ),
                "allow_self_approval": True,
            }
        )
