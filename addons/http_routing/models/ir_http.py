import contextlib
import logging
import re
import threading
import traceback
import typing
import urllib.parse

import werkzeug.exceptions
import werkzeug.http
import werkzeug.routing
from werkzeug.exceptions import HTTPException, NotFound

from odoo import api, exceptions, http, models, tools
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import Response, request
from odoo.libs.debug_log import DebugLog
from odoo.tools import lazy
from odoo.tools.urls import keep_query

from odoo.addons.base.models import ir_http
from odoo.addons.base.models.ir_http import RequestUID
from odoo.addons.base.models.res_lang import LangData
from odoo.addons.web.controllers.utils import (
    PARTIAL_NAVIGATION_HEADER,
    wants_fragments,
)

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_SLUG_NAME = r"\w{1,2}|\w[\w-]+?\w"
_SLUG_ID = r"-?\d+"
_SLUG_END = r"(?=$|\/|#|\?)"
_UNSLUG_RE = re.compile(rf"(?:({_SLUG_NAME})-)?({_SLUG_ID}){_SLUG_END}")
_UNSLUG_ROUTE_PATTERN = rf"(?:(?:{_SLUG_NAME})-)?(?:{_SLUG_ID}){_SLUG_END}"

FRONTEND_TRANSLATIONS_ROUTE = "/website/translations"

_REDIRECTABLE_METHODS = ("GET", "HEAD")

# A URL segment or an Accept-Language tag is read as a language only when it is
# shaped like one -- fr, FR, fr_FR, fr-fr, es_419, sr@latin -- so a page at
# /en_vivo is not taken for English. A configured url_code is matched as such
# before this applies.
_LANG_TAG_RE = re.compile(
    r"([a-z]{2,3})(?:[_-]([a-z]{2}|[0-9]{3}))?(@[a-z]+)?", re.IGNORECASE
)


def _lang_base(lang_code: str) -> str:
    return lang_code.partition("_")[0].partition("@")[0]


def _canonical_lang_code(tag: str) -> str | None:
    match = _LANG_TAG_RE.fullmatch(tag)
    if not match:
        return None
    lang, region, script = match.groups()
    return (
        lang.lower()
        + (f"_{region.upper()}" if region else "")
        + (script.lower() if script else "")
    )


class ModelConverter(ir_http.ModelConverter):
    def __init__(self, url_map, model=False, domain="[]") -> None:
        super().__init__(url_map, model)
        self.domain = domain
        self.regex = _UNSLUG_ROUTE_PATTERN

    def to_python(self, value) -> models.BaseModel:
        record = super().to_python(value)
        if not record.id:
            raise werkzeug.routing.ValidationError
        if record.id < 0:
            record = record.browse(-record.id)
        return record.with_context(_converter_value=value)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _slug(cls, value: models.BaseModel | tuple[int, str]) -> str:
        if isinstance(value, tuple):
            identifier, name = value
        else:
            identifier, name = value.check_singleton().id, value.display_name
        if not identifier:
            _debug.logic("slug_refused", reason="no_id")
            raise ValueError("Cannot slug non-existent record %r" % (value,))
        slugname = cls._slugify(name or "")
        if not slugname:
            return str(identifier)
        return f"{slugname}-{identifier}"

    @classmethod
    def _unslug(cls, value: str) -> tuple[str | None, int] | tuple[None, None]:
        m = _UNSLUG_RE.match(value)
        if not m:
            return None, None
        return m.group(1), int(m.group(2))

    @classmethod
    def _unslug_url(cls, value: str) -> str:
        path, suffix = cls._url_split_suffix(value)
        slash = "/" if path.endswith("/") and path != "/" else ""
        if slash:
            path = path[:-1]
        parts = path.split("/")
        slug_id = cls._unslug(parts[-1])[1]
        if slug_id is None:
            return value
        parts[-1] = str(slug_id)
        return "/".join(parts) + slash + suffix

    @classmethod
    def _get_converters(cls) -> dict[str, type]:
        return dict(
            super()._get_converters(),
            model=ModelConverter,
        )

    @classmethod
    def _url_split_suffix(cls, url: str) -> tuple[str, str]:
        head, hash_, fragment = url.partition("#")
        path, qmark, query = head.partition("?")
        return path, qmark + query + hash_ + fragment

    @classmethod
    def _lang_url_prefix(cls, path: str, url_code: str) -> str:
        if not path.startswith("/"):
            _logger.warning("Lang-prefixing a non root-relative path %r", path)
            _debug.logic("lang_prefix_on_relative_path", path=path, lang=url_code)
            path = "/" + path
        return f"/{url_code}{path if path != '/' else ''}"

    @classmethod
    def _lang_url_prefix_unless_default(
        cls, path: str, lang: LangData, force_default_lang: bool = False
    ) -> str:
        if (
            not force_default_lang
            and lang == request.env["ir.http"]._get_default_lang()
        ):
            return path
        return cls._lang_url_prefix(path, lang.url_code)

    @api.model
    def _frontend_url_codes(self) -> list[str]:
        return [info.url_code for info in self.env["res.lang"]._get_frontend().values()]

    @classmethod
    def _lang_url_split(
        cls, path: str, url_codes: list[str] | None = None
    ) -> tuple[str | None, str]:
        if url_codes is None:
            url_codes = request.env["ir.http"]._frontend_url_codes()
        segments = path.split("/")
        if len(segments) > 1 and segments[1] in url_codes:
            return segments[1], "/" + "/".join(segments[2:])
        return None, path

    @classmethod
    def _lang_url_unprefix(cls, path: str, url_codes: list[str] | None = None) -> str:
        return cls._lang_url_split(path, url_codes)[1]

    @classmethod
    def _url_localized(
        cls,
        url: str | None = None,
        lang_code: str | None = None,
        canonical_domain: str | None = None,
        prefetch_langs: bool = False,
        force_default_lang: bool = False,
    ) -> str:
        if url and (not url.startswith("/") or url.startswith("//")):
            return url

        if not lang_code:
            lang = request.lang
        else:
            lang = request.env["res.lang"]._get_data(code=lang_code)
            if not lang.url_code:
                lang = request.lang

        if not url:
            qs = keep_query()
            url = request.httprequest.path + ("?%s" % qs if qs else "")

        url, suffix = cls._url_split_suffix(url)

        url = cls._lang_url_unprefix(url)

        router = http.root.get_routing_map(request.db, env=request.env).bind("")
        try:
            # matched as the link will be followed, not as this request came:
            # a page answering a POST still links to its GET-only neighbours
            rule, args = router.match(path_info=url, method="GET", return_rule=True)
            for key, val in list(args.items()):
                if isinstance(val, models.BaseModel):
                    if isinstance(val.env.uid, RequestUID):
                        args[key] = val = val.with_user(request.env.uid)
                    if val.env.context.get("lang") != lang.code:
                        args[key] = val = val.with_context(lang=lang.code)
                    if prefetch_langs:
                        args[key] = val = val.with_context(prefetch_langs=True)
            path = router.build(rule.endpoint, args)
        except (
            HTTPException,
            AccessError,
            MissingError,
            werkzeug.routing.BuildError,
            ValueError,
        ):
            _debug.logic("url_localize", by="quote_unrouted", url=url, lang=lang.code)
            path = urllib.parse.quote(url, safe="/%")
        path = cls._lang_url_prefix_unless_default(path, lang, force_default_lang)

        if canonical_domain:
            try:
                return tools.urls.urljoin(canonical_domain, path)
            except ValueError:
                # An URL the router could not rebuild is quoted as-is above, so
                # it may still carry '.'/'..' segments -- scanners probe with
                # them. urljoin refuses to build a domain-qualified URL out of
                # such a path, and rightly so: it is not canonical. Degrade to
                # the root-relative path, like the no-domain branch below, as
                # this runs while rendering the error page of that very request.
                return path

        return path + suffix

    @classmethod
    def _url_for(cls, url_from: str, lang_code: str | None = None) -> str:
        location = (url_from or "").strip()
        force_lang = lang_code is not None
        try:
            url = urllib.parse.urlparse(location)
        except ValueError:
            return location
        if url.netloc or url.scheme or not (url.path or force_lang):
            return location

        IrHttp = request.env["ir.http"]
        location = urllib.parse.urljoin(request.httprequest.path, location)
        url_codes = IrHttp._frontend_url_codes()
        if not (len(url_codes) > 1 or force_lang) or not IrHttp._is_multilang_url(
            location, url_codes
        ):
            return location

        default_url_code = IrHttp._get_default_lang().url_code
        requested_code = (
            lang_code
            or request.env.context.get("lang")
            or getattr(getattr(request, "lang", None), "code", None)
        )
        lang_url_code = (
            request.env["res.lang"]._get_data(code=requested_code).url_code
            if requested_code
            else None
        )
        if lang_url_code not in url_codes:
            # A language the site does not serve is kept only when the caller
            # named it: the target may serve more languages than the site does
            # (survey serves every installed one). One that merely leaked in
            # from the context -- a backend user's language -- would 404.
            _debug.logic("url_lang_unserved", lang=requested_code, kept=bool(lang_code))
            lang_url_code = (
                (lang_url_code or lang_code) if lang_code else default_url_code
            )

        path, suffix = cls._url_split_suffix(location)
        if path.endswith("/") and path != "/":
            path = path[:-1]
        url_code, rest = cls._lang_url_split(path, url_codes)
        if url_code is not None:
            if force_lang:
                path = cls._lang_url_prefix(rest, lang_url_code)
            elif url_code == default_url_code:
                path = rest
        elif force_lang or lang_url_code != default_url_code:
            path = cls._lang_url_prefix(rest, lang_url_code)
        return path + suffix

    @classmethod
    def _is_multilang_routing(cls, routing: dict[str, typing.Any]) -> bool:
        return bool(
            routing.get("website")
            and routing.get("multilang", routing["type"] == "http")
        )

    @classmethod
    def _is_asset_or_webclient_path(cls, path: str) -> bool:
        return "/static/" in path or path.startswith("/web/")

    @api.model
    def _is_multilang_url(
        self, local_url: str, lang_url_codes: list[str] | None = None
    ) -> bool:
        if lang_url_codes is None:
            lang_url_codes = self.env["ir.http"]._frontend_url_codes()
        path, _suffix = self._url_split_suffix(local_url)
        path = self._lang_url_unprefix(path, lang_url_codes)

        if self._is_asset_or_webclient_path(path):
            _debug.logic(
                "multilang_url", verdict=False, reason="asset_or_web", url=local_url
            )
            return False

        _, func = self.env["ir.http"].url_rewrite(path)
        return not func or self._is_multilang_routing(func.routing)

    @api.model
    @tools.ormcache()
    def _get_default_lang_code(self) -> str | None:
        return self.env["ir.default"].sudo()._get("res.partner", "lang")

    @api.model
    def _get_default_lang(self) -> LangData:
        Lang = self.env["res.lang"]
        lang_code = self._get_default_lang_code()
        lang = Lang._get_data(code=lang_code) if lang_code else None
        if not lang:
            lang = next(iter(Lang._get_active_by_field("code").values()))
            _debug.logic("default_lang", by="first_active", lang=lang.code)
        return lang

    @api.model
    def get_frontend_session_info(self) -> dict:
        session_info = super().get_frontend_session_info()

        if getattr(request, "is_frontend", False):
            session_info["bundle_params"]["lang"] = request.lang.code
        session_info.update(
            {
                "translationURL": FRONTEND_TRANSLATIONS_ROUTE,
            }
        )
        return session_info

    @api.model
    def _get_webclient_translation_modules(self) -> list[list[str]]:
        return [
            *super()._get_webclient_translation_modules(),
            self._get_translation_frontend_modules_name(),
        ]

    @classmethod
    def _get_translation_frontend_modules_name(cls) -> list[str]:
        return ["web"]

    @api.model
    def get_nearest_lang(self, lang_code: str | None) -> str | None:
        """Return the active frontend language code nearest to ``lang_code``.

        An exact match wins outright. Otherwise, among the active frontend
        languages that share ``lang_code``'s base (e.g. ``es_MX`` and
        ``es_419`` both base to ``"es"``), the first one in
        ``res.lang._get_frontend()``'s iteration order is returned — which is
        alphabetical by language display name, not by any linguistic or
        geographic notion of "nearest". When two or more variants of the same
        base are active, which one wins this tie-break is therefore
        arbitrary but deterministic.
        """
        if not lang_code:
            return None

        frontend_langs = self.env["res.lang"]._get_frontend()
        if lang_code in frontend_langs:
            return lang_code

        base = _lang_base(lang_code)
        if not base:
            return None
        _debug.logic("nearest_lang", wanted=lang_code, base=base)
        return next((code for code in frontend_langs if _lang_base(code) == base), None)

    @classmethod
    def _match(cls, path: str) -> tuple[werkzeug.routing.Rule, dict[str, typing.Any]]:
        if hasattr(request, "is_frontend"):
            return super()._match(path)

        # See /1, match a non website endpoint
        matched = not_found = None
        try:
            rule, args = cls._match_and_flag(path)
            if not request.is_frontend:
                return rule, args
            matched = (rule, args)
        except NotFound as exc:
            not_found = exc
            url_lang_str, _, rest = path[1:].partition("/")
            path_no_lang = "/" + rest
        else:
            url_lang_str = ""
            path_no_lang = path

        allow_redirect = (
            request.httprequest.method in _REDIRECTABLE_METHODS
            and getattr(request, "is_frontend_multilang", True)
        )

        if allow_redirect and "//" in path:
            new_url = re.sub(r"/{2,}", "/", path)
            _debug.logic("path_collapsed", path=path, to=new_url)
            werkzeug.exceptions.abort(
                request.redirect_query(
                    new_url, request.httprequest.args, code=301, local=True
                )
            )

        default_lang, nearest_url_lang = cls._resolve_frontend_lang(url_lang_str)
        if not nearest_url_lang:
            url_lang_str = None

        served_path = cls._reroute_for_lang(
            path, path_no_lang, url_lang_str, default_lang, allow_redirect
        )

        if matched is not None:
            return matched

        if served_path != path:
            try:
                return cls._match_and_flag(served_path)
            except NotFound as exc:
                not_found = exc
        _debug.logic(
            "frontend_not_found", path=served_path, rerouted=served_path != path
        )
        request.is_frontend = True
        request.is_frontend_multilang = True
        raise not_found

    @classmethod
    def _match_and_flag(
        cls, path: str
    ) -> tuple[werkzeug.routing.Rule, dict[str, typing.Any]]:
        rule, args = super()._match(path)
        routing = rule.endpoint.routing
        request.is_frontend = routing.get("website", False)
        request.is_frontend_multilang = cls._is_multilang_routing(routing)
        _debug.logic(
            "route_flagged",
            path=path,
            frontend=request.is_frontend,
            multilang=request.is_frontend_multilang,
        )
        return rule, args

    @classmethod
    def _resolve_frontend_lang(cls, url_lang_str: str) -> tuple[LangData, str | None]:
        with cls._borrowed_public_env() as real_env:
            IrHttp = request.env["ir.http"]
            Lang = request.env["res.lang"]
            url_lang_code = url_lang_str and (
                Lang._get_data(url_code=url_lang_str).code
                or _canonical_lang_code(url_lang_str)
            )
            nearest_url_lang = (
                IrHttp.get_nearest_lang(url_lang_code) if url_lang_code else None
            )
            default_lang = IrHttp._get_default_lang()
            sources = (
                ("url", lambda: nearest_url_lang),
                (
                    "cookie",
                    lambda: IrHttp.get_nearest_lang(
                        request.cookies.get("frontend_lang")
                    ),
                ),
                # an anonymous session's context language is the browser's
                # (Request.get_default_lang): it is the "browser" source, which
                # a site may switch off, not a choice the visitor made
                (
                    "user",
                    lambda: (
                        request.session.uid
                        and IrHttp.get_nearest_lang(real_env.context.get("lang"))
                    ),
                ),
                ("browser", IrHttp._get_nearest_browser_lang),
            )
            by, code = "default", default_lang.code
            for source, resolve in sources:
                if found := resolve():
                    by, code = source, found
                    break
            request.lang = Lang._get_data(code=code)
            _debug.logic(
                "frontend_lang",
                by=by,
                lang=request.lang.code,
                url_code=url_lang_str or None,
            )
        return default_lang, nearest_url_lang

    @api.model
    def _uses_browser_lang(self) -> bool:
        return True

    @api.model
    def _get_nearest_browser_lang(self) -> str | None:
        if not self._uses_browser_lang():
            return None
        for tag, _quality in request.httprequest.accept_languages:
            code = _canonical_lang_code(tag)
            if code and (nearest := self.get_nearest_lang(code)):
                _debug.logic("browser_lang", tag=tag, lang=nearest)
                return nearest
        return None

    @classmethod
    @contextlib.contextmanager
    def _borrowed_public_env(cls) -> typing.Iterator[api.Environment]:
        real_env = request.env
        real_default_env = real_env.transaction.default_env
        real_uid = getattr(threading.current_thread(), "uid", None)
        try:
            request.registry["ir.http"]._auth_method_public()
            yield real_env
        finally:
            request.env = real_env
            real_env.transaction.default_env = real_default_env
            threading.current_thread().uid = real_uid

    @classmethod
    def _redirect_lang(cls, target: str, code: int = 303) -> typing.NoReturn:
        _debug.logic("lang_redirect", to=target, code=code, lang=request.lang.code)
        redirect = request.redirect_query(target, request.httprequest.args, code=code)
        redirect.set_cookie("frontend_lang", request.lang.code)
        werkzeug.exceptions.abort(redirect)

    @classmethod
    def _reroute_for_lang(
        cls,
        path: str,
        path_no_lang: str,
        url_lang_str: str | None,
        default_lang: LangData,
        allow_redirect: bool,
    ) -> str:
        if url_lang_str:
            return cls._reroute_for_prefixed_lang(
                path, path_no_lang, url_lang_str, default_lang, allow_redirect
            )

        # See /2, no lang in url and default website
        if request.lang == default_lang:
            _debug.logic("reroute_for_lang", by="default_lang", path=path)

        # See /3, missing lang in url but user-agent is a bot
        elif request.env["ir.http"].is_a_bot():
            _debug.logic(
                "reroute_for_lang", by="bot", path=path, ignored=request.lang.code
            )
            request.lang = default_lang

        # See /4, no lang in url and should not redirect (e.g. POST), continue
        elif not allow_redirect:
            _debug.logic(
                "reroute_for_lang",
                by="no_lang_no_redirect",
                path=path,
                lang=request.lang.code,
            )

        # See /5, missing lang in url, /home -> /fr/home
        else:
            _debug.logic(
                "reroute_for_lang", by="missing_lang", path=path, lang=request.lang.code
            )
            cls._redirect_lang(cls._lang_url_prefix(path, request.lang.url_code))

        return path

    @classmethod
    def _reroute_for_prefixed_lang(
        cls,
        path: str,
        path_no_lang: str,
        url_lang_str: str,
        default_lang: LangData,
        allow_redirect: bool,
    ) -> str:
        request_url_code = request.lang.url_code

        if allow_redirect:
            # See /6, default lang in url, /en/home and /en_US/home -> /home.
            # Compared on the resolved language, not the segment: an alias of
            # the default language goes there in one hop instead of 301-ing to
            # /en/home first.
            if request.lang == default_lang:
                _debug.logic("reroute_for_lang", by="default_lang_in_url", path=path)
                cls._redirect_lang(path_no_lang)

            # See /7, lang alias in url, /fr_FR/home -> /fr/home
            if url_lang_str != request_url_code:
                _debug.logic(
                    "reroute_for_lang", by="lang_alias", path=path, to=request_url_code
                )
                cls._redirect_lang(
                    cls._lang_url_prefix(path_no_lang, request_url_code), code=301
                )

            # See /8, homepage with trailing slash, /fr/ -> /fr
            if path == f"/{url_lang_str}/":
                _debug.logic("reroute_for_lang", by="trailing_slash", path=path)
                cls._redirect_lang(path[:-1], code=301)

        # See /9, canonical lang in url, or any lang when redirecting is forbidden
        _debug.logic(
            "reroute_for_lang",
            by="valid_lang_rerouted",
            path=path,
            to=path_no_lang,
            redirectable=allow_redirect,
        )
        request.reroute(path_no_lang)
        return path_no_lang

    @classmethod
    def _update_request_context(cls) -> None:
        super()._update_request_context()
        if request.is_frontend:
            cls._frontend_pre_dispatch()

    @classmethod
    def _is_partial_navigation(cls) -> bool:
        return bool(
            request and request.httprequest.headers.get(PARTIAL_NAVIGATION_HEADER)
        )

    @classmethod
    def _post_dispatch(cls, response) -> None:
        super()._post_dispatch(response)
        if getattr(request, "is_frontend", False):
            response.headers.add("Vary", PARTIAL_NAVIGATION_HEADER)

    @classmethod
    def _pre_dispatch(
        cls, rule: werkzeug.routing.Rule, args: dict[str, typing.Any]
    ) -> None:
        super()._pre_dispatch(rule, args)

        if (
            not request.is_frontend_multilang
            or request.httprequest.method not in _REDIRECTABLE_METHODS
        ):
            return
        try:
            built, error = rule.build(args), None
        except (ValueError, TypeError, werkzeug.routing.ValidationError) as exc:
            built, error = None, exc
        if not built:
            _logger.warning(
                "Cannot rebuild a canonical URL for rule %r (%s), "
                "serving %r without the slug redirect",
                rule.rule,
                error or "a converter rejected the value",
                request.httprequest.path,
            )
            return
        _, path = built
        if urllib.parse.unquote(path) != request.httprequest.path:
            _debug.logic("canonical_redirect", path=request.httprequest.path, to=path)
            werkzeug.exceptions.abort(
                request.redirect_query(
                    cls._lang_url_prefix_unless_default(path, request.lang),
                    request.httprequest.args,
                    code=301,
                )
            )

    @classmethod
    def _frontend_pre_dispatch(cls) -> None:
        request.update_context(lang=request.lang.code)
        if request.cookies.get("frontend_lang") != request.lang.code:
            request.future_response.set_cookie("frontend_lang", request.lang.code)

    @classmethod
    def _prepare_exception_code_and_values(
        cls, exception: Exception
    ) -> tuple[int, dict[str, typing.Any]]:
        code = 500
        values = {
            "exception": exception,
            # shown to an editor or in debug mode only: a crawler's 404 flood
            # should not format a stack per request
            "traceback": lazy(lambda: "".join(traceback.format_exception(exception))),
        }

        if isinstance(exception, exceptions.UserError):
            code = exception.http_status
            values["error_message"] = exception.args[0]
        elif isinstance(exception, werkzeug.exceptions.HTTPException):
            code = exception.code or 500
            values["error_message"] = exception.description

        if hasattr(exception, "qweb"):
            values.update(qweb_exception=exception.qweb)
            if code == 404 and exception.qweb.path:
                code = 500

        values.update(
            status_message=werkzeug.http.HTTP_STATUS_CODES.get(code, ""),
            status_code=code,
        )

        return (code, values)

    @classmethod
    def _get_values_500_error(cls, env, values, exception):
        values["view"] = env["ir.ui.view"]
        return values

    @classmethod
    def _get_error_template(cls, code: int, values: dict[str, typing.Any]) -> str:
        return "http_routing.%s" % code

    @classmethod
    def _get_error_html(
        cls, env, code: int, values: dict[str, typing.Any]
    ) -> tuple[int, typing.Any]:
        View = env["ir.ui.view"]
        try:
            return code, View._render_template(
                cls._get_error_template(code, values), values
            )
        except MissingError:
            return code, View._render_template(
                "http_routing.4xx" if 400 <= code < 500 else "http_routing.http_error",
                values,
            )

    @classmethod
    def _serve_error_page(cls, title: str, message: str, *, status: int) -> Response:
        # http_error's layout reads what only a frontend request carries
        # (portal's frontend_languages, website's website), so a route that is
        # not one -- a backend download, an OAuth callback -- is made one first
        if not getattr(request, "is_frontend", False):
            _debug.logic("error_page_made_frontend", path=request.httprequest.path)
            request.is_frontend = True
            request.is_frontend_multilang = False
            cls._resolve_frontend_lang("")
            cls._frontend_pre_dispatch()
        return request.render(
            "http_routing.http_error",
            {"status_code": title, "status_message": message},
            status=status,
        )

    @classmethod
    def _handle_error(cls, exception):
        # a refusal of a form posted in place (@web/public/fragment_form) is
        # told to the page, which stays as it is
        if isinstance(exception, UserError) and wants_fragments():
            request.env.cr.rollback()
            return request.prepare_json_response(
                {"error": {"message": exception.args[0]}},
                status=403 if isinstance(exception, AccessError) else 422,
            )
        response = super()._handle_error(exception)

        is_frontend_request = bool(getattr(request, "is_frontend", False))
        if not is_frontend_request or not isinstance(response, HTTPException):
            return response

        if not request.env.uid:
            cls._auth_method_public()
        cls._handle_debug()
        if not getattr(request, "lang", None):
            request.lang = request.env["ir.http"]._get_default_lang()
        cls._frontend_pre_dispatch()
        request.params = request.get_http_params()

        code, values = cls._prepare_exception_code_and_values(exception)

        request.env.cr.rollback()
        # an unrouted URL has been through the fallback already, in
        # _serve_ir_http_fallback, before this NotFound was raised
        if code in (404, 403) and not getattr(
            request.attempt_scratch, "fallback_tried", False
        ):
            try:
                response = cls._serve_fallback()
                if response:
                    cls._post_dispatch(response)
                    return response
            except werkzeug.exceptions.Forbidden:
                pass
        elif code >= 500:
            values = cls._get_values_500_error(request.env, values, exception)
        try:
            code, html = cls._get_error_html(request.env, code, values)
        except Exception:
            _logger.exception("Couldn't render a template for http status %s", code)
            request.env.cr.rollback()
            html = request.env["ir.ui.view"]._render_template(
                "http_routing.http_error", values
            )

        response = Response(html, status=code, content_type="text/html;charset=utf-8")
        cls._post_dispatch(response)
        return response

    @api.model
    def _routing_map_key(self) -> int | str | None:
        return None

    @api.model
    @tools.ormcache("self._routing_map_key()", "path", cache="routing.rewrites")
    def url_rewrite(self, path: str) -> tuple[str, typing.Any]:
        return self._url_rewrite(path, frozenset())

    def _url_rewrite(
        self, path: str, _visited: frozenset[str]
    ) -> tuple[str, typing.Any]:
        router = http.root.get_routing_map(
            self.env.registry.db_name, env=self.env
        ).bind("")
        try:
            try:
                func, _args = router.match(path, method="POST")
            except werkzeug.exceptions.MethodNotAllowed:
                func, _args = router.match(path, method="GET")
        except werkzeug.routing.RequestRedirect as e:
            new_path = urllib.parse.urlsplit(e.new_url).path or "/"
            if new_path == path or new_path in _visited:
                _logger.warning(
                    "Redirect loop while rewriting %r (targets %r again)",
                    path,
                    new_path,
                )
                return path, False
            return self._url_rewrite(new_path, _visited | {path})
        except HTTPException:
            return path, False
        return path, func
