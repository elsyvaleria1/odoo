import hashlib
import json
import logging
from http import HTTPStatus

from werkzeug.exceptions import NotFound
from werkzeug.http import is_resource_modified, parse_cache_control_header

from odoo import http
from odoo.exceptions import AccessError, ConcurrencyError
from odoo.http import request
from odoo.tools import (
    SQL,
    hmac,
    json_default,
    py_to_js_locale,
    register_signed_scope,
)

from ..tools.cache import (
    doc_cache_generation,
    index_attachment_name,
    stale_index_domain,
)
from ..tools.registry import describe_method, describe_model_doc, public_method_names

logger = logging.getLogger(__name__)

DOC_ETAG_SCOPE = register_signed_scope(
    "rpc.doc_etag",
    purpose="the ETag of a /doc document, so a client revalidates what it cached",
    lifetime="undated: it changes with the database generation, the language "
    "and the reader's groups",
)


class DocController(http.Controller):
    @http.route("/doc-bearer/index.json", type="json2", auth="bearer", typed=True)
    def doc_bearer_index(self):
        return self.doc_index()

    @http.route("/doc/index.json", type="json2", auth="user", typed=True)
    def doc_index(self):
        self._check_doc_access()

        generation = doc_cache_generation(self.env)
        unique = self._doc_cache_key("/doc/index.json", generation)
        use_cache = self._client_accepts_cache()
        if use_cache and not is_resource_modified(
            request.httprequest.environ, etag=unique
        ):
            return request.prepare_response("", status=HTTPStatus.NOT_MODIFIED)

        filename = index_attachment_name(generation, unique)
        index_attach = (
            self.env["ir.attachment"].sudo().search([("name", "=", filename)], limit=1)
        )
        if not index_attach or not use_cache:
            index_attach = self._doc_index_cache(
                filename, generation, refresh=not use_cache
            )

        response = index_attach._to_http_stream().prepare_response(etag=unique)
        response.headers["Content-Language"] = py_to_js_locale(self.env.lang)
        return response

    @http.route(
        "/doc-bearer/<model_name>.json",
        type="json2",
        auth="bearer",
        readonly=True,
        typed=True,
    )
    def doc_bearer_model(self, model_name: str):
        return self.doc_model(model_name)

    @http.route(
        "/doc/<model_name>.json", type="json2", auth="user", readonly=True, typed=True
    )
    def doc_model(self, model_name: str):
        self._check_doc_access()
        if model_name not in self.env:
            raise NotFound

        Model = self.env[model_name]
        Model.check_access("read")
        ir_model = self.env["ir.model"]._get(model_name)

        unique = self._doc_cache_key(
            "/doc/<model_name>.json", doc_cache_generation(self.env)
        )
        use_cache = self._client_accepts_cache()
        if use_cache and not is_resource_modified(
            request.httprequest.environ, etag=unique
        ):
            return request.prepare_response("", status=HTTPStatus.NOT_MODIFIED)

        result = {
            "model": model_name,
            "name": ir_model.name,
            "doc": describe_model_doc(Model),
            "fields": {
                field["name"]: dict(
                    field,
                    module=next(iter(Model._fields[field["name"]]._modules), None),
                )
                for field in Model.fields_get().values()
            },
            "methods": {
                method_name: describe_method(Model, method_name)
                for method_name in public_method_names(Model)
            },
        }

        response = request.prepare_json_response(result)
        response.set_etag(unique)
        response.headers["Cache-Control"] = "no-cache, private"
        response.headers["Content-Language"] = py_to_js_locale(self.env.lang)
        return response

    def _check_doc_access(self):
        if not self.env.user.has_group("rpc.group_allow_doc"):
            raise AccessError(
                self.env._(
                    "This page is only accessible to %s users.",
                    self.env.ref("rpc.group_allow_doc").sudo().name,
                )
            )

    def _doc_cache_key(self, route, generation):
        return hmac(
            self.env(su=True),
            scope=DOC_ETAG_SCOPE,
            message=(
                route,
                generation,
                self.env.lang,
                sorted(self.env.user.all_group_ids.ids),
            ),
        )

    def _client_accepts_cache(self):
        cache_control = parse_cache_control_header(
            request.httprequest.headers.get("Cache-Control")
        )
        return not cache_control.no_cache

    def _doc_index_cache(self, filename, generation, refresh):
        digest = hashlib.blake2b(filename.encode(), digest_size=8).digest()
        self.env.cr.execute(
            SQL(
                "SELECT pg_advisory_xact_lock(%s)",
                int.from_bytes(digest, "big", signed=True),
            )
        )

        Attachment = self.env["ir.attachment"].sudo()
        index_attach = Attachment.search([("name", "=", filename)], limit=1)
        if index_attach and not refresh:
            return index_attach
        if not index_attach and self._is_doc_index_committed(filename):
            raise ConcurrencyError(f"{filename} was built by a concurrent request")

        payload = json.dumps(
            {"models": self._doc_index()},
            ensure_ascii=False,
            default=json_default,
        )
        if index_attach:
            index_attach.raw = payload
            logger.info("refreshed index attachment: %s", filename)
        else:
            index_attach = Attachment.create(
                {
                    "name": filename,
                    "description": (
                        "Generated /doc/index.json document.\n\n"
                        f"Lang: {self.env.lang}\n"
                        f"Groups: {sorted(self.env.user.all_group_ids.ids)}"
                    ),
                    "mimetype": "application/json",
                    "raw": payload,
                    "public": False,
                }
            )
            logger.info("new index attachment: %s", filename)

        superseded = Attachment.search(stale_index_domain(generation))
        if superseded:
            superseded.unlink()
            logger.info(
                "dropped %s superseded /doc index attachment(s)", len(superseded)
            )
        return index_attach

    def _is_doc_index_committed(self, filename) -> bool:
        with self.env.registry.cursor() as cr:
            cr.use_read_committed()
            cr.execute(
                SQL("SELECT 1 FROM ir_attachment WHERE name = %s LIMIT 1", filename)
            )
            return cr.fetchone() is not None

    def _doc_index(self):
        return [
            {
                "model": ir_model.model,
                "name": ir_model.name,
                "fields": {
                    field.name: {"string": field.field_description}
                    for field in ir_model.field_id
                    if (python_field := Model._fields.get(field.name)) is not None
                    and Model._has_field_access(python_field, "read")
                },
                "methods": public_method_names(Model),
            }
            for ir_model in self.env["ir.model"].sudo().search([])
            if ir_model.model in self.env
            if (Model := self.env[ir_model.model]).has_access("read")
        ]
