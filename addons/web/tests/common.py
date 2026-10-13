import contextlib
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qsl, urlparse

from markupsafe import Markup
from werkzeug.datastructures import MultiDict
from werkzeug.test import EnvironBuilder
from werkzeug.user_agent import UserAgent

import odoo.http
from odoo.libs.web import urljoin as url_join
from odoo.tests import HOST, HttpCase
from odoo.tools import DotDict, config, frozendict


@contextlib.contextmanager
def MockRequest(
    env,
    *,
    path="/mockrequest",
    method="GET",
    user_agent="",
    context=frozendict(),
    cookies=frozendict(),
    country_code=None,
    city_name=None,
    remote_addr=HOST,
    environ_base=None,
    url_root=None,
    **attributes,
):
    lang_code = context.get("lang", env.context.get("lang", "en_US"))
    env = env(context=dict(context, lang=lang_code))
    if HttpCase.http_port():
        base_url = HttpCase.base_url()
    else:
        base_url = f"http://{HOST}:{config['http_port']}"
    request = Mock(
        httprequest=Mock(
            host="localhost",
            path=path,
            method=method,
            user_agent=UserAgent(user_agent),
            app=odoo.http.root,
            environ=dict(
                EnvironBuilder(
                    path=path,
                    method=method,
                    base_url=base_url,
                    headers={"User-Agent": user_agent} if user_agent else None,
                    environ_base=environ_base,
                ).get_environ(),
                REMOTE_ADDR=remote_addr,
            ),
            cookies=cookies,
            referrer="",
            remote_addr=remote_addr,
            url_root=url_root,
            args=MultiDict(parse_qsl(urlparse(path).query)),
        ),
        type="http",
        attempt_scratch=SimpleNamespace(),
        future_response=odoo.http.FutureResponse(),
        params={},
        session=DotDict(
            odoo.http.prepare_default_session(),
            context={"lang": ""},
        ),
        geoip=odoo.http.GeoIP("127.0.0.1", app=odoo.http.root),
        db=env.registry.db_name,
        env=env,
        registry=env.registry,
        cookies=cookies,
        lang=env["res.lang"]._get_data(code=lang_code),
        render=lambda *a, **kw: "<MockResponse>",
        nonce_scripts=lambda html: Markup(html or ""),
    )
    type(request).bound_env = property(lambda request: request.env)
    request.prepare_response = partial(odoo.http.Request.prepare_response, request)
    request.prepare_json_response = partial(
        odoo.http.Request.prepare_json_response, request
    )
    request.redirect = partial(odoo.http.Request.redirect, request)
    request.redirect_query = partial(odoo.http.Request.redirect_query, request)
    if url_root is not None:
        request.httprequest.url = url_join(url_root, path)
    for name, value in attributes.items():
        setattr(request, name, value)
    if country_code or city_name:
        request.geoip._city_record = odoo.http.geoip.geoip2.models.City(
            ["en"],
            country=(country_code and {"iso_code": country_code}) or {},
            city=(city_name and {"names": {"en": city_name}}) or {},
        )

    def update_context(**overrides):
        request.env = request.env(context=dict(request.env.context, **overrides))

    request.update_context = update_context

    odoo.http._request_stack.push(request)
    try:
        yield request
    finally:
        odoo.http._request_stack.pop()
