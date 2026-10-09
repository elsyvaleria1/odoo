from typing import Any

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_datetime, formatLang

from odoo.addons.approval.models.mixin_approval import APPROVAL_TRIGGER_RULE

MAX_DETAIL_LINES = 200


def _depends_on_approval_settings(model) -> list:
    if model._abstract:
        return []
    prefix = model._get_approval_field_prefix()
    return [
        *(
            f"company_id.{prefix}_{name}"
            for name in (
                "validation_level",
                "validation_amount",
                "rate_limit_enabled",
                "rate_limit_hours",
                "rate_limit_count",
                "rate_limit_amount",
            )
        ),
        "partner_id",
        f"partner_id.{prefix}_approval_required",
        "line_ids.product_id",
        "line_ids.product_id.categ_id",
        f"line_ids.product_id.categ_id.{prefix}_approval_required",
        f"line_ids.product_id.{prefix}_approval_required",
        "amount_total",
        "approval_request_id",
        "approval_request_id.target_model",
        "approval_request_id.state",
    ]


class MixinApprovalDocument(models.AbstractModel):
    _name = "mixin.approval.document"
    _inherit = "mixin.approval.lifecycle"
    _description = "Approval Mixin for Order-Like Documents"
    _approval_requester_field = "user_id"

    def _check_before_approval(self, verb: str) -> None:
        # an order is asked for approval before its confirmation checks run, as
        # its own action_confirm always asked; they run when it is confirmed
        if verb != "confirm":
            super()._check_before_approval(verb)

    def _get_approval_field_prefix(self) -> str:
        raise NotImplementedError

    def _get_approval_document_label(self) -> str:
        raise NotImplementedError

    def _get_approval_partner_label(self) -> str:
        raise NotImplementedError

    def _get_approval_category_type(self) -> str:
        raise NotImplementedError

    def _get_approval_manager_group(self) -> str:
        raise NotImplementedError

    def _get_approval_subtype(self, state: str) -> str:
        raise NotImplementedError

    def _get_approval_config_menu(self) -> str:
        raise NotImplementedError

    def _get_approval_rate_limit_fallback(self) -> float:
        company = self.env["res.company"]
        field = company._fields[
            f"{self._get_approval_field_prefix()}_rate_limit_amount"
        ]
        return field.default(company)

    def _get_approval_deadline_date(self):
        return self.date_commitment

    def _get_approval_reference(self) -> str:
        return self.origin

    def _get_approval_setting(self, record, suffix):
        return record[f"{self._get_approval_field_prefix()}_{suffix}"]

    def _is_approval_forced_by_partner(self) -> bool:
        return bool(
            self._get_approval_setting(self.partner_id.sudo(), "approval_required")
        )

    def _is_approval_forced_by_product(self) -> bool:
        return any(
            line.product_id
            and self._get_approval_setting(line.product_id.sudo(), "approval_required")
            for line in self.line_ids
        )

    def _is_approval_forced_by_product_category(self) -> bool:
        categories = self.line_ids.product_id.categ_id
        if not categories:
            return False
        # The flag marks a branch, not a single node: a product filed under
        # "Controlled / Solvents" is controlled because "Controlled" says so.
        # approval.category._is_matching_product_category already reads the
        # tree that way (`child_of`), and reading it any other way here meant
        # a flag set on a parent protected nothing underneath it.
        branch = (
            self.env["product.category"]
            .sudo()
            .search([("id", "parent_of", categories.ids)])
        )
        return any(
            self._get_approval_setting(category, "approval_required")
            for category in branch
        )

    @api.depends(_depends_on_approval_settings)
    def _compute_approval_required(self) -> None:
        super()._compute_approval_required()

    def _get_approval_trigger(self) -> str | bool:
        return APPROVAL_TRIGGER_RULE if self._is_approval_required_by_rule() else False

    def _is_approval_required_by_rule(self) -> bool:
        self.check_singleton()
        if self.env.context.get("install_module"):
            return False
        request = self.approval_request_id
        if (
            request
            and request.target_model == self._name
            and request.state == "approved"
        ):
            return False

        if self._is_approval_forced_by_partner():
            return True
        if self._is_approval_forced_by_product():
            return True
        if self._is_approval_forced_by_product_category():
            return True

        validation_level = self._get_approval_setting(
            self.company_id, "validation_level"
        )
        if validation_level == "none":
            return False
        if validation_level == "module_approval":
            return True
        if validation_level != "manager_amount":
            return False

        threshold_amount = self.company_id.currency_id._convert(
            self._get_approval_setting(self.company_id, "validation_amount"),
            self.currency_id,
            self.company_id,
            self.date_order or fields.Date.today(),
        )
        if self.amount_total >= threshold_amount:
            return True

        policed_user = self.create_uid or self.env.user
        if not policed_user.sudo()._has_group(self._get_approval_manager_group()):
            return True
        return self._check_rate_limit_exceeded()

    def action_create_approval_request(self) -> dict[str, Any]:
        if (
            self.approval_request_id
            and self.approval_request_id.target_model == self._name
        ):
            raise UserError(
                self.env._(
                    "This %(document)s was created from an approval request "
                    "(%(request)s). It does not need a separate approval.",
                    document=self._get_approval_document_label().lower(),
                    request=self.approval_request_id.name,
                ),
            )
        return super().action_create_approval_request()

    def _get_fields_approval_required(self) -> list[str]:
        return ["partner_id", "line_ids"]

    def _get_fields_approval_protected(self) -> list[str]:
        return ["line_ids", "partner_id", "currency_id"]

    def _get_domain_approval_category(self) -> list[tuple[str, str, Any]]:
        self.check_singleton()
        return [
            ("company_id", "in", (self.company_id.id, False)),
            ("active", "=", True),
            ("approval_type", "=", self._get_approval_category_type()),
            ("target_model", "=", False),
        ]

    def _raise_approval_category_not_configured(self) -> None:
        raise UserError(
            self.env._(
                "No approval category configured for %(documents)s.\n\n"
                "Please configure an approval category with:\n"
                "• Approval Type = '%(type)s'\n"
                "• Target Model = empty (for mixin flow)\n"
                "• Company = '%(company)s' or global\n\n"
                "Go to %(menu)s to configure.",
                documents=f"{self._get_approval_document_label().lower()}s",
                type=self._get_approval_category_type().capitalize(),
                company=self.company_id.name,
                menu=self._get_approval_config_menu(),
            ),
        )

    def _get_approval_category_mismatch_report(self, categories) -> str:
        self.check_singleton()
        checks = (
            (self.env._("amount"), "_is_matching_amount"),
            (self.env._("partner"), "_is_matching_partner"),
            (self.env._("product category"), "_is_matching_product_category"),
            (self.env._("product"), "_is_matching_product"),
            (self.env._("credit/debit policy"), "_is_matching_credit_policy"),
        )
        lines = []
        for category in categories:
            failed = [
                label for label, method in checks if not getattr(category, method)(self)
            ]
            if not failed:
                continue
            lines.append(
                self.env._(
                    "• %(category)s — failed on: %(criteria)s",
                    category=category.name,
                    criteria=", ".join(failed),
                ),
            )
        return "\n".join(lines)

    def _raise_approval_category_not_matched(self, categories) -> None:
        report = self._get_approval_category_mismatch_report(categories)
        raise UserError(
            self.env._(
                "No approval category matches this %(document)s.\n\n"
                "Order: %(order)s\n"
                "%(partner_label)s: %(partner)s\n"
                "Amount: %(amount)s\n\n"
                "%(report)s\n\n"
                "Note: a criterion still constrains matching even when the "
                "category's trigger hides it on the form.",
                document=self._get_approval_document_label().lower(),
                order=self.name,
                partner_label=self._get_approval_partner_label(),
                partner=self.partner_id.name,
                amount=self._format_approval_amount(self.amount_total),
                report=report,
            ),
        )

    def _get_approval_reason_header(self) -> list[str]:
        self.check_singleton()
        label = escape(self._get_approval_document_label())
        partner_label = escape(self._get_approval_partner_label())
        amount = escape(self._format_approval_amount(self.amount_total))
        deadline = self._get_approval_deadline_date()
        delivery = escape(
            format_datetime(self.env, deadline)
            if deadline
            else self.env._("Not specified"),
        )
        total_label = escape(self.env._("Total Amount"))
        delivery_label = escape(self.env._("Expected Delivery"))
        return [
            f"<h4>{label}: {escape(self.name)}</h4>",
            (
                f"<p><strong>{partner_label}:</strong> "
                f"{escape(self.partner_id.name)}</p>"
            ),
            f"<p><strong>{total_label}:</strong> {amount}</p>",
            f"<p><strong>{delivery_label}:</strong> {delivery}</p>",
        ]

    def _get_approval_reason_html(self):
        self.check_singleton()
        reason_parts = self._get_approval_reason_header()

        product_lines = self.line_ids.filtered(
            lambda line: not line.display_type and line.product_id,
        )
        if product_lines:
            products_label = escape(self.env._("Products"))
            quantity_label = escape(self.env._("Qty"))
            reason_parts.append(f"<p><strong>{products_label}:</strong></p><ul>")
            reason_parts.extend(
                f"<li>{escape(line.product_id.name)} - "
                f"{quantity_label}: {escape(formatLang(self.env, line.product_qty))} "
                f"{escape(line.product_uom_id.name)} - "
                f"{escape(self._format_approval_amount(line.price_subtotal))}</li>"
                for line in product_lines[:MAX_DETAIL_LINES]
            )
            reason_parts.append("</ul>")
            omitted = len(product_lines) - MAX_DETAIL_LINES
            if omitted > 0:
                omitted_note = escape(
                    self.env._("… and %(count)s more lines", count=omitted),
                )
                reason_parts.append(f"<p><em>{omitted_note}</em></p>")

        reason_parts.extend(self._get_approval_notes_html())
        return "".join(reason_parts)

    def _get_approval_notes_html(self) -> list[str]:
        notes: list[tuple[str, str]] = []
        seen: set[tuple[str, int]] = set()
        records = [self.partner_id]
        for line in self.line_ids:
            records += [line.product_id, line.product_id.categ_id]
        for record in records:
            if not record:
                continue
            record = record.sudo()
            key = (record._name, record.id)
            if key in seen:
                continue
            seen.add(key)
            if note := self._get_approval_setting(record, "approval_notes"):
                notes.append((record.display_name, note))
        if not notes:
            return []
        notes_label = escape(self.env._("Notes for approvers"))
        return [
            f"<p><strong>{notes_label}:</strong></p>",
            *(
                f"<p><strong>{escape(source)}:</strong> {escape(note)}</p>"
                for source, note in notes
            ),
        ]

    def _format_approval_amount(self, amount, currency=None) -> str:
        return formatLang(
            self.env,
            amount,
            currency_obj=currency or self.currency_id,
        )

    def _approval_approved_message_values(self) -> dict:
        label = self._get_approval_document_label()
        title = self.env._("%(document)s Approved", document=label)

        return {
            "body": Markup("<p>✅ <strong>%s</strong></p><p>%s: %s</p><p>%s: %s</p>")
            % (
                title,
                self.env._("Approved by"),
                escape(self._approval_decider_names("approved")),
                self.env._("Approved amount"),
                escape(self._format_approval_amount(self.amount_total)),
            ),
            "subject": title,
            "message_type": "notification",
            "subtype_xmlid": self._get_approval_subtype("approved"),
        }

    def _is_operation_run_on_approval(self, operation: str) -> bool:
        return bool(
            self._get_approval_setting(self.company_id, "auto_confirm_on_approval")
        ) and super()._is_operation_run_on_approval(operation)

    def _on_approval_refused(self) -> None:
        self.check_singleton()
        refused_approver = self.approval_request_id.approver_ids.filtered(
            lambda approver: approver.state == "refused",
        )

        if not (refused_approver and refused_approver[0].user_id):
            self.message_post(
                body=self.env._("Approval request refused. Order can be modified."),
                message_type="notification",
            )
            return

        title = self.env._(
            "%(document)s Rejected",
            document=self._get_approval_document_label(),
        )
        self.message_post(
            body=Markup("<p>❌ <strong>%s</strong></p><p>%s: %s</p>")
            % (
                title,
                self.env._("Rejected by"),
                escape(refused_approver[0].user_id.name),
            ),
            subject=title,
            message_type="notification",
            subtype_xmlid=self._get_approval_subtype("refused"),
        )

    def _prepare_approval_request_values(self, category: Any) -> dict[str, Any]:
        values = super()._prepare_approval_request_values(category)
        values.update(
            {
                "date_deadline": self._get_approval_deadline_date(),
                "reference": self._get_approval_reference() or self.origin,
            },
        )
        return values

    def _is_locked_by_approval(self) -> bool:
        self.check_singleton()
        return bool(self.approval_request_id and self.approval_state == "approved")

    def _check_approval_covers(self, operation: str) -> None:
        super()._check_approval_covers(operation)
        self._check_approved_amount()

    def _check_approved_amount(self) -> None:
        self.check_singleton()
        if not self.approval_request_id:
            return

        approved_amount = self.approval_request_id.amount
        approved_currency = self.approval_request_id.currency_id
        comparable_amount = approved_amount
        if approved_currency and approved_currency != self.currency_id:
            comparable_amount = approved_currency._convert(
                approved_amount,
                self.currency_id,
                self.company_id,
                self.date_order or fields.Date.context_today(self),
            )

        if self.currency_id.compare_amounts(self.amount_total, comparable_amount) == 0:
            return

        raise UserError(
            self.env._(
                "%(document)s amount has changed since approval was granted.\n\n"
                "Approved amount: %(approved)s\n"
                "Current amount: %(current)s\n\n"
                "Please refuse the current approval and request a new one "
                "with the updated amount.",
                document=self._get_approval_document_label(),
                approved=self._format_approval_amount(
                    approved_amount,
                    currency=approved_currency or self.currency_id,
                ),
                current=self._format_approval_amount(self.amount_total),
            ),
        )

    def _approval_rate_limit_rate_date(self):
        self.check_singleton()
        return self.date_order or fields.Date.context_today(self)

    def _check_rate_limit_exceeded(self) -> bool:
        self.check_singleton()
        company = self.company_id

        if not self._get_approval_setting(company, "rate_limit_enabled"):
            return False

        return self._approval_rate_limit_exceeded(
            hours=self._get_approval_setting(company, "rate_limit_hours") or 24,
            max_count=self._get_approval_setting(company, "rate_limit_count") or 5,
            max_amount=self._get_approval_setting(company, "rate_limit_amount")
            or self._get_approval_rate_limit_fallback(),
            under_threshold_amount=self._get_approval_setting(
                company,
                "validation_amount",
            ),
        )
