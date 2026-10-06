import logging
from typing import Any

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict
from odoo.tools.misc import format_datetime, formatLang

from odoo.addons.approval.models.mixin_approval import APPROVAL_TRIGGER_CATEGORY

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "mixin.approval.gate"]

    _max_detail_lines = 5
    _approval_requester_field = "user_id"
    _access_anchors = frozendict(
        {
            "owner": "approval_pending_user_ids",
        }
    )

    @api.depends(
        "company_id",
        "picking_type_id",
        "location_id",
        "location_id.stock_approval_required",
        "location_dest_id",
        "location_dest_id.stock_approval_required",
        "move_ids.product_id.categ_id",
        "move_ids.product_id.categ_id.stock_approval_required",
        "approval_request_id",
        "approval_request_id.target_model",
        "approval_request_id.state",
    )
    def _compute_approval_required(self) -> None:
        self.move_ids.product_id.mapped("categ_id")
        super()._compute_approval_required()

    def _get_approval_trigger(self) -> str | bool:
        self.check_singleton()
        request = self.approval_request_id
        if (
            request
            and request.target_model == "stock.picking"
            and request.state == "approved"
        ):
            return False
        return APPROVAL_TRIGGER_CATEGORY

    def _approval_trigger_fired(self) -> bool:
        self.check_singleton()
        if self.location_id.stock_approval_required:
            return True
        if self.location_dest_id.stock_approval_required:
            return True
        return bool(
            self.move_ids.mapped("product_id.categ_id").filtered(
                lambda c: c.stock_approval_required,
            ),
        )

    def _get_fields_approval_required(self) -> list[str]:
        return [
            "picking_type_id",
            "location_id",
            "location_dest_id",
            "move_ids",
        ]

    def _get_fields_approval_protected(self) -> list[str]:
        return [
            "move_ids",
            "location_id",
            "location_dest_id",
            "picking_type_id",
            "partner_id",
        ]

    def _get_domain_approval_category(self) -> list[tuple[str, str, Any]]:
        return [
            ("approval_type", "=", "stock"),
            ("target_model", "=", False),
        ]

    def _get_approval_category_fallback(self, categories):
        self.check_singleton()
        if not self._approval_trigger_fired():
            return self.env["approval.category"].browse()

        catch_all = categories.filtered(
            lambda c: (
                not (c.picking_type_ids or c.location_ids or c.stock_product_categ_ids)
                and c.step_ids
            ),
        )[:1]
        if not catch_all:
            _logger.warning(
                "%s: a stock approval trigger fired (source %r, destination %r) "
                "but no catch-all approval category can serve it, so the "
                "transfer proceeds without approval. Create a stock category "
                "with no location/operation/product criteria and enough "
                "approvers to reach its own minimum.",
                self.name,
                self.location_id.complete_name,
                self.location_dest_id.complete_name,
            )
        return catch_all

    def _prepare_approval_request_values(self, category: Any) -> dict[str, Any]:
        vals = super()._prepare_approval_request_values(category)
        vals.update(
            {
                "partner_id": self.partner_id.id if self.partner_id else False,
                "date": self.date_planned or fields.Date.today(),
                "reference": self.origin or self.name,
            },
        )
        return vals

    def _get_approval_reason_html(self) -> str:
        self.check_singleton()
        scheduled = (
            format_datetime(self.env, self.date_planned)
            if self.date_planned
            # Same wording the document mixin already translates for an absent
            # deadline, so the two blocks read alike once both are catalogued.
            else self.env._("Not specified")
        )
        transfer_label = escape(self.env._("Stock Transfer"))
        operation_label = escape(self.env._("Operation"))
        from_label = escape(self.env._("From"))
        to_label = escape(self.env._("To"))
        scheduled_label = escape(self.env._("Scheduled Date"))
        reason_parts = [
            f"<h4>{transfer_label}: {escape(self.name)}</h4>",
            (
                f"<p><strong>{operation_label}:</strong> "
                f"{escape(self.picking_type_id.name)}</p>"
            ),
            (
                f"<p><strong>{from_label}:</strong> "
                f"{escape(self.location_id.complete_name)}</p>"
            ),
            (
                f"<p><strong>{to_label}:</strong> "
                f"{escape(self.location_dest_id.complete_name)}</p>"
            ),
            f"<p><strong>{scheduled_label}:</strong> {escape(scheduled)}</p>",
        ]

        if self.partner_id:
            partner_label = escape(self.env._("Partner"))
            reason_parts.append(
                f"<p><strong>{partner_label}:</strong> "
                f"{escape(self.partner_id.name)}</p>",
            )

        if len(self.move_ids) <= self._max_detail_lines:
            products_label = escape(self.env._("Products"))
            quantity_label = escape(self.env._("Qty"))
            reason_parts.append(f"<p><strong>{products_label}:</strong></p><ul>")
            reason_parts.extend(
                f"<li>{escape(move.product_id.name)} - "
                f"{quantity_label}: {escape(formatLang(self.env, move.product_uom_qty))} "
                f"{escape(move.product_uom_id.name)}</li>"
                for move in self.move_ids.filtered(lambda m: m.product_id)
            )
            reason_parts.append("</ul>")
        else:
            count_label = escape(self.env._("Number of Products"))
            reason_parts.append(
                f"<p><strong>{count_label}:</strong> {len(self.move_ids)}</p>",
            )

        return "".join(reason_parts)

    def _approval_approved_message_values(self) -> dict:
        approver_names = self._approval_decider_names("approved")

        return {
            "body": Markup("<p>✅ <strong>%s</strong></p><p>%s: %s</p><p>%s: %s</p>")
            % (
                self.env._("Stock Transfer Approved"),
                self.env._("Approved by"),
                escape(approver_names),
                self.env._("Operation"),
                escape(self.picking_type_id.name),
            ),
            "subject": self.env._("Stock Transfer Approved"),
            "message_type": "notification",
            "subtype_xmlid": "approval_stock.mt_stock_approved",
        }

    def _on_approval_refused(self) -> None:
        self.check_singleton()
        refused_approver = self.approval_request_id.approver_ids.filtered(
            lambda a: a.state == "refused",
        )

        if refused_approver and refused_approver[0].user_id:
            rejector_name = refused_approver[0].user_id.name
            self.message_post(
                body=Markup("<p>❌ <strong>%s</strong></p><p>%s: %s</p>")
                % (
                    self.env._("Stock Transfer Rejected"),
                    self.env._("Rejected by"),
                    escape(rejector_name),
                ),
                subject=self.env._("Stock Transfer Rejected"),
                message_type="notification",
                subtype_xmlid="approval_stock.mt_stock_refused",
            )
        else:
            self.message_post(
                body=self.env._("Approval request refused. Transfer can be modified."),
                message_type="notification",
            )

    def action_create_approval_request(self) -> dict[str, Any]:
        if (
            self.approval_request_id
            and self.approval_request_id.target_model == "stock.picking"
        ):
            raise UserError(
                self.env._(
                    "This stock transfer was created from an approval request (%s). "
                    "It does not need a separate approval.",
                    self.approval_request_id.name,
                ),
            )

        return super().action_create_approval_request()

    def action_cancel(self) -> bool:
        result = super().action_cancel()
        self.filtered(
            lambda picking: not picking.approval_request_id.target_model
        )._refuse_pending_approval()
        return result

    def _check_before_approval_gate(self) -> None:
        # Validation checks that must fail in the operator's face, not after
        # approval inside the sudo() side effect, where a UserError only
        # becomes a chatter note. Modules extend this hook and keep their
        # button_validate override for the path without approval. This module
        # sits first in the MRO, so the chain is continued explicitly:
        # otherwise the overrides declared by later modules never run.
        # A delivery that must travel in a departed trip is refused here too.
        self._check_dispatch_requirements()
        parent = getattr(super(), "_check_before_approval_gate", None)
        if parent:
            parent()  # pylint: disable=not-callable  (getattr default is None; the guard above settles it)

    def _check_before_approval(self, verb: str) -> None:
        super()._check_before_approval(verb)
        if verb == "validate":
            self._check_before_approval_gate()

    def _is_approval_reasked_after_refusal(self, operation: str) -> bool:
        return True

    def _get_approval_snapshot(self, operation: str) -> dict[str, Any]:
        self.check_singleton()
        return {
            "location_id": self.location_id.id,
            "location_dest_id": self.location_dest_id.id,
            "moves": sorted(
                [move.product_id.id, move.product_uom_qty] for move in self.move_ids
            ),
        }

    def _check_approval_covers(self, operation: str) -> None:
        super()._check_approval_covers(operation)
        approved = dict(self.approval_request_id.operation_snapshot or {})
        # Sum both sides per product: dict() over the snapshot pairs would keep
        # only one quantity per product, so a product spread over two
        # non-merging moves could move more than the grant, each move passing
        # against the largest pair alone.
        demanded: dict[int, float] = {}
        for product_id, quantity in approved.get("moves") or ():
            demanded[product_id] = demanded.get(product_id, 0.0) + quantity
        picked: dict[int, float] = {}
        for move in self.move_ids:
            picked[move.product_id.id] = (
                picked.get(move.product_id.id, 0.0) + move.quantity
            )
        for move in self.move_ids:
            allowed = demanded.get(move.product_id.id)
            if (
                allowed is None
                or move.product_uom_id.compare(picked[move.product_id.id], allowed) > 0
            ):
                raise UserError(
                    self.env._(
                        "%(product)s moves more than the %(allowed)s approved on "
                        "%(name)s. Ask for approval again.",
                        product=move.product_id.display_name,
                        allowed=allowed or 0.0,
                        name=self.display_name,
                    )
                )

    def _get_operation_failure_note(self, operation: str) -> str:
        return self.env._("⚠️ Could not auto-validate transfer: %(error)s")

    def _is_operation_run_on_approval(self, operation: str) -> bool:
        return bool(
            self.company_id.stock_auto_validate_on_approval
            and self.state in ("draft", "confirmed", "assigned")
        )

    def _get_approval_asked_headline(self, ready, need_approval, blocked=()) -> str:
        validated = len(ready.filtered(lambda picking: picking.state == "done"))
        if blocked:
            return self.env._(
                "%(sent)s stock transfer(s) sent for approval; %(validated)s "
                "validated; %(blocked)s could not be sent.",
                sent=len(need_approval),
                validated=validated,
                blocked=len(blocked),
            )
        return self.env._(
            "%(sent)s stock transfer(s) sent for approval; %(validated)s validated.",
            sent=len(need_approval),
            validated=validated,
        )
