from odoo import fields, models
from odoo.exceptions import UserError

from . import approval_trace as trace
from .approval_utils import ApprovalStepUnstaffed

ASK_ADMISSION = "approval.ask:"
GRANT_RUN_ADMISSION = "approval.grant_run"


class MixinApprovalGate(models.AbstractModel):
    _name = "mixin.approval.gate"
    _inherit = ["mixin.approval"]
    _description = "Operation Gated by Approval"

    def _check_before_approval(self, verb):
        pass

    def _run_through_approval(self, operation, run):
        ready, need_approval = self._split_for_approval(operation)
        result = True
        if ready:
            result = ready._run_admitted(operation, run)
            ready._stamp_operation_run(operation)
        if not need_approval:
            return result
        trace.MIXIN.note(
            "operation_needs_approval",
            records=need_approval,
            operation=operation,
            ran=len(ready),
        )
        drafted = need_approval.filtered(
            lambda record: record._get_own_approval_request().state == "new"
        )
        if len(self) == 1 and drafted:
            return drafted._submit_drafted_approval(operation)
        asked, blocked = drafted._submit_drafted_approval_each(operation)
        fresh = need_approval - drafted
        with self.env.transaction.admitting(
            fresh._name, ASK_ADMISSION + operation, fresh.ids
        ):
            if len(self) == 1:
                return fresh.action_create_approval_request()
            if fresh:
                fresh_asked, fresh_blocked = fresh._ask_approval_each()
                asked |= fresh_asked
                blocked += fresh_blocked
        return self._get_approval_asked_notification(
            operation, ready, asked, result, blocked
        )

    def _submit_drafted_approval(self, operation):
        self.check_singleton()
        request = self._get_own_approval_request()
        if not self._submits_approval_request_on_raise():
            trace.MIXIN.note(
                "drafted_approval_left_to_owner", record=self, operation=operation
            )
            return self._get_approval_submitted_action(request)
        trace.MIXIN.note("drafted_approval_submitted", record=self, operation=operation)
        request.action_confirm()
        self.message_post(
            body=self.env._(
                "%(request)s was submitted again for %(operation)s, for what "
                "%(name)s holds now.",
                request=request.display_name,
                operation=operation,
                name=self.display_name,
            ),
            message_type="notification",
        )
        return self._get_approval_submitted_action(request)

    def _submit_drafted_approval_each(self, operation) -> tuple:
        asked = self.browse()
        blocked = []
        for record in self:
            try:
                with self.env.cr.savepoint():
                    record._submit_drafted_approval(operation)
            except ApprovalStepUnstaffed as error:
                trace.MIXIN.event(
                    "drafted_approval_unstaffed", record=record, operation=operation
                )
                blocked.append((record, error))
            else:
                asked |= record
        return asked, blocked

    def _ask_approval_each(self) -> tuple:
        self.env.flush_all()
        try:
            with self.env.cr.savepoint():
                self._raise_approval_requests()
        except ApprovalStepUnstaffed:
            trace.MIXIN.event("batch_not_asked_unstaffed", records=self)
        else:
            return self, []
        asked = self.browse()
        blocked = []
        for record in self:
            try:
                with self.env.cr.savepoint():
                    record._raise_approval_requests()
            except ApprovalStepUnstaffed as error:
                trace.MIXIN.event(
                    "approval_not_asked_unstaffed",
                    record=record,
                    step=error.step.id if error.step else None,
                    company=error.company.id if error.company else None,
                )
                blocked.append((record, error))
            else:
                asked |= record
        return asked, blocked

    def _get_approval_asked_headline(self, ready, need_approval, blocked=()) -> str:
        if blocked:
            return self.env._(
                "%(sent)s sent for approval; %(ran)s went through; "
                "%(blocked)s could not be sent.",
                sent=len(need_approval),
                ran=len(ready),
                blocked=len(blocked),
            )
        return self.env._(
            "%(sent)s sent for approval; %(ran)s went through.",
            sent=len(need_approval),
            ran=len(ready),
        )

    def _get_approval_unstaffed_note(self, error) -> str:
        self.check_singleton()
        step = error.step
        company = error.company
        if not step or not company:
            return self.env._(
                "%(name)s could not be sent for approval: no approver is configured.",
                name=self.display_name,
            )
        return self.env._(
            "%(name)s could not be sent for approval: nobody in %(company)s can "
            "approve step %(step)s.",
            name=self.display_name,
            company=company.display_name,
            step=step.name,
        )

    def _get_approval_asked_notification(
        self, operation, ready, need_approval, result, blocked=()
    ) -> dict:
        params = {
            "type": "warning",
            "title": self.env._("Approval Required"),
            "message": "\n".join(
                [
                    self._get_approval_asked_headline(ready, need_approval, blocked),
                    *(
                        record._get_approval_unstaffed_note(error)
                        for record, error in blocked
                    ),
                ]
            ),
            "sticky": bool(blocked),
        }
        if isinstance(result, dict):
            params["next"] = result
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": params,
        }

    def _split_for_approval(self, operation) -> tuple:
        self.invalidate_recordset(["approval_required"])
        ready = need_approval = self.browse()
        for record in self:
            state = record.approval_state if record.approval_request_id else False
            other_operation = False
            if state and not record._approval_request_gates(operation):
                other_operation = bool(record._get_own_approval_request())
                state = False
            if state == "pending":
                trace.REFUSAL.event(
                    "operation_approval_pending", record=record, operation=operation
                )
                raise UserError(
                    self.env._(
                        "%(name)s is pending approval: wait for the decision, "
                        "or ask an approver to refuse it so the document can change.",
                        name=record.display_name,
                    )
                )
            if state == "new":
                need_approval |= record
            elif state == "approved":
                if record.id in self.env.transaction.admitted_ids(
                    record._name, GRANT_RUN_ADMISSION
                ):
                    record._check_approval_covers(operation)
                    ready |= record
                elif record._is_approval_covering(operation):
                    ready |= record
                else:
                    record._reset_approval_not_covering(operation)
                    need_approval |= record
            elif not record.approval_required:
                ready |= record
            elif state and record._is_approval_reasked_after_refusal(operation):
                record._clear_refused_approval_link()
                need_approval |= record
            elif state:
                trace.REFUSAL.event(
                    "operation_approval_refused", record=record, operation=operation
                )
                raise UserError(
                    self.env._(
                        "The approval of %(name)s was refused or cancelled. "
                        "Reset it to draft to ask again.",
                        name=record.display_name,
                    )
                )
            else:
                if other_operation:
                    record._release_approval_of_other_operation(operation)
                need_approval |= record
        return ready, need_approval

    def _get_own_approval_request(self):
        self.check_singleton()
        request = self.approval_request_id.sudo()
        if not request:
            return request
        return request if request.get_source_document() == self else request.browse()

    def _release_approval_of_other_operation(self, operation) -> None:
        self.check_singleton()
        request = self._get_own_approval_request()
        if request.state in ("new", "pending"):
            trace.REFUSAL.event(
                "other_operation_pending",
                record=self,
                operation=operation,
                request=request.id,
            )
            raise UserError(
                self.env._(
                    "%(name)s is waiting for an approval of %(other)s: it is decided "
                    "before %(operation)s can be asked for.",
                    name=self.display_name,
                    other=request.operation,
                    operation=operation,
                )
            )
        if request.state == "approved" and not request.date_operation_run:
            trace.REFUSAL.event(
                "other_operation_unused",
                record=self,
                operation=operation,
                request=request.id,
            )
            raise UserError(
                self.env._(
                    "%(name)s holds an approval of %(other)s that has not been used "
                    "yet. Run %(other)s, or reset that approval, before asking for "
                    "%(operation)s.",
                    name=self.display_name,
                    other=request.operation,
                    operation=operation,
                )
            )
        trace.MIXIN.note(
            "approval_released_for_another_operation",
            record=self,
            operation=operation,
            request=request.id,
        )
        self.approval_request_id = False
        self.message_post(
            body=self.env._(
                "%(request)s, for %(other)s, stays with its history; %(operation)s "
                "is asked for on its own.",
                request=request.display_name,
                other=request.operation,
                operation=operation,
            ),
            message_type="notification",
        )

    def _is_approval_reasked_after_refusal(self, operation) -> bool:
        self.check_singleton()
        return False

    def _approval_request_gates(self, operation) -> bool:
        request = self._get_own_approval_request()
        if not request:
            return False
        asked_for = request.operation
        return not asked_for or asked_for in self._get_operation_names(operation)

    def _get_operation_names(self, operation):
        verb = self.env["approval.binding"]._get_declared_verb(self, operation)
        return (operation, *verb.methods) if verb else (operation,)

    def _get_operation_door(self, operation):
        verb = self.env["approval.binding"]._get_declared_verb(self, operation)
        return verb.methods[0] if verb and verb.methods else operation

    def _get_approval_snapshot(self, operation):
        self.check_singleton()
        return {}

    def _check_approval_covers(self, operation) -> None:
        self.check_singleton()
        approved = self.approval_request_id.operation_snapshot
        if not approved:
            return
        current = self._get_approval_snapshot(operation)
        if any(current.get(key) != value for key, value in approved.items()):
            trace.REFUSAL.event(
                "operation_snapshot_moved", record=self, operation=operation
            )
            raise UserError(
                self.env._(
                    "What was approved is no longer what is there: %(name)s changed "
                    "after its approval was granted. Undo the change, or run the "
                    "operation from the document, which asks for approval again.",
                    name=self.display_name,
                )
            )

    def _is_approval_covering(self, operation) -> bool:
        try:
            self._check_approval_covers(operation)
        except UserError as error:
            trace.MIXIN.event(
                "approval_no_longer_covers",
                record=self,
                operation=operation,
                reason=str(error),
            )
            return False
        return True

    def _reset_approval_not_covering(self, operation) -> None:
        self.check_singleton()
        request = self._get_own_approval_request()
        request._check_reset_allowed()
        trace.MIXIN.note(
            "approval_reset_not_covering",
            record=self,
            operation=operation,
            request=request.id,
        )
        request._force_draft(
            note=self.env._(
                "%(name)s changed after its approval was granted, so the approval "
                "no longer covers %(operation)s.",
                name=self.display_name,
                operation=operation,
            )
        )

    def _run_admitted(self, operation, run):
        return self.env["approval.binding"]._run_admitted(self, operation, run)

    def _get_admitted_ids(self, operation):
        return self.env["approval.binding"]._get_admitted_ids(self, operation)

    def _is_approval_granted_for(self, operation) -> bool:
        self.check_singleton()
        return bool(
            self.approval_request_id
            and self.approval_state == "approved"
            and self._approval_request_gates(operation)
        )

    def _get_approval_held(self, operation):
        admitted = self._get_admitted_ids(operation)
        self.invalidate_recordset(["approval_required"])
        return self.filtered(
            lambda record: (
                record.id not in admitted
                and not record._is_approval_granted_for(operation)
                and (
                    record.approval_required
                    or (
                        record.approval_request_id
                        and record.approval_state in ("new", "pending")
                    )
                )
            )
        )

    def _check_approval_admits(self, operation, enforced=True, binding=None) -> None:
        admitted = self._get_admitted_ids(operation)
        for record in self.filtered(
            lambda r: r.id not in admitted and r._is_approval_granted_for(operation)
        ):
            record._check_approval_covers(operation)
        blocked = self._get_approval_held(operation)
        if not blocked:
            return
        self.env["approval.observation"].sudo().create(
            [
                {
                    "binding_id": binding.id if binding else False,
                    "model_name": record._name,
                    "operation": operation,
                    "res_id": record.id,
                    "user_id": self.env.uid,
                    "elevation": self.env["approval.binding"]._elevation(),
                    "would_block": True,
                }
                for record in blocked
            ]
        )
        if not enforced:
            trace.MIXIN.note(
                "gate_observed", records=blocked, operation=operation, enforced=False
            )
            return
        trace.REFUSAL.event("gate_bypassed", records=blocked, operation=operation)
        raise UserError(
            self.env._(
                "%(records)s need an approval before %(operation)s can run, and this "
                "way of running it cannot ask for one. Use %(operation)s itself, "
                "which raises the request.",
                records=", ".join(blocked.mapped("display_name")),
                operation=operation,
            )
        )

    def _stamp_operation_run(self, operation) -> None:
        granted = self.filtered(
            lambda record: (
                record.approval_state == "approved"
                and record._approval_request_gates(operation)
            )
        )
        if not granted:
            return
        own = [record._get_own_approval_request() for record in granted]
        requests = (
            own[0]
            .union(*own[1:])
            .filtered(lambda request: not request.date_operation_run)
        )
        if requests:
            trace.MIXIN.note(
                "operation_ran_by_hand", records=granted, operation=operation
            )
            requests.date_operation_run = fields.Datetime.now()

    def _get_approval_refresh_values(self, request):
        values = super()._get_approval_refresh_values(request)
        if operation := request.operation or self._get_gated_operation():
            values["operation_snapshot"] = self._get_approval_snapshot(operation)
        return values

    def _is_approval_acted_on(self) -> bool:
        return bool(self._get_own_approval_request().date_operation_run)

    def _is_operation_run_on_approval(self, operation) -> bool:
        self.check_singleton()
        return True

    def _on_approval_approved(self) -> None:
        super()._on_approval_approved()
        self._run_operation_on_approval()

    def _run_operation_on_approval(self) -> None:
        request = self._get_own_approval_request()
        operation = request.operation or self._get_gated_operation()
        if not request or not operation or request.date_operation_run:
            return
        if not self._is_operation_run_on_approval(operation):
            return
        trace.MIXIN.note("operation_on_approval", record=self, operation=operation)
        document = request._as_owner(self)
        with (
            self._approval_side_effect(self._get_operation_failure_note(operation)),
            self.env.transaction.admitting(self._name, GRANT_RUN_ADMISSION, self.ids),
        ):
            request.date_operation_run = fields.Datetime.now()
            getattr(document, self._get_operation_door(operation))()

    def _get_operation_failure_note(self, operation) -> str:
        self.check_singleton()
        return self.env._(
            "Approval was granted, but the document could not go through: %(error)s"
        )

    def _get_gated_operation(self):
        self.check_singleton()
        return self.env["approval.binding"]._get_own_verb(self) or False

    def _get_asked_operation(self):
        (record,) = self
        for name in self.env.transaction.admitted_names(record._name, record.id):
            if name.startswith(ASK_ADMISSION):
                return name.removeprefix(ASK_ADMISSION)
        return False

    def _prepare_approval_request_values(self, category):
        values = super()._prepare_approval_request_values(category)
        operation = self._get_asked_operation() or self._get_gated_operation()
        if operation:
            values["operation"] = operation
            values["operation_snapshot"] = self._get_approval_snapshot(operation)
        return values
