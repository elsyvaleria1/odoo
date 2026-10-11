import psycopg

from odoo import http
from odoo.http import request
from odoo.tools.translate import LazyTranslate

from odoo.addons.payment.logging import get_payment_logger

_lt = LazyTranslate(__name__)
_logger = get_payment_logger(__name__)


class PostProcessingRetryError(Exception):
    pass


class PaymentPostProcessing(http.Controller):

    MONITORED_TX_ID_KEY = "__payment_monitored_tx_id__"

    @http.route(
        "/payment/status",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        list_as_website_content=_lt("Payment Status"),
    )
    def display_status(self, **kwargs):
        monitored_tx = self._get_monitored_transaction()
        values = {"tx": monitored_tx} if monitored_tx else {"payment_not_found": True}
        return request.render("payment.payment_status", values)

    @http.route("/payment/status/poll", type="jsonrpc", auth="public")
    def poll_status(self, **_kwargs):
        monitored_tx = self._get_monitored_transaction()

        if not monitored_tx.is_post_processed:
            try:
                monitored_tx._post_process()
            except (
                psycopg.OperationalError,
                psycopg.IntegrityError,
            ):
                request.env.cr.rollback()
                raise PostProcessingRetryError("retry") from None
            except Exception:
                request.env.cr.rollback()
                _logger.exception(
                    "Encountered an error while post-processing transaction with id %s",
                    monitored_tx.id,
                )
                raise

        return {
            "provider_code": monitored_tx.provider_code,
            "state": monitored_tx.state,
            "landing_route": monitored_tx.landing_route,
        }

    @classmethod
    def monitor_transaction(cls, transaction):
        request.session[cls.MONITORED_TX_ID_KEY] = transaction.id

    def _get_monitored_transaction(self):
        return (
            request.env["payment.transaction"]
            .sudo()
            .browse(request.session.get(self.MONITORED_TX_ID_KEY))
            .exists()
        )
