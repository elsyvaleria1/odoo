import contextlib
import threading
from unittest.mock import MagicMock, Mock, patch

from werkzeug.exceptions import NotFound

import odoo.http
from odoo.fields import Command

from odoo.addons.web.tests.common import MockRequest as WebMockRequest

FRONTEND_PROBE_ROUTE = "/http_routing/frontend_probe"
OFF_FRONTEND_REFUSAL_ROUTE = "/http_routing/off_frontend_refusal_probe"
GET_ONLY_PROBE_ROUTE = "/http_routing/get_only_probe"


class FrontendProbe(odoo.http.Controller):
    @odoo.http.route(
        FRONTEND_PROBE_ROUTE,
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        readonly=True,
    )
    def frontend_probe(self):
        return odoo.http.Response("probe", content_type="text/plain")


class GetOnlyProbe(odoo.http.Controller):
    @odoo.http.route(
        GET_ONLY_PROBE_ROUTE + '/<model("res.partner"):partner>',
        type="http",
        auth="public",
        methods=["GET"],
        website=True,
        sitemap=False,
        readonly=True,
    )
    def get_only_probe(self, partner):
        return odoo.http.Response("probe", content_type="text/plain")


class OffFrontendRefusalProbe(odoo.http.Controller):
    @odoo.http.route(OFF_FRONTEND_REFUSAL_ROUTE, type="http", auth="user")
    def off_frontend_refusal_probe(self):
        return odoo.http.request.env["ir.http"]._serve_error_page(
            "Refused", "A route off the frontend refused this request.", status=403
        )


def route_frontend_probe(test_class):
    test_class.env.registry.clear_cache("routing")
    test_class.addClassCleanup(test_class.env.registry.clear_cache, "routing")


def setup_frontend_langs(env, langs, default):
    env["ir.default"].set("res.partner", "lang", default.code)
    if "website" in env:
        env["website"].search([]).write(
            {
                "language_ids": [Command.set(langs.ids)],
                "default_lang_id": default.id,
            }
        )
    env.flush_all()
    env.registry.clear_cache()


@contextlib.contextmanager
def MockRequest(
    env,
    *,
    routing=True,
    multilang=True,
    website=None,
    mock_router=True,
    is_frontend=True,
    **kwargs,
):
    with (
        WebMockRequest(env, website=website, **kwargs) as request,
        contextlib.ExitStack() as stack,
    ):
        request.session["force_website_id"] = website and website.id
        request.website_routing = website.id if website else False
        if is_frontend is None:
            del request.is_frontend
            del request.is_frontend_multilang
        else:
            request.is_frontend = is_frontend
            request.is_frontend_multilang = is_frontend and multilang

        router = MagicMock()
        match = router.return_value.bind.return_value.match
        if routing:
            endpoint = Mock(
                routing={
                    "type": "http",
                    "website": True,
                    "multilang": multilang,
                }
            )
            match.return_value = (endpoint, {})
        else:
            match.side_effect = NotFound

        if mock_router:
            real_get_routing_map = odoo.http.root.get_routing_map
            owner = threading.get_ident()

            def get_routing_map(*args, **kwargs):
                if threading.get_ident() != owner:
                    return real_get_routing_map(*args, **kwargs)
                return router(*args, **kwargs)

            stack.enter_context(
                patch("odoo.http.root.get_routing_map", get_routing_map)
            )
        yield request
