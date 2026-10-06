import base64
import logging
import re
from urllib.parse import quote, urlsplit

import requests

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import escape_psql, misc
from odoo.tools.assets.constants import DOTTED_ASSET_EXTENSIONS as EXTENSIONS

from odoo.addons.website.tools import (
    COLOR_PALETTE_URL,
    GRAY_COLOR_PALETTE_URL,
    RE_SCSS_MAP_ENTRY,
    RUNTIME_KEYS_BY_URL,
    RUNTIME_PALETTE_KEYS,
    SALES_HEADER_KEYS,
    THEME_COLOR_PALETTE_URL,
    THEME_CUSTOMIZATION_GROUPS,
    THEME_VALUES_URL,
)

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_match_asset_file_url_regex = re.compile(r"^(/_custom/([^/]+))?/(\w+)/([/\w]+\.\w+)$")

_GOOGLE_FONT_TIMEOUT = 5
_MAX_GOOGLE_FONTS = 20
_MAX_GOOGLE_FONT_SOURCES = 40
_MAX_GOOGLE_FONT_BYTES = 5 * 1024 * 1024
_GOOGLE_FONT_HEADERS = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.41 Safari/537.36",
}


class WebsiteAssets(models.AbstractModel):
    _name = "website.assets"
    _description = "Assets Utils"

    @api.model
    def reset_asset(self, url, bundle) -> None:
        custom_url = self._prepare_custom_asset_url(url, bundle)

        _debug.lifecycle("asset_reset", url=url, bundle=bundle)
        self._get_custom_attachment(custom_url).unlink()
        self._get_custom_asset(custom_url).unlink()
        if bundle != "web.assets_frontend":
            return
        website = self.env["website"].get_current_website()
        if group := THEME_CUSTOMIZATION_GROUPS.get(url):
            website.theme_scss_values = {
                name: entries
                for name, entries in (website.theme_scss_values or {}).items()
                if name != group
            }
        if keys := RUNTIME_KEYS_BY_URL.get(url):
            website.theme_values = {
                key: value
                for key, value in (website.theme_values or {}).items()
                if key not in keys
            }

    @api.model
    def save_asset(self, url, bundle, content, file_type) -> None:
        if bundle == "web.assets_frontend" and url in THEME_CUSTOMIZATION_GROUPS:
            self._save_scss_customization_source(url, content)
            return
        self._save_custom_asset(url, bundle, content, file_type)

    def _save_scss_customization_source(self, url, content) -> None:
        # The bundle generates the file from the website's theme_scss_values,
        # so an edit made in the code editor is kept as entries; anything else
        # it added would have nowhere to live.
        template = self._get_scss_map_template(url)
        if RE_SCSS_MAP_ENTRY.sub("", content).split() != template.split():
            raise UserError(
                _(
                    "%s is generated from the theme options: only its entries "
                    "can be edited.",
                    url.rpartition("/")[2],
                )
            )
        self.env["website"].get_current_website()._set_scss_customization(
            url,
            {
                match["key"]: match["value"].strip()
                for match in RE_SCSS_MAP_ENTRY.finditer(content)
            },
        )

    def _save_custom_asset(self, url, bundle, content, file_type) -> None:
        custom_url = self._prepare_custom_asset_url(url, bundle)
        datas = base64.b64encode((content or "\n").encode("utf-8"))

        custom_attachment = self._get_custom_attachment(custom_url)
        if custom_attachment:
            _debug.lifecycle(
                "asset_saved",
                by="overwrite",
                url=url,
                bundle=bundle,
                attachment=custom_attachment.id,
            )
            custom_attachment.write({"datas": datas})
            self.env.registry.clear_cache("assets")
        else:
            new_attach = {
                "name": url.split("/")[-1],
                "type": "binary",
                "mimetype": ((file_type == "js" and "text/javascript") or "text/scss"),
                "datas": datas,
                "url": custom_url,
                **self._add_website_id({}),
            }
            self.env["ir.attachment"].create(new_attach)

            IrAsset = self.env["ir.asset"]
            new_asset = {
                "path": custom_url,
                "target": url,
                "directive": "replace",
                **self._add_website_id({}),
            }
            target_asset = self._get_custom_asset(url)
            if target_asset:
                new_asset["name"] = target_asset.name + " override"
                new_asset["bundle"] = target_asset.bundle
                new_asset["sequence"] = target_asset.sequence
            else:
                new_asset["name"] = "%s: replace %s" % (
                    bundle,
                    custom_url.split("/")[-1],
                )
                new_asset["bundle"] = IrAsset._get_bundle_containing_path(url, bundle)
            _debug.lifecycle(
                "asset_saved",
                by="override_created",
                url=url,
                bundle=new_asset["bundle"],
                overrides=target_asset.id if target_asset else None,
            )
            IrAsset.create(new_asset)

    @api.model
    def _get_content_from_url(self, url, url_info=None, custom_attachments=None):
        if url in THEME_CUSTOMIZATION_GROUPS:
            website = self.env["website"].get_current_website()
            entries = website._get_scss_customization(url)
            return self._get_scss_map_content(url, entries).encode()
        if url_info is None:
            url_info = self._get_data_from_url(url)

        if url_info["customized"]:
            attachment = None
            if custom_attachments is None:
                attachment = self._get_custom_attachment(url)
            else:
                attachment = custom_attachments.filtered(lambda r: r.url == url)
            return (attachment and base64.b64decode(attachment.datas)) or False

        with misc.file_open(url.strip("/"), "rb", filter_ext=EXTENSIONS) as f:
            return f.read()

    @api.model
    def _get_data_from_url(self, url) -> dict | None:
        m = _match_asset_file_url_regex.match(url)
        if not m:
            _debug.logic("asset_url_unrecognized", url=url)
            return None
        return {
            "module": m.group(3),
            "resource_path": m.group(4),
            "customized": bool(m.group(1)),
            "bundle": m.group(2) or False,
        }

    @api.model
    def _prepare_custom_asset_url(self, url, bundle_xmlid) -> str:
        return f"/_custom/{bundle_xmlid}{url}"

    @api.model
    def update_scss_customization(self, url, values) -> dict:
        _debug.pipeline(
            "scss_customization", url=url, keys=sorted(values), count=len(values)
        )
        website = self.env["website"].get_current_website()
        runtime_keys = RUNTIME_KEYS_BY_URL.get(url, frozenset())
        runtime = {key: values.pop(key) for key in list(values) if key in runtime_keys}
        if runtime:
            held = self._get_scss_customized_keys(url)
            compiled = {}
            for key, value in runtime.items():
                value = str(value)
                if website._theme_value_is_unset(key, value):
                    if key in held:
                        compiled[key] = "null"
                elif website._is_theme_value_compile_needed(key, value):
                    compiled[key] = value
            if url == COLOR_PALETTE_URL:
                if compiled or not website._theme_palette_fits_runtime(runtime):
                    popped = website._pop_theme_values(RUNTIME_PALETTE_KEYS)
                    values = popped | values | runtime
                    runtime = {}
            else:
                values |= compiled
                runtime |= dict.fromkeys(compiled, "null")
        if runtime:
            website._set_theme_values(runtime)
        if url == THEME_VALUES_URL and "header-template" in values:
            # Only the chosen sales header is compiled with its colour rules, so
            # its runtime colours are judged against nothing once it changes.
            if sales := website._pop_theme_values(SALES_HEADER_KEYS):
                self._write_scss_customization(COLOR_PALETTE_URL, sales)
        reload_bundles = bool(values) and self._write_scss_customization(url, values)
        return {
            "reload_bundles": reload_bundles,
            "theme_values_css": str(website._get_theme_values_css()),
        }

    def _get_scss_customized_keys(self, url):
        website = self.env["website"].get_current_website()
        return set(website._get_scss_customization(url))

    def _get_scss_map_template(self, url):
        with misc.file_open(url.strip("/"), "rb", filter_ext=EXTENSIONS) as f:
            return f.read().decode()

    def _get_scss_map_content(self, url, entries):
        template = self._get_scss_map_template(url)
        return re.sub(
            r"^( *)(.*hook.*)$",
            lambda match: (
                "".join(
                    f"{match[1]}'{key}': {entries[key]},\n" for key in sorted(entries)
                )
                + match[0]
            ),
            template,
            count=1,
            flags=re.MULTILINE,
        )

    def _write_scss_customization(self, url, values):
        palette_reset = "color-palettes-name" in values
        if palette_reset:
            _debug.logic("color_palette_reset", palette=values["color-palettes-name"])
            self.reset_asset(COLOR_PALETTE_URL, "web.assets_frontend")
            self.reset_asset(GRAY_COLOR_PALETTE_URL, "web.assets_frontend")
            self.update_scss_customization(
                THEME_COLOR_PALETTE_URL,
                {
                    "success": "null",
                    "info": "null",
                    "warning": "null",
                    "danger": "null",
                },
            )
            preset_gradients = {f"o-cc{cc}-bg-gradient": "null" for cc in range(1, 6)}
            self.update_scss_customization(
                THEME_VALUES_URL,
                {
                    "menu-gradient": "null",
                    "menu-secondary-gradient": "null",
                    "footer-gradient": "null",
                    "copyright-gradient": "null",
                    **preset_gradients,
                },
            )

        delete_attachment_id = values.pop("delete-font-attachment-id", None)
        if delete_attachment_id:
            delete_attachment_id = int(delete_attachment_id)
            self.env["ir.attachment"].search(
                [
                    "|",
                    ("id", "=", delete_attachment_id),
                    ("original_id", "=", delete_attachment_id),
                    ("name", "like", "google-font"),
                ]
            ).unlink()
            _debug.lifecycle("google_font_deleted", attachment=delete_attachment_id)

        google_local_fonts = values.get("google-local-fonts")
        if google_local_fonts and google_local_fonts != "null":
            google_local_fonts = dict(
                re.findall(r"'([^']+)': '?(\d*)", google_local_fonts)
            )
            google_local_fonts = self._localize_google_fonts(google_local_fonts)
            values["google-local-fonts"] = (
                str(google_local_fonts).replace("{", "(").replace("}", ")")
            )

        website = self.env["website"].get_current_website()
        entries = website._get_scss_customization(url)
        updated = dict(entries)
        for name, value in values.items():
            if isinstance(value, str):
                value = re.sub(
                    r"var\(--([0-9]+)\)",
                    lambda matchobj: "var(--#{" + matchobj.group(1) + "})",
                    value,
                )
            # Every customization map goes through o-map-omit, so a null entry
            # and an absent one compile alike: drop it rather than store it.
            if value == "null":
                updated.pop(name, None)
            else:
                updated[name] = str(value)
        if updated == entries:
            return palette_reset
        website._set_scss_customization(url, updated)
        return True

    def _localize_google_fonts(self, google_local_fonts):
        resolved = {}
        fetched = 0
        for font_name, size in google_local_fonts.items():
            if size:
                resolved[font_name] = int(size)
                continue
            if fetched >= _MAX_GOOGLE_FONTS:
                _logger.warning(
                    "Refusing to fetch more than %s Google fonts in one save; "
                    "%r left online.",
                    _MAX_GOOGLE_FONTS,
                    font_name,
                )
                continue
            fetched += 1
            attachment_id = self._create_google_local_font(font_name)
            if attachment_id:
                _debug.lifecycle(
                    "google_font_localized", font=font_name, attachment=attachment_id
                )
                resolved[font_name] = attachment_id
            else:
                _debug.logic("google_font_not_localized", font=font_name)
                _logger.warning(
                    "Could not localise Google font %r; leaving it online.",
                    font_name,
                )
        return resolved

    def _create_google_local_font(self, font_name) -> int | None:
        IrAttachment = self.env["ir.attachment"]
        css = self._http_get_google_font(
            f"https://fonts.googleapis.com/css?family={quote(font_name)}"
            ":300,300i,400,400i,700,700i&display=swap",
            expect_binary=False,
        )
        if css is None:
            _debug.logic("google_font_css_unavailable", font=font_name)
            return None
        font_content = css.decode()

        font_family_attachments = IrAttachment
        source_count = 0

        def replace_src(match):
            nonlocal source_count, font_family_attachments
            statement = match.group()
            m = re.match(r"src: url\(([^\)]+)\) (.+)", statement)
            if not m:
                return statement
            if source_count >= _MAX_GOOGLE_FONT_SOURCES:
                _logger.warning(
                    "Google font %r exposes more than %s sources; truncating.",
                    font_name,
                    _MAX_GOOGLE_FONT_SOURCES,
                )
                return statement
            source_count += 1
            url, font_format = m.groups()
            content = self._http_get_google_font(url, expect_binary=True)
            if content is None:
                return statement
            name = urlsplit(url).path.lstrip("/").replace("/", "-")
            attachment = IrAttachment.create(
                {
                    "name": f"google-font-{name}",
                    "type": "binary",
                    "datas": base64.b64encode(content),
                    "public": True,
                }
            )
            font_family_attachments += attachment
            return "src: url(/web/content/%s/%s) %s" % (
                attachment.id,
                name,
                font_format,
            )

        font_content = re.sub(r"src: url\(.+\)", replace_src, font_content)
        attach_font = IrAttachment.create(
            {
                "name": f"{font_name} (google-font)",
                "type": "binary",
                "datas": base64.encodebytes(font_content.encode()),
                "mimetype": "text/css",
                "public": True,
            }
        )
        if font_family_attachments:
            font_family_attachments.original_id = attach_font.id
        _debug.lifecycle(
            "google_font_attached",
            font=font_name,
            attachment=attach_font.id,
            sources=source_count,
        )
        return attach_font.id

    def _http_get_google_font(self, url, *, expect_binary):
        try:
            with _debug.perf("google_font_requested", binary=expect_binary) as span:
                with self.env["ir.egress"].request(
                    "GET",
                    url,
                    purpose="google_fonts",
                    timeout=_GOOGLE_FONT_TIMEOUT,
                    headers=_GOOGLE_FONT_HEADERS,
                    stream=True,
                ) as response:
                    span.set(status=getattr(response, "status_code", None))
                    response.raise_for_status()
                    if expect_binary and not self._is_font_content_type(response, url):
                        return None
                    chunks = []
                    total = 0
                    for chunk in response.iter_content(64 * 1024):
                        total += len(chunk)
                        if total > _MAX_GOOGLE_FONT_BYTES:
                            _logger.warning(
                                "Google Fonts resource exceeds %s bytes: %s",
                                _MAX_GOOGLE_FONT_BYTES,
                                url,
                            )
                            _debug.logic(
                                "google_font_refused",
                                reason="too_large",
                                bytes=total,
                            )
                            return None
                        chunks.append(chunk)
                    span.set(bytes=total)
                    return b"".join(chunks)
        except requests.RequestException:
            _logger.warning("Google Fonts request failed: %s", url)
            _debug.logic("google_font_refused", reason="request_failed", url=url)
            return None

    def _is_font_content_type(self, response, url) -> bool:
        content_type = response.headers.get("content-type", "").lower()
        if any(token in content_type for token in ("font", "woff", "octet-stream")):
            return True
        _logger.warning(
            "Unexpected content-type %r for Google font %s", content_type, url
        )
        _debug.logic(
            "google_font_refused", reason="content_type", content_type=content_type
        )
        return False

    @api.model
    def _get_custom_attachment(self, custom_url, op="="):
        assert op in ("in", "="), "Invalid operator"
        if self.env.user.has_group("website.group_website_designer"):
            self = self.sudo()
        website = self.env["website"].get_current_website()
        res = self.env["ir.attachment"].search([("url", op, custom_url)])
        _debug.perf.count("custom_attachments", website=website.id, found=len(res))
        return res.with_context(website_id=website.id).filtered(
            lambda x: x.website_id == website
        )

    @api.model
    def _get_custom_asset(self, custom_url):
        website = self.env["website"].get_current_website()
        url = custom_url[1:] if custom_url.startswith(("/", "\\")) else custom_url
        res = self.env["ir.asset"].search([("path", "like", escape_psql(url))])
        return res.with_context(website_id=website.id)._filtered_most_specific()

    @api.model
    def _add_website_id(self, values):
        website = self.env["website"].get_current_website()
        values["website_id"] = website.id
        return values
