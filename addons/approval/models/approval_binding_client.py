from collections import defaultdict
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import ormcache

from . import approval_trace as trace


class ApprovalBinding(models.Model):
    _inherit = "approval.binding"

    @api.model
    @ormcache()
    def _get_names_of_gated_models(self) -> frozenset[str]:
        return frozenset(
            self.sudo()
            .with_context(active_test=True)
            .search([("mode", "not in", ("advise", "act_decides"))])
            .mapped("model_name")
        )

    @api.model
    def get_button_approvals(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trace.BUTTON.event("batch_asked", specs=len(specs), uid=self.env.uid)
        by_button = defaultdict(list)
        for index, spec in enumerate(specs):
            button = (
                spec["model"],
                spec.get("method") or False,
                spec.get("action_id") or False,
                bool(spec.get("configured")),
            )
            by_button[button].append(index)
        answers = [None] * len(specs)
        for (model, method, action_id, configured), indexes in by_button.items():
            for index, answer in zip(
                indexes,
                self._get_button_approvals_for(
                    model,
                    [specs[index].get("res_id") or False for index in indexes],
                    method,
                    action_id,
                    configured,
                ),
                strict=True,
            ):
                answers[index] = answer
        return answers

    @api.model
    def check_button_approval(
        self, model: str, res_id: int | list[int], method=False, action_id=False
    ) -> dict[str, Any]:
        if not self._enabled():
            return {"approved": True, "request_id": False}
        bindings = self._get_button_bindings(model, method, action_id)
        if not bindings:
            return {"approved": True, "request_id": False}
        records = self._get_records_for_button(model, res_id, "write")
        if not records:
            return {"approved": True, "request_id": False}
        result = self._gate(
            records,
            bindings,
            method or bindings[:1].action_id.name,
            lambda runnable: True,
            mark_run=False,
            asking=True,
        )
        trace.BUTTON.note(
            "checked",
            model=model,
            res_id=res_id,
            method=method or None,
            action=action_id or None,
            bindings=bindings.ids,
            approved=result is True,
        )
        if result is True:
            return {"approved": True, "request_id": False}
        return {
            "approved": False,
            "request_id": result.get("res_id", False)
            if isinstance(result, dict)
            else False,
        }

    @api.model
    def action_decide_approval(
        self,
        model: str,
        res_id: int,
        method=False,
        action_id=False,
        approve=True,
        step_id=False,
    ) -> dict[str, Any]:
        records = self._get_records_for_button(model, res_id, "write")
        binding = self._get_button_binding_for(records, method, action_id)
        steps = binding._get_button_decision_steps(step_id)
        request = binding._get_button_request(records)
        if request.state == "approved" and records.id in binding._get_covered_ids(
            records
        ):
            trace.REFUSAL.event(
                "button_already_approved",
                binding=binding.id,
                model=model,
                res_id=res_id,
                request=request.id,
            )
            raise UserError(
                self.env._(
                    "%(record)s is already approved for this.",
                    record=records.display_name,
                ),
            )
        if request.state != "pending":
            binding._check_someone_asked(records, request)
            request = binding._raise_requests_for(records)
        request = request.with_user(self.env.user)
        trace.BUTTON.note(
            "decide",
            binding=binding.id,
            model=model,
            res_id=res_id,
            request=request.id,
            approve=approve,
            steps=steps.ids if steps else None,
            uid=self.env.uid,
        )
        if approve:
            request.action_approve(steps=steps)
        else:
            request.with_context(skip_wizard=True).action_refuse(steps=steps)
        return self._get_button_approval(model, res_id, method, action_id)

    @api.model
    def action_withdraw_decision(
        self,
        model: str,
        res_id: int,
        method=False,
        action_id=False,
        approver_id=False,
        step_id=False,
    ) -> dict[str, Any]:
        records = self._get_records_for_button(model, res_id, "write")
        binding = self._get_button_binding_for(records, method, action_id)
        request = binding._get_button_request(records)
        if not request:
            trace.REFUSAL.event(
                "button_nothing_decided",
                binding=binding.id,
                model=model,
                res_id=res_id,
            )
            raise UserError(
                self.env._(
                    "Nothing has been decided on %(record)s yet.",
                    record=records.display_name,
                ),
            )
        request = request.with_user(self.env.user)
        trace.BUTTON.note(
            "withdraw",
            binding=binding.id,
            model=model,
            res_id=res_id,
            request=request.id,
            state=request.state,
            approver=approver_id or None,
            step=step_id or None,
        )
        if request.state == "refused":
            request.action_reset_to_draft()
        else:
            request.action_withdraw_approver(approver_id, step_id)
        return self._get_button_approval(model, res_id, method, action_id)

    @api.model
    def _get_button_approval(
        self, model: str, res_id=False, method=False, action_id=False
    ) -> dict[str, Any]:
        return self._get_button_approvals_for(model, [res_id], method, action_id)[0]

    @api.model
    def _get_button_approvals_for(
        self,
        model: str,
        res_ids: list,
        method=False,
        action_id=False,
        configured: bool = False,
    ) -> list[dict[str, Any]]:
        ungated = {"gated": False, "approved": True, "request": False, "steps": []}
        if not (configured or self._enabled()):
            return [ungated] * len(res_ids)
        bindings = self._get_button_bindings(model, method, action_id).filtered(
            lambda binding: binding.mode not in ("advise", "act_decides")
        )
        if not bindings:
            return [ungated] * len(res_ids)
        records = self._get_records_for_button(model, [i for i in res_ids if i])
        none = records.browse()
        selected = {binding: binding._get_selected(records) for binding in bindings}
        covered = {
            binding: binding._get_covered_ids(chosen)
            for binding, chosen in selected.items()
        }
        requests = {
            binding: binding._get_latest_requests(chosen)
            for binding, chosen in selected.items()
        }
        user = self.env.user
        answers = []
        for res_id in res_ids:
            record = records.browse(int(res_id)) & records if res_id else none
            gating = (
                bindings.filtered(
                    lambda binding, record=record: record in selected[binding]
                )
                if record
                else bindings
            )
            if not gating:
                answers.append(ungated)
                continue
            waiting = gating.filtered(
                lambda binding, record=record: (
                    not record or record.id not in covered[binding]
                )
            )
            binding = (waiting or gating)[:1]
            request = requests[binding].get(record.id, self.env["approval.request"])
            trace.BUTTON.event(
                "state",
                model=model,
                res_id=res_id or None,
                bindings=gating.ids,
                waiting=waiting.ids,
                binding=binding.id,
                request=request.id,
            )
            answers.append(
                {
                    "gated": True,
                    "approved": bool(record) and not waiting,
                    "request": {
                        "id": request.id,
                        "state": request.state,
                        "can_reopen": request._is_standing_refusal()
                        and request._can_reopen_refusal(user),
                    }
                    if request
                    else False,
                    "steps": binding._get_button_steps(request, record),
                }
            )
        return answers

    @api.model
    def _get_records_for_button(self, model: str, res_id, operation: str = "read"):
        records = self.env[model]
        records.check_access(operation)
        res_ids = res_id if isinstance(res_id, list) else [res_id] if res_id else []
        if res_ids:
            records = records.browse([int(i) for i in res_ids]).exists()
            records.check_access(operation)
        return records

    @api.model
    def _get_button_bindings(self, model: str, method, action_id):
        if method:
            bindings = self._bindings_for(model, method)
        else:
            action = self._parse_button_action(action_id)
            bindings = self._bindings_for_action(action) if action else self.browse()
        return bindings.filtered(lambda binding: binding.model_name == model)

    @api.model
    def _parse_button_action(self, action) -> int | bool:
        if not action:
            return False
        if isinstance(action, int) or str(action).isdecimal():
            return int(action)
        record = self.env.ref(str(action), raise_if_not_found=False)
        return record.id if record else False

    @api.model
    def _get_button_binding_for(self, records, method, action_id):
        bindings = self._get_button_bindings(records._name, method, action_id).filtered(
            lambda binding: (
                binding.mode not in ("advise", "act_decides")
                and binding._get_selected(records)
            )
        )
        if not records or not bindings:
            trace.REFUSAL.event(
                "button_not_gated",
                model=records._name,
                res_id=records.id,
                method=method or None,
                action=action_id or None,
            )
            raise UserError(
                self.env._(
                    "No approval is asked for this on %(record)s.",
                    record=records.display_name,
                ),
            )
        waiting = bindings.filtered(
            lambda binding: records.id not in binding._get_covered_ids(records)
        )
        return (waiting or bindings)[:1]

    def _get_button_decision_steps(self, step_id):
        self.check_singleton()
        if not step_id:
            return None
        steps = self.category_id.sudo().step_ids.filtered(
            lambda step: step.id == int(step_id)
        )
        if not steps:
            trace.REFUSAL.event("button_step_foreign", binding=self.id, step=step_id)
            raise UserError(self.env._("That step does not gate this button."))
        return steps.sudo(False)

    def _get_button_request(self, record):
        return self._get_latest_requests(record).get(
            record.id, self.env["approval.request"]
        )

    def _check_someone_asked(self, records, request) -> None:
        self.check_singleton()
        if (
            "approval_request_id" in records._fields
            or request.state in ("new", "refused")
            or self.category_id.allow_self_approval
        ):
            return
        trace.REFUSAL.event(
            "button_nobody_asked", binding=self.id, records=records, request=request.id
        )
        raise UserError(
            self.env._(
                "Nobody has asked for %(operation)s on %(record)s yet: it is asked "
                "when someone clicks its button.",
                operation=self._get_operation_label(),
                record=records.display_name,
            )
        )

    def _get_button_steps(self, request, record) -> list[dict[str, Any]]:
        self.check_singleton()
        user = self.env.user
        rows = request.approver_ids
        is_open = not request or request.state in ("new", "pending")
        decided = rows.filtered(
            lambda a: a.state in ("approved", "refused") and a.decided_by_user_id
        )
        steps = rows.step_ids or self.category_id.sudo().step_ids.filtered(
            lambda step: (
                step.active and (not record or step._is_applicable_to_document(record))
            )
        )
        if not steps:
            trace.BUTTON.event(
                "steps_flat",
                binding=self.id,
                request=request.id,
                rows=rows.ids,
                decided=decided.ids,
                open=is_open,
            )
            return [self._get_button_flat_step(request, rows, decided, user, is_open)]
        assignment = request._get_step_assignment() if request else {}
        company = (
            request.company_id
            or (
                record.company_id
                if record and "company_id" in record._fields
                else False
            )
            or self.env.company
        )
        routed = {
            step.id: request._get_routed_step(step) if request else step
            for step in steps
        }
        drawn = [
            {
                "id": step.id,
                "name": step.name,
                "sequence": routed[step.id].sequence,
                "minimum": routed[step.id].minimum,
                "exclusive": routed[step.id].exclusive,
                "can_decide": is_open
                and user.id in step._get_pool_user_ids(record, company)
                and (not request or request._can_decide_step(step, user)),
                "decisions": [
                    self._get_button_decision(row, request, user, step)
                    for row in assignment.get(step.id, rows.browse())
                    | decided.filtered(
                        lambda a, step=step: (
                            a.state == "refused" and step in a.decided_step_ids
                        )
                    )
                ],
            }
            for step in steps.sorted(lambda step: (routed[step.id].sequence, step.id))
        ]
        trace.BUTTON.event(
            "steps_drawn",
            binding=self.id,
            request=request.id,
            steps=[step["id"] for step in drawn],
            decidable=[step["id"] for step in drawn if step["can_decide"]],
            company=company.id,
        )
        trace.BUTTON.items(
            "step_drawn",
            lambda: [
                {
                    "step": step["id"],
                    "minimum": step["minimum"],
                    "exclusive": step["exclusive"],
                    "can_decide": step["can_decide"],
                    "decisions": len(step["decisions"]),
                }
                for step in drawn
            ],
        )
        return drawn

    def _get_button_flat_step(self, request, rows, decided, user, is_open) -> dict:
        self.check_singleton()
        category = self.category_id.sudo()
        asked = any(
            row._get_effective_approver() == user and row not in decided for row in rows
        )
        trace.BUTTON.event(
            "flat_step_drawn",
            binding=self.id,
            request=request.id or None,
            category=category.id,
            asked=asked,
            can_decide=is_open and asked,
            decisions=decided.ids,
        )
        return {
            "id": False,
            "name": category.name,
            "sequence": 0,
            "minimum": request.approval_minimum
            if request
            else category.approval_minimum,
            "exclusive": False,
            "can_decide": is_open and asked,
            "decisions": [
                self._get_button_decision(row, request, user) for row in decided
            ],
        }

    @api.model
    def _get_button_decision(self, row, request, user, step=None) -> dict[str, Any]:
        actor = row.decided_by_user_id
        return {
            "approver_id": row.id,
            "user_id": actor.id,
            "user_name": actor.name,
            "state": row.state,
            "date": fields.Datetime.to_string(row.decision_date)
            if row.decision_date
            else False,
            "can_withdraw": row.state == "approved"
            and request.state in ("pending", "approved")
            and request._can_withdraw_approver(row, user, step),
        }
