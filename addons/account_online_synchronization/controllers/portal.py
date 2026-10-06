from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.tools import format_amount, format_date

from odoo.addons.portal.controllers.portal import CustomerPortal


class OnlineSynchronizationPortal(CustomerPortal):
    @http.route(
        ["/renew_consent/<int:journal_id>"],
        type="http",
        auth="link",
        link="account.journal:journal_id",
        link_refused="/my",
        website=True,
        sitemap=False,
    )
    def portal_online_sync_renew_consent(self, journal_id, access_token=None, **kw):
        # Display a page to the user allowing to renew the consent for his bank sync.
        # Requires the same rights as the button in odoo.
        journal_sudo = request.link_subject
        values = self._prepare_portal_layout_values()
        # Ignore the route if the journal isn't one using bank sync.
        if not journal_sudo.account_online_account_id:
            raise request.prepare_not_found_error()

        balance = journal_sudo.account_online_account_id.balance
        if journal_sudo.account_online_account_id.currency_id:
            formatted_balance = format_amount(
                request.env, balance, journal_sudo.account_online_account_id.currency_id
            )
        else:
            formatted_balance = format_amount(
                request.env,
                balance,
                journal_sudo.currency_id or journal_sudo.company_id.currency_id,
            )

        values.update(
            {
                "bank": journal_sudo.bank_account_id.bank_name
                or journal_sudo.account_online_account_id.name,
                "bank_account": journal_sudo.bank_account_id.acc_number,
                "journal": journal_sudo.name,
                "latest_balance_formatted": formatted_balance,
                "latest_balance": balance,
                "latest_sync": format_date(
                    request.env,
                    journal_sudo.account_online_account_id.last_sync,
                    date_format="MMM dd, YYYY",
                ),
                "iframe_params": json_dumps(journal_sudo.action_extend_consent()),
            }
        )
        return request.render(
            "account_online_synchronization.portal_renew_consent", values
        )

    @http.route(
        ["/renew_consent/<int:journal_id>/complete"],
        type="http",
        auth="link",
        link="account.journal:journal_id",
        link_role="comment",
        link_refused="/my",
        methods=["POST"],
        website=True,
    )
    def portal_online_sync_action_complete(self, journal_id, access_token=None, **kw):
        # Complete the consent renewal process
        journal_sudo = request.link_subject
        # Ignore the route if the journal isn't one using bank sync.
        if not journal_sudo.account_online_link_id:
            raise request.prepare_not_found_error()
        try:
            journal_sudo.account_online_link_id._update_connection_status()
            journal_sudo.manual_sync()
        except UserError:
            pass
        # The client reads this with post() from @web/core/network, which
        # refuses JSON typed as text/html.
        return request.prepare_response(
            json_dumps({"status": "done"}),
            headers=[("Content-Type", "application/json")],
        )
