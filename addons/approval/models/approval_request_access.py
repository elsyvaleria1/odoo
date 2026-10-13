import contextlib
from collections import Counter
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, Self

from odoo import api, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command, CommandValue

from . import approval_trace as trace
from .approval_utils import RAISE_ADMISSION, is_approval_manager

if TYPE_CHECKING:
    from .approval_approver import ApprovalApprover
    from .approval_category import ApprovalCategory
    from .approval_category_step import ApprovalCategoryStep
    from .res_users import ResUsers
    from odoo.addons.base.models.ir_access_exception import IrAccessException

_PRODUCING_REQUESTS = "approval.producing_request_ids"
_RECORD_ADMISSION = "approval.record"


class ApprovalRequestAccess(models.Model):
    _inherit = "approval.request"

    @contextlib.contextmanager
    def _producing_documents(self) -> Iterator[None]:
        self.check_singleton()
        producing = self.env.cr.cache.setdefault(_PRODUCING_REQUESTS, Counter())
        producing[self.id] += 1
        try:
            yield
        finally:
            producing[self.id] -= 1

    def _is_producing_documents(self) -> bool:
        self.check_singleton()
        return self.env.cr.cache.get(_PRODUCING_REQUESTS, {}).get(self.id, 0) > 0

    def _link_produced_documents(self, documents: models.BaseModel) -> None:
        self.check_singleton()
        with self._producing_documents():
            for document in documents:
                document.write({"approval_request_id": self.id})

    @api.constrains("date_start", "date_end")
    def _check_date_consistency(self) -> None:
        for request in self:
            if (
                request.date_start
                and request.date_end
                and request.date_start > request.date_end
            ):
                trace.REFUSAL.event(
                    "date_range_inverted",
                    request=request.id,
                    start=request.date_start,
                    end=request.date_end,
                )
                raise ValidationError(
                    self.env._("End date must be after start date."),
                )

    @api.constrains("category_id", "request_owner_id")
    def _check_category_access(self) -> None:
        for request in self:
            category = request.category_id
            owner = request.request_owner_id

            if not category.allowed_user_ids and not category.allowed_group_ids:
                continue

            if owner in category.allowed_user_ids:
                continue

            if owner in category.allowed_group_ids.all_user_ids:
                continue

            trace.REFUSAL.event(
                "category_not_allowed",
                request=request.id,
                category=category.id,
                owner=owner.id,
            )
            raise ValidationError(
                self.env._(
                    "You are not allowed to create requests for category '%(category)s'.\n\n"
                    "This category is restricted to specific users or groups. "
                    "Please contact your administrator if you need access.",
                    category=category.name,
                ),
            )

    def _raise_category_change_blocked(
        self, previous_category: ApprovalCategory
    ) -> None:
        trace.REFUSAL.event(
            "category_change_after_confirm",
            request=self.id,
            was=previous_category.id,
            state=self.state,
        )
        raise ValidationError(
            self.env._(
                "Cannot change approval category after the request has been confirmed.\n\n"
                "Request: %(name)s\n"
                "Current category: %(category)s\n"
                "Current state: %(state)s\n\n"
                "To change the category, refuse this request and create a new one.",
                name=self.name or self.env._("New"),
                category=previous_category.name,
                state=self.state,
            ),
        )

    def _check_access_unlink(self) -> None:
        if self._skip_check_access():
            return

        for request in self:
            is_owner = request.request_owner_id == self.env.user

            if not is_owner:
                trace.REFUSAL.event(
                    "unlink_not_owner",
                    request=request.id,
                    uid=self.env.uid,
                    owner=request.request_owner_id.id,
                )
                raise AccessError(
                    self.env._(
                        "You can only delete your own approval requests.\n\nRequest: %(name)s\nOwner: %(owner)s",
                        name=request._label(),
                        owner=request.request_owner_id.name,
                    ),
                )

    def _check_access_write(self) -> None:
        if self._skip_check_access() or self._granted_by_privilege("write"):
            return

        current_user = self.env.user
        for request in self:
            if request.request_owner_id == current_user:
                continue
            is_approver = any(
                approver._get_effective_approver() == current_user
                for approver in request.approver_ids
            )
            if is_approver and request.state != "new":
                continue
            if is_approver:
                trace.REFUSAL.event(
                    "write_draft_by_approver",
                    request=request.id,
                    uid=current_user.id,
                )
                raise AccessError(
                    self.env._(
                        "You cannot modify this request while it is still a "
                        "draft — only its owner can. You will be able to "
                        "complete your own fields once it is submitted for "
                        "your approval.\n\n"
                        "Request: %(name)s\nOwner: %(owner)s",
                        name=request._label(),
                        owner=request.request_owner_id.name,
                    ),
                )
            trace.REFUSAL.event(
                "write_not_owner_nor_approver",
                request=request.id,
                uid=current_user.id,
                state=request.state,
            )
            raise AccessError(
                self.env._(
                    "You can only modify approval requests where you "
                    "are the owner or an assigned approver.\n\n"
                    "Request: %(name)s\nOwner: %(owner)s",
                    name=request._label(),
                    owner=request.request_owner_id.name,
                ),
            )

    def _check_routing_fields_after_submit(self, vals: ValuesType) -> None:
        if self._skip_check_access():
            return
        touched = set(vals) & (
            self._get_routing_fields_live() - self._get_fields_locked()
        )
        if not touched:
            return
        for request in self:
            if request.state == "new" or request.request_owner_id == self.env.user:
                continue
            trace.REFUSAL.event(
                "routing_field_after_submit",
                request=request.id,
                uid=self.env.uid,
                fields=sorted(touched),
            )
            raise AccessError(
                self.env._(
                    "Only the request owner or an approval manager can change "
                    "%(fields)s once the request is submitted: it decides who "
                    "approves and how soon the reminders fire.\n\n"
                    "Request: %(name)s",
                    fields=", ".join(sorted(touched)),
                    name=request._label(),
                ),
            )

    def _check_approver_ids_business_rules(
        self, approver_commands: Sequence[CommandValue | list[Any]]
    ) -> None:
        if self.env.su and self.env.context.get("approver_ids_computation"):
            return

        for request in self:
            request_name = request._label()

            for command in approver_commands:
                cmd_type = command[0]

                if cmd_type == Command.UPDATE:
                    continue

                if request.state != "new":
                    trace.REFUSAL.event(
                        "approver_list_after_submit",
                        request=request.id,
                        state=request.state,
                        command=cmd_type,
                    )
                    raise ValidationError(
                        self.env._(
                            "Cannot modify approver list after request is submitted.\n\n"
                            "Request: %(name)s\n"
                            "Current state: %(state)s\n\n"
                            "The approver list can only be modified while the "
                            "request is a draft. Reset a decided request to "
                            "draft first — the approver list is recomputed "
                            "there.",
                            name=request_name,
                            state=request.state,
                        ),
                    )

    _LOCKED_FIELDS = frozenset(
        {
            "amount",
            "currency_id",
            "quantity",
            "date",
            "date_start",
            "date_end",
            "partner_id",
            "reason",
            "request_owner_id",
            "company_id",
            "res_model",
            "res_id",
        },
    )

    _SYSTEM_LOCKED_FIELDS = frozenset({"name"})

    _WORKFLOW_FIELDS = frozenset(
        {
            "applied_rule_ids",
            "approval_minimum",
            "binding_replay_error",
            "category_snapshot",
            "date_binding_replayed",
            "date_confirmed",
            "date_operation_run",
            "date_revoked",
            "escalated_to_manager",
            "granted_by_user_id",
            "last_reminder_date",
            "pending_change_field",
            "refusal_note",
            "refusal_reason_id",
            "reminder_count",
            "revoked_by_user_id",
            "revoked_state",
        },
    )

    _SOURCE_LINK_FIELDS = frozenset(
        {
            "binding_id",
            "binding_snapshot",
            "operation",
            "operation_snapshot",
            "requester_id",
            "res_id",
            "res_model",
            "subject_key",
        },
    )

    _PENDING_CHANGE_EDITABLE = {
        "date": frozenset({"date", "date_start", "date_end"}),
        "reason": frozenset({"reason"}),
    }

    def _get_fields_locked(self) -> frozenset[str]:
        return self._LOCKED_FIELDS

    def _get_pending_change_candidates(self) -> frozenset[str]:
        self.check_singleton()
        if self.date or self.date_start or self.date_end:
            return frozenset({"reason", "date"})
        return frozenset({"reason"})

    _COMPUTE_ONLY_FIELDS = frozenset(
        {
            "state",
            "date_approval_granted",
            "date_refused",
            "date_cancelled",
            "approval_deadline",
            "res_model_id",
        },
    )

    def _check_no_forged_computed_fields(self, vals: ValuesType) -> None:
        forged = set(vals) & self._COMPUTE_ONLY_FIELDS
        if forged:
            trace.REFUSAL.event(
                "forged_computed_fields",
                requests=self.ids,
                uid=self.env.uid,
                fields=sorted(forged),
            )
            raise ValidationError(
                self.env._(
                    "%(fields)s cannot be set directly — these are "
                    "computed by the approval workflow itself and change "
                    "only as a consequence of real approver decisions.",
                    fields=", ".join(sorted(forged)),
                ),
            )

    @api.model
    def _create_raised(self, vals_list: list[ValuesType]) -> Self:
        with contextlib.ExitStack() as stack:
            for vals in vals_list:
                stack.enter_context(
                    self.env.transaction.admitting(
                        vals["res_model"], RAISE_ADMISSION, [vals["res_id"]]
                    )
                )
            return self.create(vals_list)

    def _refresh_from_source(self) -> None:
        self.check_singleton()
        document = self.get_source_document()
        if (
            not document
            or not isinstance(document, self.env.registry["mixin.approval"])
            or not document.exists()
            or document.approval_request_id != self
            or not self._get_requests_with_decision_log()
        ):
            return
        vals = document._get_approval_refresh_values(self)
        trace.LIFECYCLE.event(
            "refreshed_from_source", request=self.id, fields=sorted(vals)
        )
        with (
            self.env.transaction.admitting(
                document._name, RAISE_ADMISSION, document.ids
            ),
            self._recording(),
        ):
            self.write(vals)

    @api.model
    def _is_raised_by_source(self, vals: ValuesType) -> bool:
        return RAISE_ADMISSION in self.env.transaction.admitted_names(
            vals.get("res_model") or "", vals.get("res_id") or 0
        )

    def _are_raised_by_their_sources(self) -> bool:
        return all(
            RAISE_ADMISSION
            in self.env.transaction.admitted_names(request.res_model, request.res_id)
            for request in self
        )

    @contextlib.contextmanager
    def _recording(self) -> Iterator[None]:
        with self.env.transaction.admitting(
            "approval.request", _RECORD_ADMISSION, self.ids
        ):
            yield

    def _is_recording(self) -> bool:
        return bool(self) and set(self.ids) <= self.env.transaction.admitted_ids(
            "approval.request", _RECORD_ADMISSION
        )

    def _without_engine_defaults(self) -> Self:
        owned = self._WORKFLOW_FIELDS | self._SOURCE_LINK_FIELDS
        context = {
            key: value
            for key, value in self.env.context.items()
            if not (key.startswith("default_") and key[8:] in owned)
        }
        if len(context) == len(self.env.context):
            return self
        return self.with_context(context)

    def _check_engine_owned_fields(
        self, vals: ValuesType, create: bool = False
    ) -> None:
        if self.env.su:
            return
        forged = vals.keys() & self._WORKFLOW_FIELDS
        if forged and self._is_recording():
            forged = set()
        linked = vals.keys() & self._SOURCE_LINK_FIELDS
        raised = (
            self._is_raised_by_source(vals)
            if create
            else self._are_raised_by_their_sources()
        )
        if linked and not raised:
            forged |= linked
        if not forged:
            return
        trace.REFUSAL.event(
            "engine_owned_fields",
            requests=self.ids,
            uid=self.env.uid,
            create=create,
            fields=sorted(forged),
        )
        raise AccessError(
            self.env._(
                "%(fields)s cannot be set on an approval request: the approval "
                "workflow records them itself, from the decisions taken and the "
                "document that raised the request.",
                fields=", ".join(sorted(forged)),
            ),
        )

    def _check_locked_fields(self, vals: ValuesType) -> None:
        locked = self._get_fields_locked()
        if not self.env.su:
            locked |= self._SYSTEM_LOCKED_FIELDS
        locked_touched = set(vals) & locked
        if not locked_touched:
            return
        may_apply_change = self.env.su or is_approval_manager(self.env)
        for request in self:
            if request.state == "new":
                continue
            editable = (
                self._PENDING_CHANGE_EDITABLE.get(
                    request.pending_change_field, frozenset()
                )
                if may_apply_change or request.request_owner_id == self.env.user
                else frozenset()
            )
            blocked = locked_touched - editable
            if blocked:
                trace.REFUSAL.event(
                    "locked_fields",
                    request=request.id,
                    uid=self.env.uid,
                    state=request.state,
                    blocked=sorted(blocked),
                    editable=sorted(editable),
                )
                raise ValidationError(
                    self.env._(
                        "Cannot modify %(fields)s after the request has "
                        "been submitted — approvers decide on these "
                        "values.\n\n"
                        "Request: %(name)s\nCurrent state: %(state)s\n\n"
                        "Ask an approver to request a change, or reset "
                        "the request to draft if it was refused or "
                        "cancelled.",
                        fields=", ".join(sorted(blocked)),
                        name=request._label(),
                        state=request.state,
                    ),
                )

    def _check_business_rules_unlink(self) -> None:
        if decided := self._get_requests_with_decision_log():
            trace.REFUSAL.event("unlink_with_decision_log", requests=decided.ids)
            raise ValidationError(
                self.env._(
                    "Cannot delete %(names)s: decisions were recorded about it, and "
                    "a request with a decision history stays on file.",
                    names=", ".join(request._label() for request in decided),
                ),
            )
        for request in self:
            if request.state != "new":
                trace.REFUSAL.event(
                    "unlink_not_draft", request=request.id, state=request.state
                )
                raise ValidationError(
                    self.env._(
                        "Cannot delete requests in %(state)s state.\n\n"
                        "Request: %(name)s\n\n"
                        "Once submitted, requests can only be refused or "
                        "cancelled — they remain on file as part of the "
                        "audit trail.",
                        name=request._label(),
                        state=request.state,
                    ),
                )

    def _get_requests_with_decision_log(self) -> Self:
        logged = (
            self.env["approval.decision.log"]
            .sudo()
            ._read_group([("request_id", "in", self.ids)], ["request_id"])
        )
        return self.browse(request.id for (request,) in logged)

    def _granted_by_privilege(self, operation: str) -> bool:
        if not self.env.privileges:
            return False
        domain = self.env["ir.access"]._privilege_domain("approval.request", operation)
        granted = self.filtered_domain(domain) == self
        if granted:
            trace.ACCESS.event(
                "granted_by_privilege",
                uid=self.env.uid,
                operation=operation,
                record=self,
            )
        return granted

    def _skip_check_access(self) -> bool:
        skipped = self.env.su or is_approval_manager(self.env)
        if skipped:
            trace.ACCESS.event(
                "checks_skipped", uid=self.env.uid, su=self.env.su, record=self
            )
        return skipped

    def _check_reset_actor(self) -> None:
        self.check_singleton()
        standing = self._is_standing_refusal()
        trace.ACCESS.event(
            "reset_actor_rule",
            request=self.id,
            uid=self.env.uid,
            rule="refusal_reopener" if standing else "owner_or_manager",
        )
        if standing:
            self._check_refusal_reopener()
            return
        self._check_owner_or_manager(self.env._("reset to draft"))

    def _is_standing_refusal(self) -> bool:
        self.check_singleton()
        if self.state != "refused" or not self.binding_id:
            trace.ACCESS.event(
                "standing_refusal",
                request=self.id,
                standing=False,
                state=self.state,
                binding=self.binding_id.id or None,
            )
            return False
        document = self.get_source_document()
        standing = not (document and "approval_request_id" in document._fields)
        trace.ACCESS.event(
            "standing_refusal",
            request=self.id,
            standing=standing,
            document=document or None,
            links_back=bool(document) and "approval_request_id" in document._fields,
        )
        return standing

    def _check_refusal_reopener(self) -> None:
        self.check_singleton()
        if self.env.su or self._can_reopen_refusal(self.env.user):
            return
        trace.REFUSAL.event("refusal_stands", request=self.id, uid=self.env.uid)
        raise AccessError(
            self.env._(
                "A refusal on %(name)s stands until whoever refused it, an approval "
                "manager, or a member of a later step reopens it.",
                name=self.display_name,
            ),
        )

    def _can_reopen_refusal(self, user: ResUsers) -> bool:
        self.check_singleton()
        if user._is_approval_manager():
            trace.ACCESS.event(
                "can_reopen_refusal", request=self.id, user=user.id, by="manager"
            )
            return True
        refused = self.approver_ids.filtered(
            lambda a: a.state == "refused" and a.decided_by_user_id,
        )
        is_refuser = user in refused.decided_by_user_id
        later_step = not is_refuser and self._is_later_step_member(refused, user)
        trace.ACCESS.event(
            "can_reopen_refusal",
            request=self.id,
            user=user.id,
            refused=refused.ids,
            by="refuser" if is_refuser else "later_step" if later_step else None,
        )
        return is_refuser or later_step

    def _check_withdraw_actor(
        self,
        approver: ApprovalApprover,
        steps: ApprovalCategoryStep | None = None,
    ) -> None:
        self.check_singleton()
        if self.env.su or self._can_withdraw_approver(approver, self.env.user, steps):
            return
        trace.REFUSAL.event(
            "withdraw_actor",
            request=self.id,
            uid=self.env.uid,
            approver=approver.id,
            steps=steps.ids if steps else None,
        )
        raise AccessError(
            self.env._(
                "Only %(approver)s, an approval manager, or a member of a later step "
                "can withdraw that decision on %(name)s.",
                approver=approver._get_effective_approver().name,
                name=self.display_name,
            ),
        )

    def _can_withdraw_approver(
        self,
        approver: ApprovalApprover,
        user: ResUsers,
        steps: ApprovalCategoryStep | None = None,
    ) -> bool:
        self.check_singleton()
        is_manager = user._is_approval_manager()
        is_own = not is_manager and approver._get_effective_approver() == user
        later_step = (
            not is_manager
            and not is_own
            and self._is_later_step_member(approver, user, steps)
        )
        trace.ACCESS.event(
            "can_withdraw_approver",
            request=self.id,
            approver=approver.id,
            user=user.id,
            by="manager"
            if is_manager
            else "own"
            if is_own
            else "later_step"
            if later_step
            else None,
        )
        return is_manager or is_own or later_step

    def _can_decide_step(self, step: ApprovalCategoryStep, user: ResUsers) -> bool:
        self.check_singleton()
        decided = self.approver_ids.filtered(
            lambda a: (
                a.state in ("approved", "refused")
                and user in (a._get_effective_approver() | a.decided_by_user_id)
            )
        ).decided_step_ids
        can = step not in decided and not (
            decided
            and any(self._get_routed_step(each).exclusive for each in step | decided)
        )
        trace.ACCESS.event(
            "can_decide_step",
            request=self.id,
            step=step.id,
            user=user.id,
            decided=decided.ids,
            can=can,
        )
        return can

    def _get_rows_decidable_by(self, user: ResUsers) -> ApprovalApprover:
        self.check_singleton()
        decidable = self.approver_ids.filtered(
            lambda approver: (
                approver._get_effective_approver() == user
                and (
                    approver.state == "pending"
                    or (
                        approver.state == "approved"
                        and any(
                            self._can_decide_step(step, user)
                            for step in approver.step_ids - approver.decided_step_ids
                        )
                    )
                )
            )
        )
        trace.ACCESS.event(
            "rows_decidable_by",
            request=self.id,
            user=user.id,
            rows=decidable.ids,
            of=self.approver_ids.ids,
        )
        return decidable

    def _is_later_step_member(
        self,
        approvers: ApprovalApprover,
        user: ResUsers,
        steps: ApprovalCategoryStep | None = None,
    ) -> bool:
        self.check_singleton()
        own_steps = steps or approvers.decided_step_ids or approvers.step_ids
        if not own_steps:
            return False
        last = max(self._get_routed_step(step).sequence for step in own_steps)
        document = self.get_source_document()
        is_member = any(
            user.id in step._get_pool_user_ids(document, self.company_id, self)
            for step in self.approver_ids.step_ids
            if self._get_routed_step(step).sequence > last
        )
        trace.ACCESS.event(
            "later_step_member",
            request=self.id,
            user=user.id,
            after=last,
            member=is_member,
        )
        return is_member

    def _check_owner_or_manager(self, action_label: str) -> None:
        if self.env.su or is_approval_manager(self.env):
            return
        for request in self:
            if request.request_owner_id != self.env.user:
                trace.REFUSAL.event(
                    "not_owner_nor_manager",
                    request=request.id,
                    uid=self.env.uid,
                    action=action_label,
                )
                raise AccessError(
                    self.env._(
                        "Only the request owner or an approval manager "
                        "can %(action)s this request.\n\n"
                        "Request: %(name)s\nOwner: %(owner)s",
                        action=action_label,
                        name=request.display_name,
                        owner=request.request_owner_id.name,
                    ),
                )

    def _check_decision_actor(self, approver: ApprovalApprover) -> None:
        self._check_not_deciding_own_request(approver)
        if self.env.su:
            return
        current_user = self.env.user
        impersonated = approver.filtered(
            lambda a: a._get_effective_approver() != current_user,
        )
        if impersonated:
            trace.REFUSAL.event(
                "decision_actor",
                request=self.id,
                uid=current_user.id,
                rows=impersonated.ids,
            )
            raise AccessError(
                self.env._(
                    "You are not the assigned approver for this decision.\n\n"
                    "Request: %(name)s",
                    name=self.display_name,
                ),
            )

    def _check_not_deciding_own_request(self, approver: ApprovalApprover) -> None:
        self.check_singleton()
        own_users = self.request_owner_id | self._get_requester()
        own = approver.filtered(
            lambda a: (a._get_effective_approver() | a.user_id) & own_users
        )
        if not own:
            return
        excluded = self._get_excluded_approvers()
        refused = own.filtered(
            lambda a: (a._get_effective_approver() | a.user_id) & excluded
        )
        if refused:
            person = (refused[0]._get_effective_approver() | refused[0].user_id) & (
                excluded
            )
            trace.REFUSAL.event(
                "decision_on_own_request",
                request=self.id,
                owner=self.request_owner_id.id,
                requester=self._get_requester().id,
                rows=refused.ids,
            )
            raise AccessError(
                self.env._(
                    "%(person)s cannot approve or refuse %(name)s: it was asked by "
                    "them or on their behalf, and its category does not allow "
                    "self-approval.",
                    person=person[:1].name,
                    name=self.display_name,
                )
            )
        if self.category_id.allow_self_approval:
            return
        users = own_users.filtered(
            lambda user: any(
                user in (row._get_effective_approver() | row.user_id) for row in own
            )
        )
        for user in users:
            self._get_own_decision_exception(user)._record_use(self.display_name)

    def _get_requester(self) -> ResUsers:
        self.check_singleton()
        return self.requester_id

    def _get_own_decision_exception(self, user: ResUsers) -> IrAccessException:
        self.check_singleton()
        kind = (
            "self_approval" if user == self.request_owner_id else "requester_exclusion"
        )
        return self.env["ir.access.exception"]._get_exception_active(
            user, kind, self.category_id
        )

    def _get_excluded_approvers(self) -> ResUsers:
        self.check_singleton()
        excluded = self.env["res.users"]
        if self.category_id.allow_self_approval:
            return excluded
        for user in self.request_owner_id | self._get_requester():
            if not self._get_own_decision_exception(user):
                excluded |= user
        return excluded

    @api.constrains("request_owner_id", "company_id", "res_model", "res_id")
    def _check_owner_company(self) -> None:
        for request in self:
            if request.res_model or not request.company_id:
                continue
            if request.company_id not in request.request_owner_id.company_ids:
                trace.REFUSAL.event(
                    "owner_outside_company",
                    request=request.id,
                    owner=request.request_owner_id.id,
                    company=request.company_id.id,
                )
                raise ValidationError(
                    self.env._(
                        "%(owner)s cannot own a request of %(company)s: they do not "
                        "work in that company.",
                        owner=request.request_owner_id.name,
                        company=request.company_id.name,
                    )
                )
