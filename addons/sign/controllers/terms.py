from odoo import http
from odoo.http import request


def sitemap_sign_terms(env, rule, qs):
    use_sign_terms = env.registry.settings.get_bool(env, "sign.use_sign_terms")
    if not (use_sign_terms and env.company.sign_terms_type == "html"):
        return

    if not qs or qs.lower() in "/sign/terms":
        yield {"loc": "/sign/terms"}


class TermsController(http.Controller):
    @http.route(
        "/sign/terms",
        type="http",
        auth="public",
        website=True,
        sitemap=sitemap_sign_terms,
    )
    def terms_conditions(self, **kwargs):
        use_sign_terms = request.env.registry.settings.get_bool(
            request.env, "sign.use_sign_terms"
        )
        if not (use_sign_terms and request.env.company.sign_terms_type == "html"):
            return request.env["ir.http"]._serve_error_page(
                request.env._("Oops"),
                request.env._(
                    """The requested page is invalid, or doesn't exist anymore."""
                ),
            )
        values = {"use_sign_terms": use_sign_terms, "company": request.env.company}
        return request.render("sign.sign_terms_conditions_page", values)
