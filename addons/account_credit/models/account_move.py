from collections import defaultdict

from odoo import models

from .sale_order import APPROVAL_ROUTE_CONDITIONS


class AccountMove(models.Model):
    _inherit = "account.move"

    def _credit_profile(self):
        self.check_singleton()
        return (
            self._credit_profiles_of(self.company_id)
            ._for_partner(self.partner_id, company=self.company_id)
            .with_context(credit_exclude_move_ids=tuple(self._origin.ids))
        )

    def _credit_profiles_of(self, company):
        return self.env["credit.profile"].sudo().with_company(company)

    def _prepare_credit_warning_message(self, record, current_amount=0.0):
        record = record.with_privilege(
            "account_credit.privilege_read_credit_limit",
            reason="whoever works on a document is warned of its partner's "
            "credit limit",
        )
        return super()._prepare_credit_warning_message(
            record, current_amount=current_amount
        )

    def _get_partner_credit_exposure(self) -> tuple[float, float]:
        self.check_singleton()
        profile = self._credit_profile()
        if not profile:
            return super()._get_partner_credit_exposure()
        profile._invalidate_exposure()
        return (
            profile.exposure_open + profile.exposure_draft,
            profile.exposure_uninvoiced,
        )

    def _check_posting_advisories(self) -> None:
        if self.env.context.get("install_module"):
            return super()._check_posting_advisories()
        for company, moves in (
            self.filtered(lambda m: m.is_sale_document()).grouped("company_id").items()
        ):
            moves._check_credit_on_posting(company)
        return super()._check_posting_advisories()

    def _check_credit_on_posting(self, company) -> None:
        Profile = self._credit_profiles_of(company)
        profile_by_partner = Profile._for_partners(self.partner_id, company)
        if not profile_by_partner:
            return
        profiles = (
            Profile.browse({profile.id for profile in profile_by_partner.values()})
            .with_context(credit_exclude_move_ids=tuple(self._origin.ids))
            ._invalidate_exposure()
        )
        profile_by_id = {profile.id: profile for profile in profiles}
        drafts = defaultdict(float)
        for move in self:
            if move._counts_as_draft_exposure():
                drafts[move.partner_id.commercial_partner_id.id] += (
                    move.amount_total_signed
                )
        extra_exposure = self.env.context.get("credit_extra_exposure", 0.0)
        for move in self:
            partner_id = move.partner_id.commercial_partner_id.id
            profile = profile_by_partner.get(partner_id)
            if not profile:
                continue
            others = drafts[partner_id] - (
                move.amount_total_signed if move._counts_as_draft_exposure() else 0.0
            )
            profile = profile_by_id[profile.id].with_context(
                credit_extra_exposure=extra_exposure + others
            )
            if move.move_type == "out_refund":
                if profile.hold_active:
                    profile._check_credit("invoice", immediate=True, refresh=False)
                continue
            term_days = move._credit_days()
            profile._check_credit(
                "invoice",
                amount=abs(move.amount_total_signed),
                immediate=not term_days,
                term_days=term_days,
                approval_exempt=move._credit_approved_conditions(),
                refresh=False,
            )

    def _credit_approved_conditions(self) -> tuple:
        self.check_singleton()
        orders = self.with_privilege(
            "account_credit.privilege_credit_invoice",
            reason="an invoice weighs the approval of the orders it invoices",
        ).invoice_line_ids.sale_line_ids.order_id
        if orders and all(order.approval_state == "approved" for order in orders):
            return tuple(APPROVAL_ROUTE_CONDITIONS)
        return ()

    def _counts_as_draft_exposure(self) -> bool:
        return self.state == "draft" and self.move_type in ("out_invoice", "out_refund")
