from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _is_immediate_payment(self) -> bool:
        self.check_singleton()
        invoice_date = self.invoice_date or fields.Date.today()
        return all(
            line.date_maturity <= invoice_date
            for line in self.line_ids
            if line.display_type == "payment_term" and line.date_maturity
        )

    def _credit_term_days(self):
        self.check_singleton()
        invoice_date = self.invoice_date or fields.Date.today()
        due_dates = [
            line.date_maturity
            for line in self.line_ids
            if line.display_type == "payment_term" and line.date_maturity
        ]
        return max(((due - invoice_date).days for due in due_dates), default=0)

    def _credit_profile(self):
        self.check_singleton()
        return (
            self.env["credit.profile"]
            .sudo()
            .with_company(self.company_id)
            ._for_partner(self.partner_id, company=self.company_id)
            .with_context(credit_exclude_move_ids=tuple(self._origin.ids))
        )

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

    def _post_check_business_rules(self):
        for move in self.filtered(lambda m: m.is_sale_document()):
            if move.env.context.get("install_module"):
                continue
            profile = move._credit_profile()
            if not profile:
                continue
            if move.move_type == "out_refund":
                if profile.hold_active:
                    profile._check_credit("invoice", immediate=True)
                continue
            profile._check_credit(
                "invoice",
                amount=abs(move.amount_total_signed),
                immediate=move._is_immediate_payment(),
                term_days=move._credit_term_days(),
            )
        return super()._post_check_business_rules()
