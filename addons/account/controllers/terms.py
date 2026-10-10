from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


def sitemap_terms(env, rule, qs):
    if qs and qs.lower() not in "/terms":
        return
    use_invoice_terms = env.registry.settings.get_bool(env, "account.use_invoice_terms")
    if use_invoice_terms and env.company.account_config_id.terms_type == "html":
        yield {"loc": "/terms"}


class TermsController(http.Controller):
    @http.route(
        "/terms", type="http", auth="public", website=True, sitemap=sitemap_terms
    )
    def terms_conditions(self, **kwargs):
        _debug.pipeline("route", handler="TermsController.terms_conditions")
        use_invoice_terms = request.env.registry.settings.get_bool(
            request.env, "account.use_invoice_terms"
        )
        if not (
            use_invoice_terms
            and request.env.company.account_config_id.terms_type == "html"
        ):
            return request.env["ir.http"]._serve_error_page(
                request.env._("Oops"),
                request.env._(
                    """The requested page is invalid, or doesn't exist anymore."""
                ),
                status=404,
            )
        values = {
            "use_invoice_terms": use_invoice_terms,
            "company": request.env.company,
        }
        return request.render("account.account_terms_conditions_page", values)
