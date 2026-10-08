import base64
import hashlib
import io
import logging
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from werkzeug.utils import send_file

import odoo
from odoo import api, http
from odoo.exceptions import AccessError, UserError
from odoo.http import BadRequest, Response, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.filesystem import guess_mimetype
from odoo.libs.json import loads as json_loads
from odoo.tools import file_open, file_path, replace_exceptions, str2bool
from odoo.tools.assets.constants import ANY_UNIQUE
from odoo.tools.image import image_guess_size_from_field_name
from odoo.tools.misc import is_valid_limited_field_access_token

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

BAD_X_SENDFILE_ERROR = """\
Odoo is running with --x-sendfile but is receiving /web/filestore requests.

With --x-sendfile enabled, NGINX should be serving the
/web/filestore route, however Odoo is receiving the
request.

This usually indicates that NGINX is badly configured,
please make sure the /web/filestore location block exists
in your configuration file and that it is similar to:

    location /web/filestore {{
        internal;
        alias {data_dir}/filestore;
    }}
"""


def clean(name: str) -> str:
    return name.replace("<", "").replace(">", "")


def _get_int_or_zero(value) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return 0


def _resolve_res_id(value) -> int | None:
    if value is None or value is False or value == "":
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _vary_on_encoding(response: Response) -> Response:
    # an asset answers in the encoding the request accepts, so a cache keys
    # it by Accept-Encoding as well
    response.headers.add("Vary", "Accept-Encoding")
    return response


def _get_send_file_kwargs(unique, download, nocache) -> dict[str, Any]:
    send_file_kwargs: dict[str, Any] = {"as_attachment": str2bool(download, False)}
    if unique:
        send_file_kwargs["immutable"] = True
        send_file_kwargs["max_age"] = http.STATIC_CACHE_LONG
    if str2bool(nocache, False):
        send_file_kwargs["max_age"] = None
    return send_file_kwargs


def _get_static_image_response(name: str) -> Response:
    return http.Stream.from_path(file_path(f"web/static/img/{name}")).prepare_response()


def _is_public_access_token_valid(record, field, access_token) -> bool:
    if not access_token:
        return False
    valid = bool(
        is_valid_limited_field_access_token(record, field, access_token, scope="binary")
    )
    _debug.logic("limited_access_token", record=record, field=field, valid=valid)
    return valid


@contextmanager
def _locked_rw_env(env: api.Environment, lock_key: str) -> Iterator[api.Environment]:
    if env.cr.readonly:
        _debug.logic("lock_readonly_cursor_rollback", lock_key=lock_key)
        env.cr.rollback()
    # Always use a fresh cursor: the request cursor has already queried and
    # cannot change its isolation level before waiting for the lock.
    with env.registry.cursor(readonly=False) as rw_cr:
        # Read under the lock what the previous generator committed.
        rw_cr.use_read_committed()
        digest = hashlib.blake2b(lock_key.encode(), digest_size=8).digest()
        with _debug.perf("lock_advisory_wait", lock_key=lock_key):
            rw_cr.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (int.from_bytes(digest, "big", signed=True),),
            )
        yield api.Environment(rw_cr, env.user.id, {})


class Binary(http.Controller):
    @http.route("/web/filestore/<path:_path>", type="http", auth="none")
    def content_filestore(self, _path: str) -> Response:
        _debug.lifecycle(
            "filestore_not_found", x_sendfile=bool(odoo.tools.config["x_sendfile"])
        )
        if odoo.tools.config["x_sendfile"]:
            _logger.error(
                BAD_X_SENDFILE_ERROR.format(data_dir=odoo.tools.config["data_dir"])
            )
        raise http.request.prepare_not_found_error()

    @http.route(
        [
            "/web/content",
            "/web/content/<string:xmlid>",
            "/web/content/<string:xmlid>/<string:filename>",
            "/web/content/<int:id>",
            "/web/content/<int:id>/<string:filename>",
            "/web/content/<string:model>/<int:id>/<string:field>",
            "/web/content/<string:model>/<int:id>/<string:field>/<string:filename>",
        ],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_common(  # noqa: E8539  content: an attachment's own token or ownership token
        self,
        xmlid: str | None = None,
        model: str = "ir.attachment",
        id: int | str | None = None,
        field: str = "raw",
        filename: str | None = None,
        filename_field: str = "name",
        mimetype: str | None = None,
        unique: str | bool = False,
        download: str | bool = False,
        access_token: str | None = None,
        nocache: str | bool = False,
    ) -> Response:
        _debug.lifecycle(
            "content",
            model=model,
            id=id,
            field=field,
            xmlid=xmlid,
            filename=filename,
            unique=unique,
            download=download,
            nocache=nocache,
            token=bool(access_token),
        )
        with replace_exceptions(UserError, by=request.prepare_not_found_error()):
            with _debug.perf(
                "content_resolve", cr=request.env.cr, model=model, id=id, field=field
            ):
                record = request.env["ir.binary"]._get_record(
                    xmlid, model, _resolve_res_id(id), access_token, field_name=field
                )
                stream = request.env["ir.binary"]._get_stream_from_record(
                    record, field, filename, filename_field, mimetype
                )
            if _is_public_access_token_valid(record, field, access_token):
                stream.public = True
        _debug.pipeline(
            "content_stream",
            record=record,
            field=field,
            stream_type=stream.type,
            size=stream.size,
            mimetype=stream.mimetype,
            public=stream.public,
        )

        send_file_kwargs = _get_send_file_kwargs(unique, download, nocache)
        _debug.logic(
            "content_send_file",
            model=model,
            id=id,
            field=field,
            send_file=send_file_kwargs,
        )

        return stream.prepare_response(**send_file_kwargs)

    @http.route(
        ["/web/assets/scope/<string:scope>/<string:unique>/<string:filename>"],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_assets_scoped(
        self,
        scope: str,
        unique: str,
        filename: str,
        nocache: str | bool = False,
    ) -> Response:
        return self.content_assets(
            filename,
            unique=unique,
            nocache=nocache,
            assets_params=self._unit_test_scope_params(scope, filename),
        )

    def _unit_test_scope_params(
        self, scope: str, filename: str | None
    ) -> dict[str, Any]:
        if scope not in request.env["ir.asset"]._get_addons_installed():
            _debug.logic("asset_scope_not_installed", filename=filename, scope=scope)
            raise request.prepare_not_found_error()
        _debug.pipeline("asset_scoped", filename=filename, scope=scope)
        return {"unit_test_scope": scope}

    @http.route(
        ["/web/assets/<string:unique>/<string:filename>"],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_assets(
        self,
        filename: str,
        unique: str = ANY_UNIQUE,
        nocache: str | bool = False,
        assets_params: dict[str, Any] | None = None,
    ) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "asset_requested",
                filename=filename,
                unique=unique,
                nocache=nocache,
                params=sorted(assets_params)
                if isinstance(assets_params, dict)
                else assets_params,
            )
        if filename.endswith(".map") and not self._source_map_published():
            _debug.logic("asset_source_map_withheld", filename=filename)
            raise request.prepare_not_found_error()
        env = request.env
        assets_params = assets_params or {}
        if not isinstance(assets_params, dict):
            _debug.logic("asset_params_not_dict", filename=filename)
            raise request.prepare_not_found_error()
        debug_assets = unique == "debug"
        stream = None
        persisted = True
        if unique in ("any", "%"):
            unique = ANY_UNIQUE
        if not debug_assets:
            url = env["ir.asset"]._get_asset_bundle_url_pattern(
                filename, unique, assets_params
            )
            if "%" in url:
                _debug.logic("asset_url_pattern_unresolved", filename=filename)
                raise request.prepare_not_found_error()
            with _debug.perf("asset_attachment_lookup", cr=env.cr, filename=filename):
                attachment = env["ir.attachment"]._search_generated_assets(
                    url_pattern=url, limit=1
                )
            _debug.logic(
                "asset_cached_attachment",
                filename=filename,
                attachment=attachment.id if attachment else "miss",
            )
            if attachment:
                stream = attachment._get_asset_stream(
                    filename, request.httprequest.accept_encodings
                )
        if stream is None:
            _debug.pipeline(
                "asset_generate", filename=filename, debug_assets=debug_assets
            )
            stream, redirect, persisted = self._get_generated_asset_stream(
                filename,
                unique,
                debug_assets,
                assets_params,
                request.httprequest.accept_encodings,
            )
            if redirect is not None:
                _debug.pipeline("asset_version_mismatch_redirect", filename=filename)
                return redirect
        if stream is None:
            _debug.logic("asset_no_stream_after_generation", filename=filename)
            raise request.prepare_not_found_error()
        if stream.type == "url":
            _debug.logic("asset_url_stream_blanked", filename=filename)
            stream.type = "data"
            stream.data = b""
            stream.size = 0
            stream.url = None
        _debug.perf.count(
            "asset_stream", filename=filename, stream_type=stream.type, size=stream.size
        )
        send_file_kwargs: dict[str, Any] = {
            "as_attachment": False,
            "content_security_policy": None,
        }
        if str2bool(nocache, False) or not persisted or unique == ANY_UNIQUE:
            # an asset built but not saved (a stylesheet's error banner) is
            # served once: the next request builds again once the fault clears;
            # an "any" URL names whichever version is current, so it must not
            # outlive that version in a cache
            send_file_kwargs["max_age"] = None
        elif not debug_assets:
            send_file_kwargs["immutable"] = True
            send_file_kwargs["max_age"] = http.STATIC_CACHE_LONG

        return _vary_on_encoding(stream.prepare_response(**send_file_kwargs))

    def _get_generated_asset_stream(
        self,
        filename: str,
        unique: str,
        debug_assets: bool,
        assets_params: dict[str, Any],
        accept_encodings: Any = None,
    ) -> tuple[Any, Response | None, bool]:
        if filename.endswith(".map"):
            _logger.error(
                ".map should have been generated through debug assets, (version %s most likely outdated)",
                unique,
            )
            raise request.prepare_not_found_error()
        stream = None
        with _locked_rw_env(request.env, filename) as rw_env:
            try:
                bundle_name, rtl, asset_type, autoprefix = rw_env[
                    "ir.asset"
                ]._parse_bundle_name(filename, debug_assets)
                css = asset_type == "css"
                js = asset_type == "js"
                _debug.pipeline(
                    "asset_generate_bundle",
                    filename=filename,
                    bundle=bundle_name,
                    asset_type=asset_type,
                    rtl=rtl,
                    autoprefix=autoprefix,
                )
                with _debug.perf(
                    "asset_generate_build_bundle", cr=rw_env.cr, filename=filename
                ):
                    bundle = rw_env["ir.qweb"]._get_asset_bundle(
                        bundle_name,
                        css=css,
                        js=js,
                        debug_assets=debug_assets,
                        rtl=rtl,
                        autoprefix=autoprefix,
                        assets_params=assets_params,
                    )
                if (
                    not debug_assets
                    and unique != ANY_UNIQUE
                    and unique != bundle.get_version(asset_type)
                ):
                    _debug.logic(
                        "asset_generate_version_mismatch",
                        filename=filename,
                        requested=unique,
                        current=bundle.get_version(asset_type),
                    )
                    return None, request.redirect(bundle.get_link(asset_type)), True
                attachment = None
                with _debug.perf(
                    "asset_generate_attachment",
                    cr=rw_env.cr,
                    filename=filename,
                    asset_type=asset_type,
                ):
                    if css:
                        attachment = bundle.css()
                    elif js:
                        attachment = bundle.js()
                _debug.logic(
                    "asset_generate_attachment_result",
                    filename=filename,
                    attachment=attachment.id if attachment else None,
                )
                if attachment:
                    stream = attachment._get_asset_stream(filename, accept_encodings)
                    if not attachment.id:
                        _debug.logic(
                            "asset_generate_unsaved_attachment", filename=filename
                        )
                        return stream, None, False
            except ValueError as e:
                _debug.logic("asset_bundle_name_unparsable", filename=filename)
                _logger.warning("Parsing asset bundle %s has failed: %s", filename, e)
                raise request.prepare_not_found_error() from e
        return stream, None, True

    @http.route(
        ["/web/assets/esm/<string:unique>/<string:filename>"],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_esm_assets(self, unique: str, filename: str) -> Response:
        if filename.endswith(".map") and not self._source_map_published():
            _debug.logic("esm_source_map_withheld", filename=filename)
            raise request.prepare_not_found_error()
        return self._serve_generated_esm(f"/web/assets/esm/{unique}/{filename}")

    @staticmethod
    def _source_map_published() -> bool:
        # an "external" map carries every bundled source, comments included:
        # it is written for the server's own use and for administrators, and
        # only "linked" hands it to whoever loads the bundle
        env = request.env
        mode = env.registry.settings.get(env, "web.esbuild.source_maps", "")
        return mode == "linked" or env.user._is_system()

    @http.route(
        ["/web/assets/lib/<string:unique>/<path:path>"],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_esm_lib(self, unique: str, path: str) -> Response:
        return self._serve_generated_esm(f"/web/assets/lib/{unique}/{path}")

    @http.route(
        "/web/assets/owl/<string:checksum>/<string:lang>/"
        "<string:translations_hash>/<string:filename>",
        type="http",
        auth="public",
        readonly=True,
    )
    def content_precompiled_templates(
        self,
        checksum: str,
        lang: str,
        translations_hash: str,
        filename: str,
        assets_params: str | None = None,
    ) -> Response:
        if not filename.endswith(".js"):
            raise request.prepare_not_found_error()
        bundle = filename.removesuffix(".js")
        dev = bundle.endswith(".dev")
        bundle = bundle.removesuffix(".dev")
        params = None
        if assets_params:
            try:
                params = json_loads(assets_params)
            except ValueError:
                raise request.prepare_not_found_error() from None
            if not isinstance(params, dict) or not all(
                isinstance(key, str) and isinstance(value, str | int | bool)
                for key, value in params.items()
            ):
                raise request.prepare_not_found_error()
        args = (bundle, checksum, lang, translations_hash)
        env = request.env
        attachment = env["ir.qweb"]._get_or_create_precompiled_template_attachment(
            *args, dev=dev, build=False
        )
        if not attachment:
            url = env["ir.qweb"]._get_precompiled_templates_url(*args, dev=dev)
            with _locked_rw_env(env, url) as rw_env:
                attachment = rw_env[
                    "ir.qweb"
                ]._get_or_create_precompiled_template_attachment(
                    *args, dev=dev, assets_params=params
                )
                if not attachment:
                    raise request.prepare_not_found_error()
                stream = attachment._get_asset_stream(
                    filename, request.httprequest.accept_encodings
                )
        else:
            stream = attachment._get_asset_stream(
                filename, request.httprequest.accept_encodings
            )
        return _vary_on_encoding(
            stream.prepare_response(
                as_attachment=False,
                content_security_policy=None,
                immutable=True,
                max_age=http.STATIC_CACHE_LONG,
            )
        )

    @staticmethod
    def _serve_generated_esm(url: str) -> Response:
        _debug.lifecycle("esm", url=url)
        with _debug.perf("esm_attachment_lookup", cr=request.env.cr, url=url):
            stream = request.env["ir.qweb"]._get_generated_esm_stream(
                url, request.httprequest.accept_encodings
            )
        if stream is None:
            _debug.logic("esm_no_generated_attachment", url=url)
            raise request.prepare_not_found_error()
        _debug.pipeline("esm_stream", url=url, size=stream.size)
        return _vary_on_encoding(
            stream.prepare_response(
                as_attachment=False,
                content_security_policy=None,
                immutable=True,
                max_age=http.STATIC_CACHE_LONG,
            )
        )

    @http.route(
        [
            "/web/image",
            "/web/image/<string:xmlid>",
            "/web/image/<string:xmlid>/<string:filename>",
            "/web/image/<string:xmlid>/<int:width>x<int:height>",
            "/web/image/<string:xmlid>/<int:width>x<int:height>/<string:filename>",
            "/web/image/<string:model>/<int:id>/<string:field>",
            "/web/image/<string:model>/<int:id>/<string:field>/<string:filename>",
            "/web/image/<string:model>/<int:id>/<string:field>/<int:width>x<int:height>",
            "/web/image/<string:model>/<int:id>/<string:field>/<int:width>x<int:height>/<string:filename>",
            "/web/image/<int:id>",
            "/web/image/<int:id>/<string:filename>",
            "/web/image/<int:id>/<int:width>x<int:height>",
            "/web/image/<int:id>/<int:width>x<int:height>/<string:filename>",
            "/web/image/<int:id>-<string:unique>",
            "/web/image/<int:id>-<string:unique>/<string:filename>",
            "/web/image/<int:id>-<string:unique>/<int:width>x<int:height>",
            "/web/image/<int:id>-<string:unique>/<int:width>x<int:height>/<string:filename>",
        ],
        type="http",
        auth="public",
        readonly=True,
        save_session=False,
    )
    def content_image(  # noqa: E8539  content: an attachment's own token or ownership token
        self,
        xmlid: str | None = None,
        model: str = "ir.attachment",
        id: int | str | None = None,
        field: str = "raw",
        filename_field: str = "name",
        filename: str | None = None,
        mimetype: str | None = None,
        unique: str | bool = False,
        download: str | bool = False,
        width: int | str = 0,
        height: int | str = 0,
        crop: str | bool = False,
        access_token: str | None = None,
        nocache: str | bool = False,
    ) -> Response:
        crop = str2bool(crop, False)
        width = _get_int_or_zero(width)
        height = _get_int_or_zero(height)
        _debug.lifecycle(
            "image",
            model=model,
            id=id,
            field=field,
            xmlid=xmlid,
            width=width,
            height=height,
            crop=crop,
            unique=unique,
            download=download,
            token=bool(access_token),
        )
        try:
            with _debug.perf(
                "image_resolve", cr=request.env.cr, model=model, id=id, field=field
            ):
                record = request.env["ir.binary"]._get_record(
                    xmlid, model, _resolve_res_id(id), access_token, field_name=field
                )
                stream = request.env["ir.binary"]._get_stream_image_from_record(
                    record,
                    field,
                    filename=filename,
                    filename_field=filename_field,
                    mimetype=mimetype,
                    width=width,
                    height=height,
                    crop=crop,
                )
            if _is_public_access_token_valid(record, field, access_token):
                stream.public = True
            _debug.pipeline(
                "image_stream",
                record=record,
                field=field,
                stream_type=stream.type,
                size=stream.size,
                mimetype=stream.mimetype,
            )
        except UserError as exc:
            if str2bool(download, False):
                _debug.logic(
                    "image_unavailable_download_not_found",
                    model=model,
                    id=id,
                    field=field,
                    error=type(exc).__name__,
                )
                raise request.prepare_not_found_error() from exc
            if (width, height) == (0, 0):
                width, height = image_guess_size_from_field_name(field)
            _debug.logic(
                "image_unavailable_placeholder",
                model=model,
                id=id,
                field=field,
                error=type(exc).__name__,
                width=width,
                height=height,
            )
            record = request.env.ref("web.image_placeholder").sudo()
            stream = request.env["ir.binary"]._get_stream_image_from_record(
                record,
                "raw",
                width=width,
                height=height,
                crop=crop,
            )
            stream.public = False

        return stream.prepare_response(
            **_get_send_file_kwargs(unique, download, nocache)
        )

    @http.route("/web/binary/upload_attachment", type="http", auth="user")
    def upload_attachment(
        self,
        model: str,
        id: int | str,
        ufile: Any,
    ) -> Response:
        files = request.httprequest.files.getlist("ufile")
        _debug.lifecycle("upload", model=model, id=id, files=len(files))
        try:
            res_id = int(id)
        except ValueError:
            _debug.logic("upload_record_id_unparsable", model=model, id=id)
            raise BadRequest(f"Invalid record id {id!r}") from None
        Attachment = request.env["ir.attachment"]
        normalize_name = request.httprequest.user_agent.browser == "safari"
        results = []
        for uploaded_file in files:
            filename = uploaded_file.filename
            if normalize_name:
                _debug.logic("upload_safari_nfd_normalize", model=model, id=id)
                filename = unicodedata.normalize("NFD", uploaded_file.filename)

            try:
                uploaded_file.filename = filename
                with (
                    _debug.perf(
                        "upload_create",
                        cr=request.env.cr,
                        model=model,
                        id=id,
                        filename=filename,
                    ),
                    request.env.cr.savepoint(),
                ):
                    attachment = Attachment._create_from_request_file(
                        uploaded_file,
                        res_model=model,
                        res_id=res_id,
                    )
                    attachment._post_add_create()
            except AccessError:
                _debug.logic(
                    "upload_access_denied", model=model, id=id, filename=filename
                )
                results.append(
                    {
                        "error": request.env._(
                            "You are not allowed to upload an attachment here."
                        )
                    }
                )
            except Exception:
                _debug.logic(
                    "upload_unexpected_failure", model=model, id=id, filename=filename
                )
                results.append({"error": request.env._("Something horrible happened")})
                _logger.exception(
                    "Fail to upload attachment %s", uploaded_file.filename
                )
            else:
                _debug.lifecycle(
                    "upload_attachment_created",
                    model=model,
                    id=id,
                    filename=filename,
                    attachment=attachment.id,
                    mimetype=attachment.mimetype,
                    size=attachment.file_size,
                )
                results.append(
                    {
                        "filename": clean(filename),
                        "mimetype": attachment.mimetype,
                        "id": attachment.id,
                        "size": attachment.file_size,
                    }
                )
        return request.prepare_json_response(results)

    @http.route(
        [
            "/web/binary/company_logo",
            "/logo",
            "/logo.png",
        ],
        type="http",
        auth="none",
        cors="*",
        readonly=True,
    )
    def company_logo(self, **kw: Any) -> Response:
        dbname = request.db
        uid = (request.session.uid if dbname else None) or odoo.SUPERUSER_ID
        _debug.lifecycle("logo", company=kw.get("company"), uid=uid)

        if not dbname:
            _debug.logic("logo_no_db_static")
            response = _get_static_image_response("logo.png")
        else:
            try:
                try:
                    company = int(kw["company"]) if kw.get("company") else False
                except ValueError, TypeError:
                    company = False
                _debug.logic(
                    "logo_lookup",
                    by="company" if company else "uid",
                    company=company,
                    uid=uid,
                )
                if company:
                    request.env.cr.execute(
                        """
                        SELECT logo_web, write_date
                          FROM res_company
                         WHERE id = %s
                    """,
                        (company,),
                    )
                else:
                    request.env.cr.execute(
                        """
                        SELECT c.logo_web, c.write_date
                          FROM res_users u
                     LEFT JOIN res_company c
                            ON c.id = u.company_id
                         WHERE u.id = %s
                    """,
                        (uid,),
                    )
                row = request.env.cr.fetchone()
                if row and row[0]:
                    image_base64 = base64.b64decode(row[0])
                    image_data = io.BytesIO(image_base64)
                    mimetype = guess_mimetype(image_base64, default="image/png")
                    imgext = "." + mimetype.split("/")[1]
                    if imgext == ".svg+xml":
                        imgext = ".svg"
                    _debug.pipeline(
                        "logo_company",
                        mimetype=mimetype,
                        size=len(image_base64),
                        modified=row[1],
                    )
                    response = send_file(
                        image_data,
                        request.httprequest.environ,
                        download_name=f"logo{imgext}",
                        mimetype=mimetype,
                        last_modified=row[1],
                        response_class=Response,
                    )
                else:
                    _debug.logic("logo_missing_nologo")
                    response = _get_static_image_response("nologo.png")
            except Exception as exc:
                _debug.logic("logo_lookup_failed", error=type(exc).__name__)
                _logger.warning(
                    "While retrieving the company logo, using the Odoo logo instead",
                    exc_info=True,
                )
                response = _get_static_image_response("logo.png")

        return response

    @http.route(
        [
            "/web/sign/get_fonts",
            "/web/sign/get_fonts/<string:fontname>",
        ],
        type="jsonrpc",
        auth="none",
        readonly=True,
    )
    def get_fonts(self, fontname: str | None = None) -> list[bytes]:
        supported_exts = (".ttf", ".otf", ".woff", ".woff2")
        fonts_dir = Path(file_path("web/static/fonts/sign"))
        _debug.lifecycle("fonts", fontname=fontname)
        if fontname:
            if Path(fontname).name != fontname:
                _debug.logic("fonts_name_not_bare", fontname=fontname)
                raise request.prepare_not_found_error()
            font_filenames = [fontname]
        else:
            font_filenames = sorted(
                fn.name for fn in fonts_dir.iterdir() if fn.suffix in supported_exts
            )
        fonts = []
        for filename in font_filenames:
            try:
                with file_open(
                    str(fonts_dir / filename), "rb", filter_ext=supported_exts
                ) as font_file:
                    fonts.append(base64.b64encode(font_file.read()))
            except FileNotFoundError, ValueError:
                _debug.logic("fonts_not_sign_font", filename=filename)
                raise request.prepare_not_found_error() from None
        if _debug.perf.enabled:
            _debug.perf.count("fonts_size", fonts=len(fonts), size=sum(map(len, fonts)))
        return fonts
