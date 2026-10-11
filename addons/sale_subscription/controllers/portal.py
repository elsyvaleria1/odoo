import datetime
from collections import OrderedDict
from math import ceil
from urllib.parse import quote as url_quote
from urllib.parse import urlencode as url_encode

import werkzeug
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, Command, fields, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_date, str2bool
from odoo.tools.misc import get_lang

from odoo.addons.payment import utils as payment_utils
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.sale.controllers import portal as payment_portal
from odoo.addons.sale.controllers import portal as sale_portal
from odoo.addons.sale_subscription.models.sale_order import (
    SUBSCRIPTION_CLOSED_STATE,
    SUBSCRIPTION_PROGRESS_STATE,
)

_debug = DebugLog(__name__)


class CustomerPortal(payment_portal.PaymentPortal):
    def _get_domain_subscription(self, partner):
        return [
            ("partner_id", "child_of", partner.commercial_partner_id.id),
            ("subscription_state", "in", ["3_progress", "4_paused", "6_churn"]),
            ("is_subscription", "=", True),
        ]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "subscription_count" in counters:
            if request.env["sale.order"].has_access("read"):
                partner = request.env.user.partner_id
                values["subscription_count"] = request.env["sale.order"].search_count(
                    self._get_domain_subscription(partner)
                )
            else:
                values["subscription_count"] = 0
        return values

    def _get_subscription(self, access_token, order_id):
        logged_in = not request.env.user.sudo()._is_public()
        order_sudo = request.env["sale.order"]
        try:
            order_sudo = request.env["access.link"]._open_record(
                "sale.order", order_id, access_token
            )
        except AccessError:
            if not logged_in:
                subscription_url = "/my/subscriptions/%d" % order_id
                return order_sudo, werkzeug.utils.redirect(
                    "/web/login?redirect=%s" % url_quote(subscription_url)
                )
            else:
                _debug.logic("subscription_portal_denied", order=order_id)
                raise werkzeug.exceptions.NotFound from None
        except MissingError:
            return order_sudo, request.redirect("/my")
        return order_sudo, None

    def _get_invoice_sudo(self, access_token, invoice_id):
        try:
            invoice_sudo = request.env["access.link"]._open_record(
                "account.move", invoice_id, access_token
            )
        except AccessError:
            _debug.logic("invoice_portal_denied", reason="bad_token")
            raise ValidationError(request.env._("Invalid access token.")) from None
        except MissingError:
            _debug.logic("invoice_portal_denied", reason="not_found")
            raise ValidationError(request.env._("Invoice not found.")) from None
        return invoice_sudo

    @http.route(
        ["/my/subscriptions", "/my/subscriptions/page/<int:page>", "/my/subscription"],
        type="http",
        auth="user",
        website=True,
    )
    def my_subscription(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        order_id=None,
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        Order = request.env["sale.order"]

        if order_id:
            order_sudo, redirection = self._get_subscription(None, int(order_id))
            if redirection:
                return redirection
            origin_order = order_sudo.origin_order_id or order_sudo
            domain = [
                ("state", "not in", ["cancel", "draft"]),
                "|",
                ("id", "=", origin_order.id),
                ("origin_order_id", "=", origin_order.id),
            ]
        else:
            domain = self._get_domain_subscription(partner)

        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]

        searchbar_sortings = {
            "date": {
                "label": request.env._("Newest"),
                "order": "create_date desc, id desc",
            },
            "name": {"label": request.env._("Name"), "order": "name asc, id asc"},
            "subscription_state": {
                "label": request.env._("Status"),
                "order": "subscription_state asc, id desc",
            },
        }
        searchbar_filters = {
            "all": {"label": request.env._("All"), "domain": []},
            "open": {
                "label": request.env._("In Progress"),
                "domain": [("subscription_state", "in", ["3_progress", "4_paused"])],
            },
            "to_renew": {
                "label": request.env._("To Renew"),
                "domain": [
                    ("subscription_state", "=", "3_progress"),
                    ("next_invoice_date", "<", fields.Date.today()),
                ],
            },
            "close": {
                "label": request.env._("Closed"),
                "domain": [("subscription_state", "=", "6_churn")],
            },
        }

        sortby = self._resolve_searchbar_option(
            searchbar_sortings, sortby, "subscription_state"
        )
        order = searchbar_sortings[sortby]["order"]
        filterby = self._resolve_searchbar_option(searchbar_filters, filterby, "all")
        domain += searchbar_filters[filterby]["domain"]

        order_count = Order.search_count(domain)
        pager = portal_pager(
            url="/my/subscriptions",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
            },
            total=order_count,
            page=page,
            step=self._items_per_page,
        )
        orders = Order.search(
            domain, order=order, limit=self._items_per_page, offset=pager["offset"]
        )
        request.session["my_subscriptions_history"] = orders.ids[:100]
        request.session["current_history"] = "my_subscriptions_history"

        values.update(
            {
                "subscriptions": orders
                if not order_id
                else orders.with_context(force_sale_url=True),
                "page_name": "subscription",
                "pager": pager,
                "default_url": "/my/subscriptions",
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
                "searchbar_filters": OrderedDict(sorted(searchbar_filters.items())),
                "filterby": filterby,
            }
        )
        return request.render("sale_subscription.portal_my_subscriptions", values)

    @http.route()
    def portal_my_quotes(self, **kwargs):
        request.session["current_history"] = "my_quotations_history"
        return super().portal_my_quotes(**kwargs)

    @http.route()
    def portal_my_orders(self, **kwargs):
        request.session["current_history"] = "my_orders_history"
        return super().portal_my_orders(**kwargs)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>",
            "/my/subscriptions/<int:order_id>/<access_token>",
            "/my/subscription/<int:order_id>",
            "/my/subscription/<int:order_id>/<access_token>",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def subscription(
        self,
        order_id,
        access_token=None,
        message="",
        report_type=None,
        download=False,
        payment_amount=None,
        **kw,
    ):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        if report_type in ("html", "pdf", "text"):
            return self._show_report(
                model=order_sudo,
                report_type=report_type,
                report_ref="sale.action_report_saleorder",
                download=download,
            )

        payment_amount = self._cast_as_float(payment_amount)
        enable_token_management = request.env.user.partner_id in (
            order_sudo.partner_id.child_ids | order_sudo.partner_id
        )
        closable = order_sudo.user_closable and order_sudo.subscription_state in [
            "3_progress",
            "4_paused",
        ]
        display_close = closable and (
            not order_sudo.end_date
            or order_sudo.end_date > order_sudo.next_invoice_date
        )
        periods = {"day": "days", "week": "weeks", "month": "months", "year": "years"}
        missing_periods = 1
        if order_sudo.next_invoice_date:
            rel_period = relativedelta(
                datetime.datetime.today(), order_sudo.next_invoice_date
            )
            missing_periods = (
                ceil(
                    getattr(rel_period, periods[order_sudo.plan_id.repeat_unit])
                    / order_sudo.plan_id.repeat_interval
                )
                + 1
            )
        action = request.env.ref("sale_subscription.sale_subscription_action")
        token_management_url_params = {
            "manage_subscription": True,
            "sale_order_id": order_id,
            "access_token": access_token,
        }
        progress_child = order_sudo.subscription_child_ids.filtered(
            lambda s: s.subscription_state in SUBSCRIPTION_PROGRESS_STATE
        )
        display_payment_message = False
        if (
            order_sudo.subscription_state in ["3_progress", "4_paused"]
            and not progress_child
        ):
            display_payment_message = True
        elif (
            order_sudo.subscription_state in SUBSCRIPTION_CLOSED_STATE
            and not progress_child
        ):
            active_products = all(
                prod.active for prod in order_sudo.line_ids.product_template_id
            )
            display_payment_message = order_sudo.plan_id.active and active_products

        backend_url = (
            f"/odoo/action-{order_sudo._get_portal_return_action().id}/{order_sudo.id}"
        )

        portal_page_values = {
            "page_name": "subscription",
            "sale_order": order_sudo,
            "report_type": "html",
            "display_close": display_close,
            "closable": closable,
            "close_reasons": request.env["sale.order.close.reason"].search([]),
            "missing_periods": missing_periods,
            "user": request.env.user,
            "is_salesman": request.env.user.has_group("sale.group_sale_salesman"),
            "action": action,
            "message": message,
            "pricelist": order_sudo.pricelist_id.sudo(),
            "enable_token_management": enable_token_management,
            "token_management_url": f"/my/payment_method?{url_encode(token_management_url_params)}",
            "payment_action_id": request.env.ref("payment.action_payment_provider").id,
            "display_payment_message": display_payment_message,
            "backend_url": backend_url,
            "product_documents": order_sudo._get_product_documents(),
            "next_billing_details": order_sudo._next_billing_details(),
            "format_date": lambda date: format_date(request.env, date),
            "next_invoice_date_at_resume": max(
                order_sudo.user_pause_start, fields.Date.today()
            )
            if order_sudo.user_pause_start
            else False,
            "is_subscription_postpaid": order_sudo._is_subscription_postpaid(),
            "is_delivery_product": int(
                any(
                    line.product_id.invoice_policy == "transferred"
                    for line in order_sudo.line_ids
                )
            ),
            **self._prepare_partner_addresses(order_sudo),
        }

        history_session_key = request.session.get(
            "current_history", "my_subscriptions_history"
        )
        portal_page_values = self._get_page_view_values(
            order_sudo, access_token, portal_page_values, history_session_key, False
        )

        payment_form_values = {
            "default_token_id": order_sudo.payment_token_id.id,
            "sale_order_id": order_sudo.id,
        }

        payment_context = {
            "partner_id": order_sudo.partner_id.id,
        }
        rendering_context = {
            **SalePortal._prepare_payment_form_context(
                self,
                order_sudo,
                is_subscription=True,
                subscription_anticipate=True,
                payment_amount=payment_amount,
            ),
            **portal_page_values,
            **payment_form_values,
            **payment_context,
        }
        return request.render(
            "sale_subscription.subscription_portal_template", rendering_context
        )

    def _prepare_partner_addresses(self, order_sudo):
        addresses_data = self._prepare_address_data(order_sudo.partner_id)
        check_user_id = order_sudo.user_id or request.env.user
        return {
            "multiple_addresses_enabled": check_user_id.has_group(
                "account.group_delivery_invoice_address"
            ),
            "invoicing_addresses": [
                {
                    "id": partner.id,
                    "address": f"{partner.name}, {partner._display_address(without_company=True)}",
                }
                for partner in addresses_data.get("billing_addresses")
            ],
            "delivery_addresses": [
                {
                    "id": partner.id,
                    "address": f"{partner.name}, {partner._display_address(without_company=True)}",
                }
                for partner in addresses_data.get("delivery_addresses")
                if order_sudo.partner_shipping_id.id == partner.id
            ],
        }

    @http.route(
        [
            "/my/orders/<int:order_id>/document/<int:document_id>",
            "/my/subscriptions/<int:order_id>/document/<int:document_id>",
        ]
    )
    def portal_my_order_document(self, *args, **kwargs):
        return super().portal_my_order_document(*args, **kwargs)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/close",
            "/my/subscription/<int:order_id>/close",
        ],
        type="http",
        methods=["POST"],
        auth="public",
        website=True,
    )
    def close_account(self, order_id, access_token=None, **kw):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        if order_sudo.plan_id.user_closable:
            close_reason = request.env["sale.order.close.reason"].browse(
                int(kw.get("close_reason_id"))
            )
            if close_reason:
                if kw.get("closing_text"):
                    order_sudo.message_post(
                        body=request.env._("Closing text: %s", kw.get("closing_text"))
                    )
                _debug.lifecycle(
                    "subscription_closed_by_customer",
                    order=order_sudo,
                    reason=close_reason,
                )
                order_sudo.with_context(allow_future_end_date=True).set_close(
                    close_reason_id=close_reason.id
                )
        return request.redirect(
            f"/my/subscriptions/{order_id}?access_token={access_token}"
        )

    @http.route(
        ["/my/subscriptions/<int:order_id>/change_plan"],
        type="http",
        methods=["POST"],
        auth="public",
        website=True,
    )
    def change_plan(self, order_id, access_token=None, **kw):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        posted = kw.get("plan_id")
        new_plan = order_sudo._portal_plan_choices().filtered(
            lambda plan: str(plan.id) == str(posted)
        )
        if new_plan:
            _debug.lifecycle(
                "subscription_plan_changed", order=order_sudo, plan=new_plan
            )
            order_sudo.plan_id = new_plan
        elif posted is not None:
            _debug.logic(
                "plan_change_refused",
                order=order_sudo,
                reason="plan_not_offered",
                posted=posted,
            )
        return request.redirect(order_sudo.get_portal_url())

    @http.route(
        ["/my/subscriptions/<int:order_id>/pause"],
        type="http",
        methods=["POST"],
        auth="public",
        website=True,
    )
    def subscription_pause(self, order_id, access_token=None, **kw):
        order_sudo, redirection = self._get_subscription(access_token, order_id)

        if redirection:
            return redirection
        if order_sudo.next_invoice_date <= fields.Date.today():
            _debug.logic("pause_refused", order=order_sudo, reason="not_yet_due")
            raise UserError(
                self.env._("You cannot pause a subscription that is not yet due.")
            )
        if order_sudo._is_subscription_postpaid():
            _debug.logic("pause_refused", order=order_sudo, reason="postpaid_lines")
            raise UserError(
                self.env._("You cannot pause a subscription with postpaid lines.")
            )

        until = kw.get("until")
        if not until:
            _debug.logic("pause_refused", order=order_sudo, reason="no_date")
            raise ValidationError(
                self.env._("Please select a date to pause the subscription until.")
            )

        if (
            order_sudo.plan_id.pausable_by_user
            and until
            and not order_sudo.user_pause_start
        ):
            user_lang = get_lang(request.env).date_format
            until = fields.Date.to_date(
                datetime.datetime.strptime(until, user_lang).date()
            )

            user_pause_start = order_sudo.next_invoice_date

            if until == order_sudo.next_invoice_date:
                _debug.logic("pause_refused", order=order_sudo, reason="zero_days")
                raise UserError(
                    self.env._("You cannot pause the subscription for 0 days.")
                )
            if until < order_sudo.next_invoice_date:
                _debug.logic(
                    "pause_refused", order=order_sudo, reason="before_due_date"
                )
                raise UserError(
                    self.env._("A pause can't take place before the next invoice date.")
                )
            if until > user_pause_start + order_sudo.plan_id.billing_period:
                _debug.logic(
                    "pause_refused", order=order_sudo, reason="over_one_period"
                )
                raise UserError(self.env._("Pause duration cannot exceed 1 period."))

            message_body = self.env._(
                "Subscription will be paused from %(date_from)s to %(date_to)s.",
                date_from=format_date(request.env, user_pause_start),
                date_to=format_date(request.env, until),
            )

            user = (
                request.env["res.users"]
                .sudo()
                .search([("partner_id", "=", order_sudo.partner_id.id)], limit=1)
                or SUPERUSER_ID
            )
            order_sudo.with_user(user).sudo().with_context(
                subscription_pause=True
            ).write(
                {
                    "next_invoice_date": until,
                    "user_pause_start": user_pause_start,
                }
            )
            _debug.lifecycle("subscription_paused", order=order_sudo)
            order_sudo.with_user(user).sudo().message_post(body=message_body)

        return request.redirect(order_sudo.get_portal_url())

    @http.route(
        ["/my/subscriptions/<int:order_id>/resume"],
        type="http",
        methods=["POST"],
        auth="public",
        website=True,
    )
    def subscription_resume(self, order_id, access_token=None, **kw):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        if order_sudo.next_invoice_date <= fields.Date.today():
            _debug.logic("resume_refused", order=order_sudo, reason="not_yet_due")
            raise UserError(
                self.env._("You cannot resume a subscription that is not yet due.")
            )

        if order_sudo.plan_id.pausable_by_user and order_sudo.user_pause_start:
            user = (
                request.env["res.users"]
                .sudo()
                .search([("partner_id", "=", order_sudo.partner_id.id)], limit=1)
                or SUPERUSER_ID
            )
            invoice_date = max(order_sudo.user_pause_start, fields.Date.today())
            message_body = self.env._(
                "Subscription was resumed on the %s.",
                format_date(request.env, invoice_date),
            )
            order_sudo.with_user(user).sudo().with_context(
                subscription_pause=True
            ).write({"next_invoice_date": invoice_date, "user_pause_start": False})
            order_sudo.with_user(user).sudo().message_post(body=message_body)
        return request.redirect(order_sudo.get_portal_url())

    @http.route(["/my/subscriptions/<int:order_id>/upsell"], type="http", auth="public")
    def subscription_portal_upsell(self, order_id, access_token=None, **kw):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        if order_sudo.user_quantity:
            upsell = order_sudo._create_renew_upsell_order(
                "7_upsell", request.env._("An upsell has been created by the client.")
            )
            upsell.action_quotation_sent()
            return request.redirect(upsell.get_portal_url())
        return None

    @http.route(
        ["/my/subscriptions/<int:order_id>/renewal"], type="http", auth="public"
    )
    def subscription_portal_renewal(
        self, order_id, access_token=None, change_plan=False, **kw
    ):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        qs = ""
        if change_plan:
            qs = "&change_plan=true"
        if order_sudo.user_extend:
            renewal = order_sudo._create_renew_upsell_order(
                "2_renewal", request.env._("A renewal has been created by the client.")
            )
            renewal.action_quotation_sent()
            return request.redirect(renewal.get_portal_url(query_string=qs))
        return None

    @http.route(
        ["/my/subscriptions/<int:order_id>/change_address"],
        type="http",
        methods=["POST"],
        auth="public",
        website=True,
    )
    def subscription_change_address(self, order_id, access_token=None, **kw):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            return redirection
        check_user_id = order_sudo.user_id or request.env.user
        multiple_addresses_enabled = check_user_id.has_group(
            "account.group_delivery_invoice_address"
        )
        if not multiple_addresses_enabled:
            raise request.prepare_not_found_error()
        addresses_data = self._prepare_address_data(order_sudo.partner_id)
        invoicing_id = int(kw.get("invoicing_address", 0))
        invoicing_partner = request.env["res.partner"].browse(invoicing_id)
        if invoicing_partner in addresses_data["billing_addresses"]:
            order_sudo.partner_invoice_id = invoicing_partner
        return request.redirect(
            order_sudo.get_portal_url(
                query_string="&%s" % url_encode({"address_updated": "true"})
            )
        )


class PaymentPortal(payment_portal.PaymentPortal):
    def _prepare_extra_payment_form_context(
        self,
        manage_subscription=False,
        sale_order_id=None,
        subscription_invoice_id=None,
        access_token=None,
        **kwargs,
    ):
        extra_payment_form_values = super()._prepare_extra_payment_form_context(
            manage_subscription=manage_subscription,
            sale_order_id=sale_order_id,
            subscription_invoice_id=subscription_invoice_id,
            access_token=access_token,
            **kwargs,
        )
        if sale_order_id:
            sale_order_id = self._cast_as_int(sale_order_id)
            extra_payment_form_values.update(
                {
                    "sale_order_id": sale_order_id,
                }
            )
            try:
                order_sudo = request.env["access.link"]._open_record(
                    "sale.order", sale_order_id, access_token
                )
            except (
                AccessError
            ):
                if not payment_utils.is_access_token_valid(
                    access_token,
                    kwargs.get("partner_id"),
                    kwargs.get("amount"),
                    kwargs.get("currency_id"),
                ):
                    raise
                order_sudo = request.env["sale.order"].sudo().browse(sale_order_id)
            if order_sudo.subscription_state == "5_renewed":
                extra_payment_form_values["amount"] = 0
            if manage_subscription:
                extra_payment_form_values.update(
                    {
                        "subscription": order_sudo,
                        "allow_token_selection": True,
                        "allow_token_deletion": False,
                        "default_token_id": order_sudo.payment_token_id.id,
                        "transaction_route": order_sudo.get_portal_url(
                            suffix="/transaction"
                        ),
                        "assign_token_route": f"/my/subscriptions/assign_token/{sale_order_id}",
                        "landing_route": order_sudo.get_portal_url(),
                    }
                )
        if subscription_invoice_id:
            invoice_id = self._cast_as_int(subscription_invoice_id)
            access_token = kwargs.get("invoice_access_token")
            try:
                invoice_sudo = request.env["access.link"]._open_record(
                    "account.move", invoice_id, access_token
                )
            except (
                AccessError
            ):
                if not payment_utils.is_access_token_valid(
                    access_token,
                    kwargs.get("partner_id"),
                    kwargs.get("amount"),
                    kwargs.get("currency_id"),
                ):
                    raise
            invoice_sudo = request.env["account.move"].sudo().browse(invoice_id)

            if invoice_sudo.invoice_line_ids.subscription_id:
                transaction_route = (
                    f"/my/subscriptions/invoice/{invoice_id}/transaction"
                )
                extra_payment_form_values.update(
                    {
                        "transaction_route_subscription": transaction_route,
                        "access_token": invoice_sudo.access_token,
                        "is_subscription": True,
                    }
                )
        return extra_payment_form_values

    def _create_transaction(self, *args, **kwargs):
        tx_sudo = super()._create_transaction(*args, **kwargs)
        if tx_sudo.operation != "validation" and tx_sudo.state not in [
            "done",
            "cancel",
            "error",
        ]:
            subscriptions = tx_sudo.sale_order_ids.filtered("is_subscription")
            subscriptions.pending_transaction = True
        return tx_sudo

    @http.route(
        "/my/subscriptions/<int:order_id>/transaction", type="jsonrpc", auth="public"
    )
    def subscription_transaction(
        self, order_id, access_token, is_validation=False, **kwargs
    ):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        if redirection:
            raise werkzeug.exceptions.NotFound
        logged_in = not request.env.user._is_public()
        partner_sudo = (
            request.env.user.partner_id if logged_in else order_sudo.partner_id
        )
        subscription_anticipate = str2bool(kwargs.pop("subscription_anticipate", False))
        self._check_transaction_kwargs(kwargs)
        kwargs.update(partner_id=partner_sudo.id)
        if not is_validation:
            invoice_to_pay = None
            amount = kwargs.get("amount") or 0
            if not subscription_anticipate:
                for invoice in order_sudo.invoice_ids:
                    if (
                        invoice.state == "posted"
                        and invoice.move_type == "out_invoice"
                        and invoice.payment_state
                        not in ["paid", "in_payment", "reversed"]
                    ):
                        invoice_to_pay = invoice
                        break
                    if (
                        not invoice_to_pay
                        and invoice.state == "draft"
                        and invoice.move_type == "out_invoice"
                    ):
                        invoice_to_pay = invoice

                amount_to_invoice = (
                    invoice_to_pay.amount_total
                    if invoice_to_pay
                    else order_sudo.amount_taxinc_to_invoice
                )
                amount = amount or amount_to_invoice
            recurring_amount = sum(
                order_sudo.line_ids.filtered(lambda l: l.recurring_invoice).mapped(
                    "price_total"
                )
            )
            is_zero = order_sudo.currency_id.is_zero(amount or recurring_amount)
            tokenize = (
                not is_zero
                and amount
                and recurring_amount
                and order_sudo.currency_id.compare_amounts(amount, recurring_amount)
                >= 0
            )
            kwargs.update(
                {
                    "amount": amount,
                    "currency_id": order_sudo.currency_id.id,
                    "tokenization_requested": tokenize,
                }
            )
            tx_sudo = self._create_transaction(
                custom_create_values={
                    "sale_order_ids": [Command.set([order_id])],
                    "invoice_ids": [Command.set([invoice_to_pay[:1].id])]
                    if invoice_to_pay
                    else [],
                    "subscription_action": "assign_token" if tokenize else None,
                },
                is_validation=is_validation,
                **kwargs,
            )
        else:
            kwargs.update(
                {
                    "amount": None,
                    "currency_id": None,
                    "reference_prefix": payment_utils.singularize_reference_prefix(
                        prefix="V"
                    ),
                }
            )
            tx_sudo = self._create_transaction(
                custom_create_values={
                    "sale_order_ids": [Command.set([order_id])],
                    "subscription_action": "assign_token",
                },
                is_validation=is_validation,
                **kwargs,
            )

        return tx_sudo._prepare_processing_values()

    @http.route(
        "/my/subscriptions/invoice/<int:invoice_id>/transaction",
        type="jsonrpc",
        auth="public",
    )
    def subscription_transaction_from_invoice(
        self, invoice_id, access_token, is_validation=False, **kwargs
    ):
        if is_validation:
            return {}

        invoice_sudo = self._get_invoice_sudo(access_token, invoice_id)

        self._check_transaction_kwargs(kwargs)
        logged_in = not request.env.user._is_public()
        partner_sudo = (
            request.env.user.partner_id if logged_in else invoice_sudo.partner_id
        )
        amount = kwargs.get("amount", 0) or invoice_sudo.amount_total
        kwargs.update(
            {
                "partner_id": partner_sudo.id,
                "amount": amount,
                "currency_id": invoice_sudo.currency_id.id,
            }
        )

        subscriptions_sudo = invoice_sudo.invoice_line_ids.subscription_id
        tokenize = kwargs.get("tokenization_requested") or kwargs.get("flow") == "token"
        tx_sudo = self._create_transaction(
            custom_create_values={
                "sale_order_ids": [Command.set(subscriptions_sudo.ids)],
                "invoice_ids": [Command.set(invoice_sudo.ids)],
                "subscription_action": "assign_token"
                if tokenize
                else "manual_send_mail",
            },
            is_validation=False,
            **kwargs,
        )
        return tx_sudo._prepare_processing_values()

    @http.route(
        "/my/subscriptions/assign_token/<int:order_id>", type="jsonrpc", auth="user"
    )
    def subscription_assign_token(self, order_id, token_id, access_token=None):
        order_sudo, redirection = self._get_subscription(access_token, order_id)
        partner_id = request.env.user.partner_id

        if redirection:
            return redirection

        token_sudo = (
            request.env["payment.token"]
            .sudo()
            .search(
                [
                    ("id", "=", token_id),
                    ("partner_id", "child_of", partner_id.commercial_partner_id.id),
                    ("active", "=", True),
                ]
            )
        )

        if not token_sudo:
            raise werkzeug.exceptions.NotFound

        max_amount = token_sudo.provider_id.maximum_amount
        if (
            max_amount > 0
            and order_sudo.currency_id.compare_amounts(
                order_sudo.amount_total, max_amount
            )
            == 1
        ):
            raise UserError(
                request.env._(
                    "The payment method you selected can only pay amounts up to %s. Please create or select another one.",
                    token_sudo.provider_id.main_currency_id.format(max_amount),
                )
            )

        order_sudo.payment_token_id = token_sudo
        return None

    @http.route()
    def payment_method(self, sale_order_id=None, **kwargs):
        return super().payment_method(
            sale_order_id=self._cast_as_int(sale_order_id), **kwargs
        )

    def _invoice_get_page_view_values(self, invoice, access_token, /, **kwargs):
        subscription_id = invoice.line_ids.subscription_id
        if invoice and subscription_id:
            kwargs.update(
                {
                    "subscription_invoice_id": invoice.id,
                    "invoice_access_token": access_token,
                    **kwargs,
                }
            )
        return super()._invoice_get_page_view_values(invoice, access_token, **kwargs)


class SalePortal(sale_portal.CustomerPortal):
    def _prepare_payment_form_context(
        self, order_sudo, is_subscription=False, subscription_anticipate=False, **kwargs
    ):
        is_subscription = (
            is_subscription
            or order_sudo.is_subscription
            or order_sudo.subscription_id.is_subscription
        )
        return {
            **super()._prepare_payment_form_context(
                order_sudo,
                is_subscription=is_subscription,
                subscription_anticipate=subscription_anticipate,
                **kwargs,
            ),
            "is_subscription": is_subscription,
        }
