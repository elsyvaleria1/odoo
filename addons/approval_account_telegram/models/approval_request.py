import logging
from typing import TYPE_CHECKING, Any

from markupsafe import Markup
from psycopg import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

if TYPE_CHECKING:
    from odoo.addons.account.models.account_bank_statement_line import (
        AccountBankStatementLine,
    )
    from odoo.addons.approval.models.approval_approver import ApprovalApprover
    from odoo.addons.approval.models.approval_category_step import (
        ApprovalCategoryStep,
    )

_logger = logging.getLogger(__name__)


_SETTLEMENT_DAYS = {"TC": 7, "TD": 7, "CHEQUE": 2}


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    @api.depends("has_bsl", "telegram_data")
    def _compute_bank_statement_settlement_days(self) -> None:
        super()._compute_bank_statement_settlement_days()
        for record in self:
            payment_method = (record.telegram_data or {}).get("payment_method", "")
            record.bank_statement_settlement_days = _SETTLEMENT_DAYS.get(
                payment_method,
                record.bank_statement_settlement_days,
            )

    def action_approve(
        self,
        approver: ApprovalApprover | None = None,
        steps: ApprovalCategoryStep | None = None,
    ) -> dict[str, Any] | None:
        result = super().action_approve(approver, steps)

        for request in self:
            if request.state != "approved":
                continue

            if request.category_id.has_automation == "no":
                continue

            if not request.automation_id:
                _logger.debug(
                    "Skipping automation for approval %s: no automation_id configured",
                    request.name,
                )
                continue

            if (
                request.category_id.has_bsl != "no"
                and not request.bank_statement_line_id
            ):
                _logger.warning(
                    "Cannot create automation for approval %s: bank_statement_line_id required but not set",
                    request.name,
                )
                continue

            if request._claimed_statement_line().is_reconciled:
                _logger.info(
                    "Skipping automation for approval %s: bank statement line "
                    "already reconciled (settled outside the approval flow)",
                    request.name,
                )
                request.message_post(
                    body=self.env._(
                        "Bank statement line already reconciled; automation "
                        "workflow skipped (payment settled outside the "
                        "approval flow).",
                    ),
                    message_type="notification",
                )
                continue

            try:
                with self.env.cr.savepoint():
                    request._create_automation_runtime()
            except (
                UserError,
                ValidationError,
                AccessError,
                ValueError,
                IntegrityError,
            ) as e:
                _logger.exception(
                    "Failed to create automation runtime for approval %s",
                    request.name,
                )
                request.message_post(
                    body=self.env._(
                        "Warning: Could not create automation workflow. Error: %s",
                        str(e),
                    ),
                    message_type="notification",
                )

        return result

    def _claimed_statement_line(self) -> AccountBankStatementLine:
        self.check_singleton()
        return self.bank_statement_line_id.with_privilege(
            "approval_account_telegram.privilege_start_approved_workflow",
            reason="an approved payment settles the statement line it claims",
        )

    def _create_automation_runtime(self) -> None:
        self.check_singleton()

        if self.automation_runtime_id:
            raise UserError(
                self.env._(
                    "An automation workflow already exists for this approval: %s",
                    self.automation_runtime_id.display_name,
                )
            )

        telegram_data = self.telegram_data or {}

        runtime_vals = {
            "automation_id": self.automation_id.id,
            "partner_id": self.partner_id.id,
            "reference": self.name,
            "amount": self.amount,
            "currency_id": (self.currency_id or self.company_id.currency_id).id,
            "date": (
                fields.Date.context_today(self, self.date)
                if self.date
                else fields.Date.context_today(self)
            ),
            "company_ids": [Command.set(self.company_id.ids)],
        }

        if st_line := self._claimed_statement_line():
            runtime_vals["st_line_id"] = st_line.id
            if self.partner_id and not st_line.partner_id:
                st_line.partner_id = self.partner_id

        customer_id = telegram_data.get("partner_cn_id")
        if customer_id:
            customer = self.env["res.partner"].browse(customer_id).exists()
            if customer:
                runtime_vals["partner_id"] = customer.id
                if customer != self.partner_id:
                    runtime_vals["third_party_id"] = self.partner_id.id
            else:
                _logger.warning(
                    "Approval %s names partner %s in its Telegram data, which "
                    "no longer exists; the workflow starts without it",
                    self.name,
                    customer_id,
                )

        runtime = (
            self.env["automation.runtime"]
            .with_privilege(
                "approval_account_telegram.privilege_start_approved_workflow",
                reason="an approved payment starts the workflow its category names",
            )
            .create(runtime_vals)
        )

        self.automation_runtime_id = runtime

        _logger.info(
            "Created automation runtime %s for approval %s",
            runtime.name,
            self.name,
        )

        runtime.action_start()

        self.message_post(
            body=Markup(self.env._("Automation workflow started: %(runtime)s"))
            % {"runtime": runtime._get_html_link(title=runtime.name)},
            message_type="notification",
        )
