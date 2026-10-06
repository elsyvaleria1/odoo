from markupsafe import escape

from odoo import http
from odoo.http import request

from odoo.addons.portal.utils import get_url_with_params

RECEIPT_REPORT = "account.action_report_payment_receipt"
PROBLEM_MAX_LENGTH = 2000


class CollectionReceipt(http.Controller):
    @http.route(
        "/collection/receipt/<int:payment_id>",
        type="http",
        auth="link",
        link="account.payment:payment_id",
        methods=["GET"],
        sitemap=False,
        website=True,
    )
    def collection_receipt(self, payment_id, reported=None, **kwargs):
        payment = request.link_subject
        return request.render(
            "account_collection.collection_receipt_page",
            {
                "payment": payment,
                "invoices": payment.reconciled_invoice_ids,
                "access_token": kwargs.get("access_token"),
                "reported": bool(reported),
            },
        )

    @http.route(
        "/collection/receipt/<int:payment_id>/pdf",
        type="http",
        auth="link",
        link="account.payment:payment_id",
        methods=["GET"],
        sitemap=False,
        website=True,
    )
    def collection_receipt_pdf(self, payment_id, **kwargs):
        payment = request.link_subject
        pdf, _format = payment.env["ir.actions.report"]._render_qweb_pdf(
            RECEIPT_REPORT, payment.ids
        )
        filename = f"{payment.name.replace('/', '-')}.pdf"
        return request.prepare_response(
            pdf,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", f'inline; filename="{filename}"'),
            ],
        )

    @http.route(
        "/collection/receipt/<int:payment_id>/report",
        type="http",
        auth="link",
        link="account.payment:payment_id",
        link_role="comment",
        methods=["POST"],
        sitemap=False,
        website=True,
    )
    def collection_receipt_report(self, payment_id, description="", **kwargs):
        payment = request.link_subject
        description = (description or "").strip()[:PROBLEM_MAX_LENGTH]
        if description:
            payment._report_collection_receipt_problem(escape(description))
        return request.redirect(
            get_url_with_params(
                f"/collection/receipt/{payment.id}",
                {"access_token": kwargs.get("access_token", ""), "reported": 1},
            )
        )
