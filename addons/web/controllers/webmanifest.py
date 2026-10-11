import base64
import mimetypes
from typing import Any
from urllib.parse import urlencode

from odoo import http, modules
from odoo.exceptions import AccessError
from odoo.http import Response, request
from odoo.libs.debug_log import DebugLog
from odoo.tools import file_open, file_path, str2bool
from odoo.tools.image import image_process

_debug = DebugLog(__name__)

MANIFEST_THEME_COLOR = "#f8f8fc"
MANIFEST_BACKGROUND_COLOR = "#f5f5f7"


def _get_icon_type(src: str) -> str:
    return mimetypes.guess_type(src)[0] or "image/png"


class WebManifest(http.Controller):
    @_debug.perf.timed
    def _get_shortcuts(self) -> list[dict[str, Any]]:
        module_names = ["mail", "crm", "project", "project_todo"]
        try:
            module_ids = (
                request.env["ir.module.module"]
                .search([("state", "=", "installed"), ("name", "in", module_names)])
                .sorted(key=lambda r: module_names.index(r["name"]))
            )
        except AccessError:
            _debug.logic("shortcuts_module_list_denied")
            return []
        menu_roots = request.env["ir.ui.menu"].get_user_roots()
        menu_data_records = (
            request.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("model", "=", "ir.ui.menu"),
                    ("res_id", "in", menu_roots.ids),
                    ("module", "in", module_names),
                ]
            )
        )
        shortcuts = []
        _debug.perf.count(
            "shortcuts_sources",
            installed=len(module_ids),
            candidates=len(module_names),
            roots=len(menu_roots),
            xmlids=len(menu_data_records),
        )
        menu_data_by_module = menu_data_records.grouped("module")
        for module in module_ids:
            data = menu_data_by_module.get(module.name)
            if data:
                shortcuts.append(
                    {
                        "name": module.display_name,
                        "url": f"/odoo?menu_id={data[0].res_id}",
                        "description": module.summary,
                        "icons": [
                            {
                                "sizes": "100x100",
                                "src": module.icon,
                                "type": _get_icon_type(module.icon),
                            }
                        ],
                    }
                )
            else:
                _debug.logic("shortcuts_no_root_menu", module=module.name)
        return shortcuts

    def _get_webmanifest(self) -> dict[str, Any]:
        web_app_name = request.env.registry.settings.get(
            request.env, "web.web_app_name", "Odoo"
        )
        manifest = {
            "name": web_app_name,
            "scope": "/odoo",
            "start_url": "/odoo",
            "display": "standalone",
            "background_color": MANIFEST_BACKGROUND_COLOR,
            "theme_color": MANIFEST_THEME_COLOR,
            "prefer_related_applications": False,
        }
        icon_sizes = ["192x192", "512x512"]
        manifest["icons"] = [
            {
                "src": f"/web/static/img/odoo-icon-{size}.png",
                "sizes": size,
                "type": "image/png",
            }
            for size in icon_sizes
        ]
        manifest["shortcuts"] = self._get_shortcuts()
        return manifest

    @http.route(
        "/web/manifest.webmanifest",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def webmanifest(self) -> Response:
        _debug.lifecycle("webmanifest")
        manifest = self._get_webmanifest()
        _debug.pipeline(
            "webmanifest_built",
            name=manifest["name"],
            shortcuts=len(manifest["shortcuts"]),
        )
        return request.prepare_json_response(
            manifest,
            [("Content-Type", "application/manifest+json")],
        )

    @http.route(
        "/web/service-worker.js",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def service_worker(self) -> Response:
        _debug.lifecycle("service_worker")
        return request.prepare_response(
            self._get_service_worker_content(),
            [
                ("Content-Type", "text/javascript"),
                ("Service-Worker-Allowed", "/odoo"),
            ],
        )

    def _get_service_worker_content(self) -> str:
        with file_open("web/static/src/service_worker.js") as f:
            return f.read()

    def _get_icon_path(self) -> str:
        return "web/static/img/odoo-icon-192x192.png"

    @http.route(
        "/odoo/offline",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def offline(self) -> Response:
        _debug.lifecycle("offline")
        with file_open(self._get_icon_path(), "rb") as f:
            odoo_icon = base64.b64encode(f.read())
        return request.render(
            "web.webclient_offline",
            {"odoo_icon": odoo_icon},
        )

    @http.route(
        "/scoped_app",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def scoped_app(self, app_id: str, path: str = "", app_name: str = "") -> Response:
        _debug.lifecycle(
            "scoped_app", app_id=app_id, path=path, explicit_name=bool(app_name)
        )
        app_name = app_name or self._get_scoped_app_name(app_id)
        path = f"/{path}"
        scoped_app_values = {
            "app_id": app_id,
            "apple_touch_icon": "/web/static/img/odoo-icon-ios.png",
            "app_name": app_name,
            "path": path,
            "safe_manifest_url": "/web/manifest.scoped_app_manifest?"
            + urlencode({"app_id": app_id, "path": path, "app_name": app_name}),
        }
        return request.render("web.webclient_scoped_app", scoped_app_values)

    @http.route(
        "/scoped_app_icon_png",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def scoped_app_icon_png(self, app_id: str, add_padding: bool = False) -> Response:
        _debug.lifecycle("scoped_app_icon", app_id=app_id, add_padding=add_padding)
        add_padding = str2bool(add_padding, False)
        app_icon = self._get_scoped_app_icons(app_id)[0]

        if app_icon["type"] == "image/svg+xml":
            manifest = modules.Manifest.for_addon(app_id, display_warning=False)
            add_padding = True
            if manifest and manifest["icon"]:
                icon_src = manifest["icon"]
            else:
                icon_src = f"/{self._get_icon_path()}"
            _debug.logic(
                "scoped_app_icon_svg_rasterized", app_id=app_id, icon_src=icon_src
            )
        else:
            icon_src = app_icon["src"]
            if not add_padding:
                _debug.logic("scoped_app_icon_png_redirect", app_id=app_id)
                return request.redirect(app_icon["src"])

        with (
            _debug.perf("scoped_app_icon_image_process", app_id=app_id),
            file_open(icon_src.removeprefix("/"), "rb") as file,
        ):
            image = image_process(
                file.read(),
                size=(180, 180),
                expand=True,
                colorize=(255, 255, 255),
                padding=16,
            )
        if not image:
            _debug.logic("scoped_app_icon_no_image", app_id=app_id, icon_src=icon_src)
            raise request.prepare_not_found_error()
        _debug.perf.count("scoped_app_icon_size", app_id=app_id, bytes=len(image))
        return request.prepare_response(image, headers=[("Content-Type", "image/png")])

    @http.route(
        "/web/manifest.scoped_app_manifest",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def scoped_app_manifest(
        self, app_id: str, path: str, app_name: str = ""
    ) -> Response:
        _debug.lifecycle(
            "scoped_app_manifest",
            app_id=app_id,
            path=path,
            explicit_name=bool(app_name),
        )
        app_name = app_name or self._get_scoped_app_name(app_id)
        webmanifest = {
            "icons": self._get_scoped_app_icons(app_id),
            "name": app_name,
            "scope": path,
            "start_url": path,
            "display": "standalone",
            "background_color": MANIFEST_BACKGROUND_COLOR,
            "theme_color": MANIFEST_THEME_COLOR,
            "prefer_related_applications": False,
            "shortcuts": self._get_scoped_app_shortcuts(app_id),
        }
        return request.prepare_json_response(
            webmanifest, [("Content-Type", "application/manifest+json")]
        )

    def _get_scoped_app_shortcuts(self, app_id: str) -> list[dict[str, Any]]:
        return []

    def _get_scoped_app_name(self, app_id: str) -> str:
        manifest = modules.Manifest.for_addon(app_id, display_warning=False)
        if manifest:
            return manifest["name"]
        _debug.logic("scoped_app_name_fallback", app_id=app_id)
        return app_id

    def _get_scoped_app_icons(self, app_id: str) -> list[dict[str, str]]:
        try:
            file_path(f"{app_id}/static/description/icon.svg")
        except FileNotFoundError:
            _debug.logic("scoped_app_default_icon", app_id=app_id)
            src = self._get_icon_path()
        else:
            src = f"{app_id}/static/description/icon.svg"
        return [
            {
                "src": f"/{src}",
                "sizes": "any",
                "type": _get_icon_type(src),
            }
        ]
