from werkzeug.exceptions import NotFound

from odoo.exceptions import ValidationError
from odoo.http import Controller, request, route

from odoo.addons.account_iban.models.res_partner_bank_account import check_iban
from odoo.addons.base.models.res_partner_bank_account import sanitize_account_number
from odoo.addons.payment import utils as payment_utils


class SepaDirectDebitController(Controller):
    @route("/payment/sepa_direct_debit/set_mandate", type="jsonrpc", auth="public")
    def sdd_set_mandate(self, reference, iban, access_token):
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            ._search_by_reference("custom", {"reference": reference})
        )
        if not tx_sudo:
            return

        if not payment_utils.is_access_token_valid(access_token, tx_sudo.reference):
            raise NotFound

        iban = self._normalize_sdd_iban(iban)

        tx_sudo.mandate_id = tx_sudo.provider_id._sdd_find_or_create_mandate(
            tx_sudo.partner_id.id, iban
        )

        tx_sudo._set_pending()

    def _normalize_sdd_iban(self, iban) -> str:
        iban = sanitize_account_number(iban)
        check_iban(iban)
        if not iban:
            raise ValidationError(request.env._("Missing or invalid IBAN."))
        return iban
