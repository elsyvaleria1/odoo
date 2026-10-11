import logging

from odoo import SUPERUSER_ID, api
from odoo.exceptions import MissingError, ValidationError
from odoo.http import Controller, request, route

from odoo.addons.hr_expense_stripe.utils import (
    STRIPE_REQUEST_REFUSED_REASONS,
    StripeIssuingDatabaseError,
    format_amount_from_stripe,
)

_logger = logging.getLogger(__name__)


class StripeIssuingController(Controller):
    _webhook_url = "stripe_issuing/webhook"

    @route(
        f"/{_webhook_url}/<string:company_uuid>",
        type="http",
        methods=["POST"],
        auth="receiver",
        receiver="res.company:_receiver_for_stripe_issuing",
        receiver_event="stripe_issuing",
        receiver_refusal="res.company:_refuse_stripe_issuing",
        csrf=False,
        save_session=False,
        typed=True,
    )
    def stripe_issuing_webhook(self, company_uuid: str):
        admission = request.admission
        event = admission.json()
        admission.retag(event.get("type") or "stripe_issuing")
        _logger.info(
            'Webhook "%(type)s" event (%(event_id)s) received to "%(url)s" from %(ip)s',
            {
                "type": event.get("type"),
                "event_id": event.get("id"),
                "url": f"{self._webhook_url}/{company_uuid}",
                "ip": admission.remote_addr,
            },
        )
        response_headers = {
            "Stripe-Version": event.get("api_version"),
            "Content-Type": "application/json",
        }
        company_sudo = admission.subject
        env = request.env(
            user=SUPERUSER_ID,
            su=True,
            context={"allowed_company_ids": company_sudo.ids},
        )

        event_mode = "live" if event["livemode"] else "test"
        if company_sudo._get_stripe_mode() != event_mode:
            response = {
                "message": "Event ignored as the event mode does not match the company mode"
            }
            return request.prepare_json_response(
                data=response, headers=response_headers
            )

        status = 200
        try:
            match event["type"].split("."):
                case ("balance", "available"):
                    response = self._process_balance_event(env, event)
                case ("issuing_authorization", _multiples):
                    response = self._process_authorization_event(env, event)
                case ("issuing_card", "updated"):
                    response = self._process_card_event(env, event)
                case ("issuing_dispute", _multiples):
                    response = self._process_dispute_event(env, event)
                case ("issuing_transaction", _multiples):
                    response = self._process_transaction_event(env, event)
                case ("topup", "succeeded"):
                    response = self._process_topup_event(env, event)
                case _:
                    response = {
                        "approved": False,
                        "message": f"Invalid event type '{event['type']}'",
                    }
        except Exception as e:
            response = {
                "approved": False,
                "message": str(e),
            }
            _logger.exception("Stripe Issuing webhook event failed")
            status = (
                StripeIssuingDatabaseError.DB_ERROR
                if event["type"] != "issuing_authorization.request"
                else 200
            )
        return request.prepare_json_response(
            data=response, headers=response_headers, status=status
        )


    @api.model
    def _process_authorization_event(self, env, event):
        auth_object = event["data"]["object"]
        card = env["hr.expense.stripe.card"].search(
            [
                ("stripe_id", "=", auth_object["card"]["id"]),
                ("company_id", "=", env.company.id),
            ],
            limit=1,
        )
        if not card:
            raise MissingError(
                env._("A card that doesn't exist on the database was used")
            )
        if event["type"] == "issuing_authorization.request":
            amount = format_amount_from_stripe(
                auth_object["pending_request"]["amount"], card.currency_id
            )
            mcc = env["product.mcc.stripe.tag"].search(
                [
                    ("code", "=", auth_object["merchant_data"]["category_code"]),
                ]
            )
            country = env["res.country"].search(
                [("code", "ilike", auth_object["merchant_data"]["country"])], limit=1
            )

            can_pay, refusal_reason = card._get_payment_authorization(
                amount, mcc, country
            )
            if can_pay:
                return {"message": "Authorization request approved", "approved": True}
            else:
                env["hr.expense"]._create_from_stripe_authorization(
                    auth_object, refusal_reason
                )
                return {"message": refusal_reason, "approved": False}

        if event["type"] in {
            "issuing_authorization.created",
            "issuing_authorization.updated",
        }:
            default_request_history = [
                {"approved": False, "reason": request.env._("Unknown")}
            ]
            request_history = auth_object.setdefault(
                "request_history", default_request_history
            )[0]
            if auth_object["status"] == "closed" and not request_history["approved"]:
                technical_reason = request_history["reason"]
                if technical_reason == "webhook_declined":
                    refusal_reason = auth_object["metadata"].get(
                        "message",
                        STRIPE_REQUEST_REFUSED_REASONS[request_history["reason"]],
                    )
                else:
                    refusal_reason = STRIPE_REQUEST_REFUSED_REASONS[
                        request_history["reason"]
                    ]
                env["hr.expense"]._create_from_stripe_authorization(
                    auth_object, refusal_reason
                )
                return {"message": "Refused expense created"}

            elif auth_object["status"] == "pending":
                env["hr.expense"]._create_from_stripe_authorization(auth_object)
                return {"message": "Draft expense created"}

            return {"message": "Event ignored, not a refused or draft expense"}
        raise ValidationError(
            env._("Invalid event type '%(invalid_event)s'", invalid_event=event["type"])
        )

    @api.model
    def _process_balance_event(self, env, event):
        bal_object = event["data"]["object"]
        issuing_object = bal_object["issuing"]
        company = env.company
        journal = company.stripe_journal_id
        last_balance_timestamp = journal.stripe_issuing_balance_timestamp
        if last_balance_timestamp > event["created"]:
            return {
                "message": "Balance ignored, a more recent one was already received"
            }
        stripe_currency = journal.stripe_currency_id
        if issuing_object["available"]:
            issuing_amount = format_amount_from_stripe(
                issuing_object["available"][0]["amount"], stripe_currency
            )
        else:
            issuing_amount = 0

        company.stripe_journal_id.write(
            {
                "stripe_issuing_balance": issuing_amount,
                "stripe_issuing_balance_timestamp": event["created"],
            }
        )

        return {"message": "Balance updated"}

    @api.model
    def _process_card_event(self, env, event):
        card_object = event["data"]["object"]
        existing_card = env["hr.expense.stripe.card"].search(
            [
                ("stripe_id", "=", card_object["id"]),
                ("company_id", "=", env.company.id),
            ],
            limit=1,
        )
        if not existing_card:
            raise ValidationError(
                env._("A card that doesn't exist on the database was used")
            )

        if (
            card_object["shipping"]
            and card_object["shipping"].get("status")
            in {"canceled", "failure", "returned"}
            and event["data"]["previous_attributes"].get("shipping", {}).get("status")
        ):
            existing_card.with_context(
                skip_local_update=existing_card.state == "canceled"
            )._create_or_update_card(state="canceled")
        else:
            existing_card._update_from_stripe(card_object)

        return {"message": "Card updated"}

    @api.model
    def _process_transaction_event(self, env, event):
        tr_object = event["data"]["object"]
        authorization_id = tr_object["authorization"]
        transaction_id = tr_object["id"]

        split_id = False
        if transaction_id and not authorization_id:
            existing_expenses = env["hr.expense"].search(
                [
                    ("stripe_transaction_id", "=", transaction_id),
                    ("company_id", "=", env.company.id),
                ]
            )

        elif authorization_id:
            existing_expenses = env["hr.expense"].search(
                [
                    ("stripe_authorization_id", "=", authorization_id),
                    ("company_id", "=", env.company.id),
                ]
            )
            expense_transaction_ids = set(
                existing_expenses.mapped("stripe_transaction_id")
            ) - {False}
            if (
                expense_transaction_ids
                and transaction_id not in expense_transaction_ids
            ):
                if len(existing_expenses) == 1:
                    split_id = (
                        existing_expenses.split_expense_origin_id or existing_expenses
                    ).id
                else:
                    split_id = next(
                        s_id
                        for s_id in (
                            *existing_expenses.mapped("split_expense_origin_id").ids,
                            min(existing_expenses.ids),
                        )
                        if s_id
                    )
                existing_expenses.split_expense_origin_id = split_id
                existing_expenses = env[
                    "hr.expense"
                ]
            elif expense_transaction_ids:
                existing_expenses = existing_expenses.filtered(
                    lambda exp: exp.stripe_transaction_id == transaction_id
                )

        if tr_object["type"] == "capture" and not existing_expenses:
            env["hr.expense"]._create_from_stripe_transaction(
                tr_object, split_id=split_id
            )
        elif tr_object["type"] == "capture" and existing_expenses:
            existing_expenses._update_from_stripe_transaction(tr_object)
        elif tr_object["type"] == "refund" and existing_expenses:
            existing_expenses._stripe_cancel_expense_or_reverse_move(tr_object)
        if event["type"] == "issuing_transaction.created":
            existing_statement_line = env["account.bank.statement.line"].search(
                [
                    ("stripe_id", "=", transaction_id),
                    ("company_id", "=", env.company.id),
                ]
            )
            if existing_statement_line:
                existing_statement_line._update_from_stripe_transaction(tr_object)
            else:
                env["account.bank.statement.line"]._create_from_stripe_transaction(
                    tr_object
                )
        elif event["type"] == "issuing_transaction.updated":
            statement_line = env["account.bank.statement.line"].search(
                [
                    ("stripe_id", "=", transaction_id),
                    ("company_id", "=", env.company.id),
                ]
            )
            statement_line._update_from_stripe_transaction(tr_object)
        return {"message": "Expense & Bank Statement Line Created/Updated"}

    @api.model
    def _process_dispute_event(self, env, event):
        return {"message": "Not Implemented"}

    @api.model
    def _process_topup_event(self, env, event):
        tu_object = event["data"]["object"]
        statement_line = env["account.bank.statement.line"].search(
            [("stripe_id", "=", tu_object["id"]), ("company_id", "=", env.company.id)]
        )
        if statement_line:
            return {
                "message": "Top-up Bank Statement Line already exists, ignoring the event"
            }
        env["account.bank.statement.line"]._create_from_stripe_topup(tu_object)
        return {"message": "Top-up Bank Statement Line Create/updated"}
