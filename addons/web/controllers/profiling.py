import base64

from odoo.exceptions import UserError
from odoo.http import (
    Controller,
    Response,
    prepare_content_disposition_header,
    request,
    route,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import extension_for, mimetype_for
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import dumps_bytes as json_dumps_bytes

_debug = DebugLog(__name__)

JSON_MIMETYPE = mimetype_for("json")


def _get_profiles(profile: str, purpose: str):
    try:
        profile_ids = [int(p) for p in profile.split(",")]
    except ValueError, AttributeError:
        _debug.logic(
            "profiles_not_found", profile=profile, purpose=purpose, reason="unparsable"
        )
        raise request.prepare_not_found_error() from None
    profiles = request.env["ir.profile"].browse(profile_ids).exists()
    if not profiles:
        _debug.logic(
            "profiles_not_found", profile=profile, purpose=purpose, reason="missing"
        )
        raise request.prepare_not_found_error()
    return profiles


class Profiling(Controller):
    @route("/web/set_profiling", type="http", auth="public", sitemap=False)
    def profile(
        self,
        profile: str | None = None,
        collectors: str | None = None,
        **params,
    ) -> Response:
        collector_names = (
            collectors.split(",") if collectors is not None else ["sql", "traces_async"]
        )
        # None leaves the session's profiling as it is; "" or "0" stops it
        enable = None if profile is None else profile not in ("", "0")
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "set_profiling",
                enable=enable,
                collectors=collector_names,
                params=sorted(params),
            )
        try:
            state = request.env["ir.profile"].set_profiling(
                enable, collectors=collector_names, params=params
            )
            if _debug.logic.enabled:
                _debug.logic("set_profiling_state", keys=sorted(state))
            return Response(json_dumps(state), mimetype="application/json")
        except UserError as e:
            _debug.logic("set_profiling_refused", error=str(e))
            return Response(response=f"error: {e}", status=403, mimetype="text/plain")

    @route(
        [
            "/web/speedscope/<profile>",
        ],
        type="http",
        sitemap=False,
        auth="user",
        readonly=True,
    )
    def speedscope(
        self, profile: str, action: str | bool = False, **kwargs
    ) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "speedscope", profile=profile, action=action, params=sorted(kwargs)
            )
        profiles = _get_profiles(profile, "speedscope")
        params = kwargs or profiles._prepare_profile_params_default()
        _debug.logic(
            "speedscope_params",
            profile=profile,
            params="explicit" if kwargs else "default",
            profiles=profiles,
        )
        with _debug.perf("speedscope_generate", cr=request.env.cr, profile=profile):
            speedscope_result = profiles._generate_speedscope(
                profiles._parse_params(params)
            )
        _debug.perf.count(
            "speedscope_size", profile=profile, bytes=len(speedscope_result)
        )
        if action == "speedscope_download_json":
            headers = [
                ("Content-Type", JSON_MIMETYPE),
                ("X-Content-Type-Options", "nosniff"),
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(
                        f"profile_{profile}.{extension_for(JSON_MIMETYPE)}"
                    ),
                ),
            ]
            return request.prepare_response(speedscope_result, headers)
        icp = request.env["ir.config_parameter"]
        context = {
            "profiles": profiles,
            "speedscope_base64": base64.b64encode(speedscope_result).decode("utf-8"),
            "url_root": request.httprequest.url_root,
            "cdn": icp.sudo().get_param(
                "speedscope_cdn",
                "https://cdn.jsdelivr.net/npm/speedscope@1.13.0/dist/release/",
            ),
        }
        with _debug.perf("speedscope_index_render", cr=request.env.cr, profile=profile):
            response = request.render("web.view_speedscope_index", context)
        if action == "speedscope_download_html":
            response.headers["Content-Disposition"] = (
                prepare_content_disposition_header(f"profile_{profile}.html")
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Type"] = "text/html"
        return response

    @route(
        [
            "/web/profile_config/<profile>",
        ],
        type="http",
        sitemap=False,
        auth="user",
        readonly=True,
    )
    def profile_config(
        self, profile: str, action: str | bool = False, **kwargs
    ) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "profile_config", profile=profile, action=action, params=sorted(kwargs)
            )
        profiles = _get_profiles(profile, "config")

        if action == "memory_open":
            with _debug.perf(
                "memory_profile_generate", cr=request.env.cr, profile=profile
            ):
                memory_profile = profiles._generate_memory_profile(
                    profiles._parse_params(kwargs)
                )
            encoded_memory_profile = json_dumps_bytes(memory_profile)
            _debug.perf.count(
                "memory_profile_size",
                profile=profile,
                bytes=len(encoded_memory_profile),
            )
            context = {
                "profile": profiles,
                "memory_graph": base64.b64encode(encoded_memory_profile).decode(
                    "utf-8"
                ),
            }
            return request.render("web.view_memory", context)

        context = {
            "default_params": profiles._prepare_profile_params_default(),
            "profile_str": profile,
            "profiles": profiles,
        }
        return request.render("web.config_speedscope_index", context)
