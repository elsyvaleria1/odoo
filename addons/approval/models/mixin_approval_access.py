from typing import TYPE_CHECKING, Any, Literal

from odoo import models
from odoo.exceptions import UserError

from . import approval_trace as trace
from .mixin_approval_subjects import LIVE_REQUEST_STATES

if TYPE_CHECKING:
    from .approval_category import ApprovalCategory
    from .approval_request import ApprovalRequest
    from odoo.addons.base.models.res_partner import ResPartner

ACCESS_SUBJECT_PREFIX = "access"


class MixinApprovalAccess(models.AbstractModel):
    _name = "mixin.approval.access"
    _inherit = ["mixin.approval.subjects"]
    _description = "Record Whose Access Is Asked For Through Approval"

    _access_approval_category = ""

    def _get_access_subject_key(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> str:
        if role:
            return f"{ACCESS_SUBJECT_PREFIX}:{partner.id}:{role}"
        return f"{ACCESS_SUBJECT_PREFIX}:{partner.id}"

    def _get_access_subject(
        self, subject_key: str | Literal[False]
    ) -> tuple[ResPartner, str | Literal[False]]:
        prefix, _separator, rest = (subject_key or "").partition(":")
        partner_id, _separator, role = rest.partition(":")
        if prefix != ACCESS_SUBJECT_PREFIX or not partner_id.isdecimal():
            return self.env["res.partner"], False
        partner = self.env["res.partner"].browse(int(partner_id)).exists()
        return partner, role or False

    def _get_approval_subject_category(
        self, subject_key: str
    ) -> ApprovalCategory | None:
        if not self._access_approval_category:
            return self.env["approval.category"]
        return self.env.ref(self._access_approval_category, raise_if_not_found=False)

    def _get_access_request_name(
        self, partner: ResPartner, role: str | Literal[False]
    ) -> str:
        return self.env._(
            "Access to %(record)s for %(partner)s",
            record=self.display_name,
            partner=partner.name,
        )

    def _prepare_approval_subject_request_values(
        self, subject_key: str, category: ApprovalCategory
    ) -> dict[str, Any]:
        vals = super()._prepare_approval_subject_request_values(subject_key, category)
        partner, role = self._get_access_subject(subject_key)
        if partner:
            vals["name"] = self._get_access_request_name(partner, role)
        return vals

    def _on_approval_subject_state_changed(
        self, request: ApprovalRequest, new_state: str
    ) -> None:
        super()._on_approval_subject_state_changed(request, new_state)
        if new_state != "approved":
            return
        partner, role = self._get_access_subject(request.subject_key)
        if not partner:
            return
        held = self._has_access(partner, role)
        trace.SUBJECTS.note(
            "access_granted",
            record=self,
            request=request.id,
            partner=partner.id,
            role=role,
            already_held=held,
        )
        if not held:
            self._grant_access(partner, role)
        self._end_access_requests_now_held(partner, request)

    def _end_access_requests_now_held(
        self, partner: ResPartner, granted: ApprovalRequest
    ) -> None:
        self.check_singleton()
        key = self._get_access_subject_key(partner)
        waiting = self._search_subject_approval_requests(
            [
                ("state", "in", LIVE_REQUEST_STATES),
                ("id", "!=", granted.id),
                "|",
                ("subject_key", "=", key),
                ("subject_key", "=like", f"{key}:%"),
            ]
        )
        for request in waiting:
            _partner, role = self._get_access_subject(request.subject_key)
            if not self._has_access(partner, role):
                continue
            request._force_terminal(
                "cancelled",
                body=self.env._(
                    "%(partner)s already holds this access to %(record)s.",
                    partner=partner.name,
                    record=self.display_name,
                ),
            )

    def _has_access(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> bool:
        raise NotImplementedError

    def _grant_access(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> None:
        raise NotImplementedError

    def _get_live_access_request(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> ApprovalRequest:
        self.check_singleton()
        return self.sudo()._get_live_approval_request(
            self._get_access_subject_key(partner, role)
        )

    def _request_access(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> ApprovalRequest:
        self.check_singleton()
        if self._has_access(partner, role):
            trace.REFUSAL.event(
                "access_already_held",
                record=self,
                partner=partner.id,
                role=role,
            )
            raise UserError(
                self.env._(
                    "%(partner)s already has this access to %(record)s.",
                    partner=partner.name,
                    record=self.display_name,
                )
            )
        return self._raise_approval_request(self._get_access_subject_key(partner, role))

    def _decide_access_request(
        self, partner: ResPartner, role: str | Literal[False], approve: bool
    ) -> bool:
        self.check_singleton()
        request = self._get_live_access_request(partner, role)
        if not request:
            return False
        rows = request._get_rows_decidable_by(self.env.user)
        trace.SUBJECTS.event(
            "access_decided",
            record=self,
            request=request.id,
            approve=approve,
            as_approver=bool(rows),
            uid=self.env.uid,
        )
        if rows:
            if approve:
                request.action_approve(approver=rows)
            else:
                request.action_refuse(approver=rows)
            return True
        self.check_access("write")
        if approve:
            request._approve_without_decision(
                self.env._(
                    "%(user)s granted %(partner)s access to %(record)s.",
                    user=self.env.user.name,
                    partner=partner.name,
                    record=self.display_name,
                )
            )
        else:
            request._force_terminal(
                "refused",
                self.env._(
                    "%(user)s refused %(partner)s access to %(record)s.",
                    user=self.env.user.name,
                    partner=partner.name,
                    record=self.display_name,
                ),
            )
        return True
