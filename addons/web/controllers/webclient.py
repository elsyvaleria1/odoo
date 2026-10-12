import logging
from typing import Any

import odoo.tools
from odoo import http
from odoo.http import Response, request
from odoo.libs.asset_log import get_asset_logger, log_event
from odoo.libs.debug_log import DebugLog
from odoo.tools.assets.esm_registry import esm_registry

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
_http_log = get_asset_logger("http")


class WebClient(http.Controller):
    @http.route(
        "/web/webclient/translations",
        type="http",
        auth="public",
        cors="*",
        readonly=True,
    )
    def translations(
        self,
        hash: str | None = None,
        mods: str | None = None,
        lang: str | None = None,
    ) -> Response:
        _debug.lifecycle(
            "translations",
            lang=lang,
            client_hash=(hash or "")[:12] or None,
            explicit_mods=bool(mods),
        )
        module_sets = request.env["ir.http"]._get_webclient_translation_modules()
        requested = sorted(set(mods.split(","))) if mods else None
        matched = next(
            (modules for modules in module_sets if sorted(set(modules)) == requested),
            None,
        )
        if requested is not None and matched is None:
            _debug.logic("translations_mods_ignored", requested=len(requested))
        module_names = matched or module_sets[0]

        installed_langs = request.env["res.lang"].sudo().get_installed()
        if lang and lang not in {code for code, _ in installed_langs}:
            _debug.logic("translations_lang_not_installed", lang=lang)
            lang = None

        with _debug.perf(
            "translations_hash", cr=request.env.cr, mods=len(module_names)
        ):
            current_hash = (
                request.env["ir.http"]
                .with_context(cache_translation_data=True)
                ._get_web_translations_hash(module_names, lang)
            )

        body = {
            "lang": lang,
            "hash": current_hash,
        }
        if current_hash != hash:
            if "translation_data" in request.env.cr.cache:
                _debug.logic("translations_hash_miss", data_cached=True)
                body.update(request.env.cr.cache.pop("translation_data"))
            else:
                _debug.logic("translations_hash_miss", data_cached=False)
                with _debug.perf(
                    "translations_build", cr=request.env.cr, mods=len(module_names)
                ):
                    translations_per_module, lang_params = request.env[
                        "ir.http"
                    ]._get_translations_for_webclient(module_names, lang)
                body.update(
                    {
                        "lang_parameters": lang_params,
                        "modules": translations_per_module,
                        "multi_lang": len(installed_langs) > 1,
                    }
                )
            _debug.pipeline(
                "translations_body",
                hash=current_hash[:12],
                modules=len(body.get("modules") or ()),
            )
        else:
            _debug.logic("translations_hash_match", hash=current_hash[:12])

        return request.prepare_json_response(body, [("Cache-Control", "no-cache")])

    @http.route("/web/webclient/version_info", type="jsonrpc", auth="none")
    def version_info(self) -> dict[str, Any]:
        _debug.lifecycle("version_info")
        return odoo.service.common.exp_version()

    @http.route("/web/tests", type="http", auth="user", readonly=False)
    def unit_tests_suite(self, mod: str | None = None, **kwargs: Any) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle("unit_tests_suite", mod=mod, kwargs=sorted(kwargs))
        session_info = {"view_info": request.env["ir.ui.view"].get_view_info()}
        scope = request.env["ir.asset"]._get_unit_test_scope()
        _debug.logic("unit_tests_suite_scope", scope=scope or None)
        if scope:
            session_info["bundle_params"] = {"module_scope": scope}
        return request.render("web.unit_tests_suite", {"session_info": session_info})

    @http.route(
        "/web/bundle/<string:bundle_name>",
        auth="public",
        methods=["GET"],
        readonly=False,
    )
    def bundle(self, bundle_name: str, **bundle_params: Any) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle("bundle", bundle=bundle_name, params=sorted(bundle_params))
        if "lang" in bundle_params:
            request.update_context(
                lang=request.env["res.lang"]._get_code(bundle_params["lang"])
            )

        debug = bundle_params.get("debug", request.session.debug)
        page = bundle_params.pop("page", None) or None

        use_esm = bundle_name in esm_registry().bundles
        _debug.logic(
            "bundle_mode", bundle=bundle_name, esm=use_esm, debug=debug, page=page
        )
        log_event(
            _http_log,
            logging.DEBUG,
            "bundle_request",
            bundle=bundle_name,
            debug=bool(debug),
            is_esm=use_esm,
            params=sorted(bundle_params),
        )

        IrQweb = request.env["ir.qweb"]
        with _debug.perf("bundle_asset_nodes", cr=request.env.cr, bundle=bundle_name):
            if use_esm:
                nodes = IrQweb._links_to_nodes(
                    IrQweb._get_asset_links(bundle_name, debug=debug, js=True, css=True)
                )
            else:
                nodes = IrQweb._get_asset_nodes(
                    bundle_name, debug=debug, js=True, css=True
                )
        files = [
            {
                "type": tag,
                "src": attrs.get("src") or attrs.get("data-src") or attrs.get("href"),
            }
            for tag, attrs in nodes
            if tag != "link" or attrs.get("rel") == "stylesheet"
        ]

        if use_esm:
            with _debug.perf(
                "bundle_esm_payload", cr=request.env.cr, bundle=bundle_name
            ):
                payload = IrQweb._get_esm_bundle_payload(
                    bundle_name,
                    debug_assets=bool(debug) and "assets" in debug,
                    page=page,
                    with_test_satellites=IrQweb._has_esm_test_satellites(debug),
                )
            specifiers = payload["specifiers"]
            import_map = payload["import_map"]
            tpl_url = payload["template_url"]
            esm_url = payload.get("esm_url")
            if not specifiers and not esm_url and not tpl_url:
                _debug.logic("bundle_esm_payload_empty", bundle=bundle_name)
                use_esm = False

        if not use_esm:
            log_event(
                _http_log,
                logging.INFO,
                "served_legacy",
                bundle=bundle_name,
                files=len(files),
            )
            return request.prepare_json_response(files)

        descriptor = {
            "is_esm": True,
            "esm_url": esm_url,
            "specifiers": specifiers,
            "import_map": import_map,
            "files": files,
            "template_url": tpl_url,
            "carried": payload.get("carried", False),
            "owl_compiler": IrQweb._is_loaded_bundle_eval_needed(
                bundle_name, debug or ""
            ),
        }
        n_data_uri = sum(1 for v in import_map.values() if v.startswith("data:"))
        log_event(
            _http_log,
            logging.INFO,
            "served_esm",
            bundle=bundle_name,
            compiled=bool(esm_url),
            carried=payload.get("carried", False),
            specs=len(specifiers),
            imports=len(import_map),
            url=len(import_map) - n_data_uri,
            data=n_data_uri,
            files=len(files),
            tpl=bool(tpl_url),
        )
        return request.prepare_json_response(descriptor)
