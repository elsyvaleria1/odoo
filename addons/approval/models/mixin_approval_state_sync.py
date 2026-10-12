from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import TYPE_CHECKING, Any, Literal, Self

from odoo import SUPERUSER_ID, api, models
from odoo.api import ValuesType
from odoo.fields import Domain

from . import approval_trace as trace
from .approval_utils import ApprovalStepUnstaffed

if TYPE_CHECKING:
    from .approval_request import ApprovalRequest
    from .res_users import ResUsers

SYNC_ADMISSION = "approval.state_sync"


class MixinApprovalStateSync(models.AbstractModel):
    _name = "mixin.approval.state.sync"
    _inherit = ["mixin.approval"]
    _description = "Approval Request Following Its Document's State"
    _approval_request_follows_document = True

    def _get_approval_sync_state_field(self) -> str:
        return "state"

    def _get_approval_sync_kinds(self) -> dict[Any, str]:
        raise NotImplementedError

    def _get_approval_sync_kind(self) -> str | None:
        self.check_singleton()
        field = self._get_approval_sync_state_field()
        kinds = self._get_approval_sync_kinds()
        value = self[field]
        kind = kinds.get(value)
        if kind is None:
            trace.DEGRADED.event(
                "sync_state_unmapped",
                record=self,
                field=field,
                value=value,
                mapped=sorted(kinds, key=repr),
            )
        return kind

    def _check_approval_sync_policy(self, kind: str) -> None:
        return

    def _apply_approval_sync_outcome(self, kind: str) -> None:
        raise NotImplementedError

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        records = super().create(vals_list)
        records._create_approval_requests()
        return records

    def _approval_move_decided(self, verb: str) -> None:
        synced = self.env.transaction.admitted_ids("approval.request", SYNC_ADMISSION)
        with_request = self.filtered(
            lambda record: (
                record.sudo().approval_request_id
                and record.sudo().approval_request_id.id not in synced
            )
        )
        trace.SYNC.event(
            "document_moved",
            record=self,
            field=self._get_approval_sync_state_field(),
            verb=verb,
            moved=self.ids,
            with_request=with_request.ids,
            already_synced=list(synced),
        )
        with_request._sync_approval_request()
        (
            self.filtered(lambda record: not record.sudo().approval_request_id)
        )._create_approval_requests()

    def _get_approval_sync_model(self) -> str:
        return self._name

    def _get_approval_sync_verb(self, value: Any) -> str | None:
        field = self._get_approval_sync_state_field()
        transitions = self.env.registry.verb_transitions.get(
            self._get_approval_sync_model(), {}
        )
        for name, verb in transitions.get(field, ()):
            if verb.transition[2] == value:
                return name
        return None

    def _get_approval_outcome_value(self, kind: str) -> Any:
        values = [
            value
            for value, value_kind in self._get_approval_sync_kinds().items()
            if value_kind == kind
        ]
        return values[0] if len(values) == 1 else None

    def unlink(self) -> Literal[True]:
        for record in self.sudo().filtered(
            lambda record: record.approval_request_id.state == "pending"
        ):
            request = record._get_synced_approval_request()
            with record._approval_sync_admitted(request):
                request._force_terminal(
                    "cancelled",
                    self.env._(
                        "%(user)s deleted %(record)s.",
                        user=self.env.user.name,
                        record=record.display_name,
                    ),
                )
        return super().unlink()

    def _is_approval_request_required(self) -> bool:
        self.check_singleton()
        kind = self._get_approval_sync_kind()
        can_raise = kind == "pending" and self._can_raise_approval_request()
        trace.SYNC.event(
            "request_needed",
            record=self,
            kind=kind,
            has_request=bool(self.approval_request_id),
            needed=can_raise,
        )
        return can_raise

    def _can_raise_approval_request(self) -> bool:
        self.check_singleton()
        return not self.approval_request_id and self.approval_required

    def _create_approval_requests(self) -> None:
        if self.env.uid == SUPERUSER_ID or self.env.context.get("import_file"):
            return
        records = self.sudo()
        needing = records.browse()
        for record in records:
            needs = record._is_approval_request_required()
            trace.SYNC.event(
                "raise_on_create",
                model=record._name,
                res_id=record.id,
                kind=record._get_approval_sync_kind(),
                raises=needs,
            )
            if needs:
                needing |= record
        if not needing:
            return
        self.env.flush_all()
        try:
            with self.env.cr.savepoint():
                needing._raise_approval_requests()
        except ApprovalStepUnstaffed:
            trace.SYNC.event("batch_not_raised_unstaffed", records=needing)
            for record in needing:
                record._raise_approval_request_on_create()

    def _raise_approval_request_on_create(self) -> None:
        self.check_singleton()
        self.env.flush_all()
        try:
            with self.env.cr.savepoint():
                self.action_create_approval_request()
        except ApprovalStepUnstaffed as error:
            trace.SYNC.event(
                "raise_on_create_refused",
                record=self,
                kind=self._get_approval_sync_kind(),
                reason=str(error),
            )
            self.message_post(
                body=self.env._(
                    "No approval request could be raised for this document yet: "
                    "%(reason)s",
                    reason=str(error),
                ),
                message_type="notification",
            )

    def _get_synced_approval_request(self) -> ApprovalRequest:
        self.check_singleton()
        return self.sudo().approval_request_id

    @contextmanager
    def _approval_sync_admitted(self, request: ApprovalRequest) -> Iterator[None]:
        with self.env.transaction.admitting(
            "approval.request", SYNC_ADMISSION, request.ids
        ):
            yield

    def _is_synced_with_approval_request(self) -> bool:
        self.check_singleton()
        synced = self.env.transaction.admitted_ids("approval.request", SYNC_ADMISSION)
        reentrant = self.approval_request_id.id in synced
        if reentrant:
            trace.SYNC.event(
                "sync_reentry_blocked",
                record=self,
                request=self.approval_request_id.id,
                depth=len(synced),
            )
        return reentrant

    def _restart_approval_request(self, request: ApprovalRequest) -> None:
        trace.SYNC.note(
            "restart_request",
            record=self,
            request=request.id,
            was=request.state,
            forced_draft=request.state != "new",
        )
        if request.state != "new":
            request._force_draft()
        request.action_confirm()

    def _sync_approval_request(self) -> None:
        user = self.env.user
        decides = self.env.uid != SUPERUSER_ID
        for record in self:
            request = record._get_synced_approval_request()
            kind = record._get_approval_sync_kind()
            trace.SYNC.note(
                "sync_request",
                model=record._name,
                res_id=record.id,
                request=request.id,
                kind=kind,
                request_state=request.state,
                decides=decides,
            )
            with record._approval_sync_admitted(request):
                if kind == "pending":
                    record._restart_approval_request(request)
                elif kind == "draft":
                    if request.state != "new":
                        request._force_draft()
                elif kind in ("progress", "approved"):
                    record._sync_approval_request_approval(request, user, decides, kind)
                elif kind in ("refused", "cancelled"):
                    record._sync_approval_request_ending(request, user, decides, kind)

    def _sync_approval_request_approval(
        self, request: ApprovalRequest, user: ResUsers, decides: bool, kind: str
    ) -> None:
        self.check_singleton()
        if request.state in ("new", "refused", "cancelled"):
            self._restart_approval_request(request)
        if request.state != "pending":
            return
        rows = (
            request._get_rows_decidable_by(user)
            if decides
            else request.approver_ids.browse()
        )
        if kind == "progress":
            steps = request._get_open_steps()
            rows = rows.filtered(lambda row: steps <= row.step_ids)
            trace.SYNC.event(
                "sync_progress",
                request=request.id,
                steps=steps.ids,
                rows=rows.ids,
                user=user.id,
            )
            if rows:
                request.action_approve(approver=rows, steps=steps)
            return
        if rows:
            request.action_approve(approver=rows)
        trace.SYNC.event(
            "sync_approved",
            request=request.id,
            rows=rows.ids,
            state=request.state,
            grants=request.state == "pending",
        )
        if request.state == "pending":
            request._approve_without_decision(
                self.env._(
                    "%(user)s approved %(record)s without an approver's decision.",
                    user=user.name,
                    record=self.display_name,
                )
            )

    def _sync_approval_request_ending(
        self, request: ApprovalRequest, user: ResUsers, decides: bool, kind: str
    ) -> None:
        self.check_singleton()
        refused = kind == "refused"
        target = "refused" if refused else "cancelled"
        note = self.env.context.get("approval_refusal_note") if refused else None
        if request.state == "approved":
            request._revoke(
                target,
                self.env._(
                    "%(user)s refused %(record)s after it was approved.",
                    user=user.name,
                    record=self.display_name,
                )
                if refused
                else self.env._(
                    "%(user)s cancelled %(record)s after it was approved.",
                    user=user.name,
                    record=self.display_name,
                ),
                refusal_note=note,
            )
            return
        if request.state not in ("new", "pending"):
            return
        rows = (
            request._get_current_pending_approver(user)
            if decides and refused and request.state == "pending"
            else request.approver_ids.browse()
        )
        trace.SYNC.event(
            "sync_ending",
            request=request.id,
            target=target,
            state=request.state,
            rows=rows.ids,
            noted=bool(note),
        )
        if rows:
            request.action_refuse(approver=rows)
            if note:
                request._stamp_refusal_metadata(None, note)
            return
        request._force_terminal(
            target,
            self.env._(
                "%(user)s refused %(record)s.", user=user.name, record=self.display_name
            )
            if refused
            else self.env._(
                "%(user)s cancelled %(record)s.",
                user=user.name,
                record=self.display_name,
            ),
            refusal_note=note,
        )

    def _apply_approval_outcome(self, kind: str, decided: bool = True) -> None:
        self.check_singleton()
        value = self._get_approval_outcome_value(kind)
        verb = self._get_approval_sync_verb(value) if value is not None else None
        trace.SYNC.note(
            "apply_outcome",
            record=self,
            kind=kind,
            decided=decided,
            verb=verb,
            request=self.approval_request_id.id,
        )
        checks_policy = decided and self.env.uid != SUPERUSER_ID
        trace.SYNC.event(
            "sync_policy",
            record=self,
            kind=kind,
            checked=checks_policy,
            uid=self.env.uid,
        )
        if checks_policy:
            decider = self.sudo(False)
            decider._check_approval_sync_policy(kind)
            if verb:
                decider._check_approval_decider_holds(verb)
        with (
            self.env.transaction.admitting(
                self._get_approval_sync_model(), verb, self.ids
            )
            if verb
            else nullcontext(),
            self._approval_sync_admitted(self.approval_request_id),
        ):
            self._apply_approval_sync_outcome(kind)

    def _check_approval_decider_holds(self, verb: str) -> None:
        self.check_singleton()
        permissions, guards = self.env["ir.access"]._bound_access_rows(
            self._get_approval_sync_model(), verb
        )
        holds = bool(permissions) and bool(
            self.sudo()
            .with_context(active_test=False)
            .filtered_domain(Domain.OR(permissions) & Domain.AND(guards))
        )
        trace.SYNC.event("decider_holds", record=self, verb=verb, holds=holds)
        if not holds:
            raise self.env["ir.access"]._prepare_record_access_error(self, verb)

    def _on_approval_progress(self) -> None:
        if (
            not self._is_synced_with_approval_request()
            and self._get_approval_sync_kind() == "pending"
        ):
            self._apply_approval_outcome("progress")

    def _on_approval_approved(self) -> None:
        if (
            not self._is_synced_with_approval_request()
            and self._get_approval_sync_kind() != "approved"
        ):
            self._apply_approval_outcome("approved")

    def _on_approval_refused(self) -> None:
        if (
            not self._is_synced_with_approval_request()
            and self._get_approval_sync_kind() != "refused"
        ):
            self._apply_approval_outcome("refused")

    def _on_approval_cancelled(self) -> None:
        if not self._is_synced_with_approval_request() and (
            self._get_approval_sync_kind() not in ("cancelled", "refused")
        ):
            self._apply_approval_outcome("cancelled", decided=False)

    def _on_approval_reset(self) -> None:
        if not self._is_synced_with_approval_request():
            super()._on_approval_reset()

    def _on_approval_revoked(self) -> None:
        if not self._is_synced_with_approval_request():
            super()._on_approval_revoked()
