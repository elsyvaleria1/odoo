import base64
import contextlib
import functools
import io
import logging
import mimetypes
import os
import re
import time
import uuid
from collections import defaultdict
from itertools import batched
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import psycopg.errors

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import (
    AccessError,
    UserError,
    ValidationError,
)
from odoo.fields import Domain
from odoo.http import Stream, request, root
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import (
    CHEAP,
    CUES,
    METERED,
    TEXT,
    Document,
    cues_as_text,
    fix_filename_extension,
)
from odoo.libs.field_class_names import PER_RECORD
from odoo.libs.filesystem import (
    MIMETYPE_HEAD_SIZE,
    OLECF_MIMETYPES,
    guess_mimetype,
)
from odoo.libs.hashing import (
    ALGO_TAG,
    CONTENT_DIGEST_LEN,
    CONTENT_DIGEST_MAX_LEN,
    content_hash,
    prepare_content_hasher,
)
from odoo.tools import (
    SQL,
    OrderedSet,
    config,
    file_open,
    image,
    str2bool,
)
from odoo.tools.access_scan import get_inaccessible_owners
from odoo.tools.misc import limited_field_access_token
from odoo.tools.owner_reach import owner_reach, pinned_values, search_by_owner

from odoo.addons.base.models.ir_attachment_reading import (
    PERSISTED as PERSISTED_READINGS,
)
from odoo.addons.base.models.ir_attachment_storage import (
    STORAGE_BACKENDS,
    AttachmentStorage,
    FileStorage,
    backend_for_key,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Generator, Iterator

    from odoo.tools.query import Query

    from odoo.addons.base.models.ir_attachment_reading import IrAttachmentReading

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
type ContentMemo = dict[tuple[str, str, bool], tuple[bytes, dict[str, Any]]]
SECURITY_FIELDS = ("res_model", "res_id", "create_uid", "public", "res_field")
READING_JOB_CHANNEL = "reading"

_INDEX_WORD_RE = re.compile(r"[^\x00-\x1f\x7f-\x9f]{4,}")

BIN_SIZE_KEYS = {
    "bin_size": False,
    "bin_size_raw": False,
    "bin_size_datas": False,
    "bin_size_db_datas": False,
}


_REHASH_CURSOR_PARAM = "ir_attachment.rehash_legacy_keys_after_id"


@functools.cache
def _get_filestore_root(filestore: str) -> str:
    return str(Path(filestore).resolve())


@functools.cache
def _get_filestore_dir_path(filestore: str, name: str) -> Path:
    return Path(filestore, name)


class IrAttachment(models.Model):
    _name = "ir.attachment"
    _inherit = ["mixin.bearer.token"]
    _description = "Attachment"
    _order = "id desc"
    _search_visibility_fields = (
        "res_model",
        "res_id",
        "res_field",
        "public",
        "create_uid",
    )

    name = fields.Char(required=True)
    description = fields.Text()
    res_name = fields.Char(
        string="Resource Name",
        compute="_compute_res_name",
    )
    res_model = fields.Char(string="Resource Model")
    res_field = fields.Char(string="Resource Field")
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Resource ID",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        change_default=True,
    )
    type = fields.Selection(
        selection=[("url", "URL"), ("binary", "File")],
        default="binary",
        change_default=True,
        required=True,
        help="You can either upload a file from your computer or copy/paste an internet link to your file.",
    )
    url = fields.Char(
        size=1024,
        index="btree_not_null",
    )
    public = fields.Boolean(string="Is public document")
    access_token = fields.Char(
        copy=True,
        classification="base.internal",
    )

    db_datas = fields.Binary(
        string="Database Data",
        attachment=False,
    )
    store_fname = fields.Char(
        string="Stored Filename",
        index=True,
        copy=False,
    )
    file_size = fields.Integer(
        copy=False,
        readonly=True,
        bigint=True,
    )
    checksum = fields.Char(
        size=CONTENT_DIGEST_MAX_LEN,
        copy=False,
        readonly=True,
    )
    mimetype = fields.Char(
        string="Mime Type",
        readonly=True,
    )
    index_content = fields.Text(
        string="Indexed Content",
        copy=False,
        readonly=True,
        prefetch=False,
    )
    reading_ids: IrAttachmentReading = fields.One2many(
        comodel_name="ir.attachment.reading",
        inverse_name="attachment_id",
        string="Readings",
        copy=False,
    )
    has_readings = fields.Boolean(
        copy=False,
        readonly=True,
        help="A reading was kept for this file: a copy looks for readings to "
        "share only then.",
    )
    content_expires_at = fields.Datetime(
        index="btree_not_null",
        copy=False,
    )
    content_released_at = fields.Datetime(
        copy=False,
        readonly=True,
    )

    raw = fields.Binary(
        string="File Content (raw)",
        bin_size_field="file_size",
        compute="_compute_raw",
        inverse="_inverse_raw",
    )
    datas = fields.Binary(
        string="File Content (base64)",
        bin_size_field="file_size",
        compute="_compute_datas",
        inverse="_inverse_datas",
    )

    _res_field_idx = models.Index("(res_model, res_field, res_id)")
    _checksum_idx = models.Index("(checksum) WHERE checksum IS NOT NULL")

    _URL_AUDIT_WINDOW = 20

    _INDEX_MAX_BYTES = 4 * 1024 * 1024

    _INDEX_MAX_CHARS = 256 * 1024

    _STREAM_CHUNK_SIZE = 128 * 1024

    _COMPARE_BLOCK_SIZE = 65536

    _FILESTORE_TMP_MAX_AGE = 24 * 3600

    _GC_MAX_ENTRIES = 100_000

    _GC_CHECKLIST_GRACE = 24 * 3600

    def _is_attachment_backed_field(self, field: Any) -> bool:
        return field.type == "binary" or (
            field.relational and field.comodel_name == self._name
        )

    def _check_res_field_valid(self, res_model: str, res_field: str) -> None:
        if not res_model:
            raise ValidationError(
                self.env._(
                    "An attachment standing for the field %(field)s must name "
                    "the model the field belongs to.",
                    field=res_field,
                )
            )
        comodel = self.env.get(self._coerce_model_name(res_model))
        field = comodel._fields.get(res_field) if comodel is not None else None
        if field is None or self._is_attachment_backed_field(field):
            return
        _debug.logic(
            "res_field_refused",
            model=res_model,
            field=res_field,
            reason="not_binary",
        )
        raise ValidationError(
            self.env._(
                "%(field)s of %(model)s cannot be backed by an attachment: "
                "res_field must name a binary field.",
                field=res_field,
                model=res_model,
            )
        )

    def _check_res_field_access(self, res_model: str, res_field: str) -> None:
        if not res_field:
            return
        self._check_res_field_valid(res_model, res_field)
        if self.env.su or self.env.is_system():
            return
        comodel = self.env.get(self._coerce_model_name(res_model))
        field = comodel._fields.get(res_field) if comodel is not None else None
        if field is None or not comodel._has_field_access(field, "write"):
            _debug.logic(
                "res_field_access_refused",
                model=res_model,
                field=res_field,
                uid=self.env.uid,
                reason="missing" if field is None else "no_write_access",
            )
            raise AccessError(
                self.env._("Sorry, you are not allowed to access this document.")
            )

    def _get_res_field_targets(self, vals: dict[str, Any]) -> OrderedSet:
        has_model, has_field = "res_model" in vals, "res_field" in vals
        new_model = self._coerce_model_name(vals["res_model"]) if has_model else None
        if has_model and has_field:
            return OrderedSet([(new_model, vals["res_field"])])
        if has_field:
            return OrderedSet((record.res_model, vals["res_field"]) for record in self)
        if has_model:
            return OrderedSet((new_model, record.res_field) for record in self)
        return OrderedSet()

    @api.model
    def _decode_datas(self, datas: Any) -> bytes:
        try:
            return base64.b64decode(datas or b"")
        except ValueError as exc:
            _debug.logic("datas_decode_refused", reason="not_base64")
            raise UserError(self.env._("Attachment is not encoded in base64.")) from exc

    def _normalize_content_vals(
        self, vals: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        has_content = "raw" in vals or "datas" in vals
        datas = vals.pop("datas", None)
        db_datas = vals.pop("db_datas", None)
        if "raw" in vals:
            raw = vals["raw"] or b""
            vals["raw"] = raw.encode() if isinstance(raw, str) else raw
        elif has_content:
            vals["raw"] = self._decode_datas(datas)
        elif db_datas:
            has_content = True
            vals["raw"] = db_datas.encode() if isinstance(db_datas, str) else db_datas
        for field in ("checksum", "store_fname", "index_content"):
            vals.pop(field, None)
        if has_content:
            vals.pop("file_size", None)
        return vals, has_content

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        vals_list = [dict(vals) for vals in vals_list]

        self.browse().check_access("create")

        model_and_ids = defaultdict(OrderedSet)
        for values in vals_list:
            if res_field := values.get("res_field"):
                self._check_res_field_access(values.get("res_model"), res_field)
            model_and_ids[self._coerce_model_name(values.get("res_model"))].add(
                values.get("res_id")
            )
        if any(get_inaccessible_owners(self.env, model_and_ids, "write")):
            _debug.logic(
                "create_refused",
                uid=self.env.uid,
                models=[m for m in model_and_ids if m],
                reason="comodel_inaccessible",
            )
            raise AccessError(
                self.env._("Sorry, you are not allowed to access this document.")
            )

        backend = self._get_storage_backend()
        verify_collision = self._is_content_collision_check_enabled()
        memo: ContentMemo = {}
        for index, values in enumerate(vals_list):
            values, has_content = self._normalize_content_vals(values)

            values = vals_list[index] = self._prepare_contents(values)
            if has_content:
                raw = values.pop("raw")
                values.update(
                    self._store_content_cached(
                        memo,
                        raw,
                        values["mimetype"],
                        backend,
                        verify_collision=verify_collision,
                        index=self._is_content_index_required(values),
                    )
                )

        _debug.pipeline(
            "create_contents_prepared",
            count=len(vals_list),
            with_content=sum(1 for v in vals_list if "checksum" in v),
        )
        records = super().create(vals_list)
        records._check_serving_attachments()
        _debug.lifecycle(
            "create",
            count=len(records),
            models=[m for m in model_and_ids if m],
            backend=type(backend).__name__,
            memoized=len(memo),
        )
        return records

    def write(self, vals: dict[str, Any]) -> bool:
        if not self:
            _debug.logic("write.skipped", reason="empty_recordset", fields=list(vals))
            return True
        if not self.env.su and ("res_model" in vals or "res_id" in vals):
            model_and_ids = defaultdict(OrderedSet)
            new_model = self._coerce_model_name(vals.get("res_model"))
            if "res_model" in vals and "res_id" in vals:
                model_and_ids[new_model].add(vals["res_id"])
            else:
                for record in self:
                    model_and_ids[
                        new_model if "res_model" in vals else record.res_model
                    ].add(vals.get("res_id", record.res_id))
            if any(get_inaccessible_owners(self.env, model_and_ids, "write")):
                _debug.logic(
                    "write_refused",
                    uid=self.env.uid,
                    count=len(self),
                    reason="comodel_inaccessible",
                )
                raise AccessError(
                    self.env._("Sorry, you are not allowed to access this document.")
                )
        for res_model, res_field in self._get_res_field_targets(vals):
            self._check_res_field_access(res_model, res_field)
        vals, has_content = self._normalize_content_vals(vals)
        if has_content or "mimetype" in vals:
            if "mimetype" not in vals:
                vals["mimetype"] = self._get_mimetype_for_write(vals)
            vals = self._prepare_contents(vals)
        _debug.lifecycle(
            "write", count=len(self), fields=list(vals), has_content=has_content
        )
        res = super().write(vals)
        if not self.env.su and vals.keys() & {"res_model", "res_id", "res_field"}:
            self.sudo().filtered(lambda att: att.res_model and att.res_id).sudo(
                False
            ).check_access("write")
        if "url" in vals or "type" in vals or vals.get("public"):
            self._check_serving_attachments()
        return res

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if not default.keys() & {"datas", "db_datas", "raw"}:
            inlined = 0
            for attachment, vals in zip(
                self._with_bin_size_disabled(), vals_list, strict=True
            ):
                vals.pop("db_datas", None)
                if not attachment.store_fname and (
                    attachment.checksum or attachment.db_datas
                ):
                    vals["raw"] = attachment.raw
                    inlined += 1
            _debug.logic("copy_data", count=len(vals_list), inlined_raw=inlined)
        return vals_list

    def copy(self, default: ValuesType | None = None) -> Self:
        if (default or {}).keys() & {"datas", "db_datas", "raw"}:
            return super().copy(default)
        new_attachments = super(
            IrAttachment, self.with_context(attachment_index_from_origin=True)
        ).copy(default)
        self._share_stored_content(list(self), new_attachments)
        return new_attachments.with_env(self.env)

    def _copy_times(self, times: int, default: ValuesType | None = None) -> list[Self]:
        if not self or times < 1:
            return [self.browse() for _ in range(max(times, 0))]
        if (default or {}).keys() & {"datas", "db_datas", "raw"}:
            return [self.copy(default) for _ in range(times)]
        vals_list = self.with_context(active_test=False).copy_data(default)
        copies = self.with_context(attachment_index_from_origin=True).create(
            [dict(vals) for _ in range(times) for vals in vals_list]
        )
        self._share_stored_content(list(self) * times, copies)
        size = len(self)
        return [
            copies[index * size : (index + 1) * size].with_env(self.env)
            for index in range(times)
        ]

    def _share_stored_content(self, origins: list[Self], copies: Self) -> None:
        by_content: dict[tuple, list[int]] = defaultdict(list)
        for origin, copied in zip(origins, copies, strict=True):
            if origin.store_fname:
                key = (
                    origin.store_fname,
                    origin.checksum,
                    origin.file_size,
                    origin.index_content,
                )
            else:
                key = (None, None, None, origin.index_content)
            by_content[key].append(copied.id)
        for (fname, checksum, size, index), ids in by_content.items():
            values = {"index_content": index}
            if fname:
                values.update(store_fname=fname, checksum=checksum, file_size=size)
            super(IrAttachment, self.browse(ids).sudo()).write(values)
        self._share_readings(origins, copies)
        _debug.lifecycle(
            "copy_shared_content",
            copied=len(copies),
            shared=len(by_content),
        )

    def unlink(self) -> bool:
        to_delete = OrderedSet(
            attach.store_fname for attach in self if attach.store_fname
        )
        _debug.lifecycle("unlink", count=len(self), stored_files=len(to_delete))
        res = super().unlink()
        self._remove_stored_file_multi(to_delete)
        return res

    @api.depends("res_model", "res_id")
    def _compute_res_name(self) -> None:
        to_compute = self.filtered(lambda a: a.res_model and a.res_id)
        (self - to_compute).res_name = False
        for res_model, attachments in to_compute.grouped("res_model").items():
            if res_model not in self.env:
                _debug.logic(
                    "res_name_unknown_model", model=res_model, count=len(attachments)
                )
                for attachment in attachments:
                    attachment.res_name = False
                continue
            res_ids = attachments.mapped("res_id")
            with _debug.perf(
                "res_name_lookup",
                cr=self.env.cr,
                model=res_model,
                count=len(attachments),
            ) as span:
                records = self.env[res_model].browse(res_ids).exists()
                records = records._filtered_access("read")
                name_map = {record.id: record.display_name for record in records}
                span.set(readable=len(name_map))
            for attachment in attachments:
                attachment.res_name = name_map.get(attachment.res_id, False)

    @api.depends("store_fname", "db_datas", "file_size")
    def _compute_datas(self) -> None:
        for attach in self:
            attach.datas = base64.b64encode(attach._with_bin_size_disabled().raw or b"")

    @api.depends("store_fname", "db_datas", "file_size")
    def _compute_raw(self) -> None:
        for attach in self:
            attach.raw = attach._get_stored_content()

    def _inverse_raw(self) -> None:
        self._update_content(lambda a: a.raw or b"")

    def _inverse_datas(self) -> None:
        self._update_content(lambda attach: self._decode_datas(attach.datas))

    @api.model
    def _search(
        self,
        domain: Any,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        *,
        active_test: bool = True,
        bypass_access: bool = False,
    ) -> Query:
        assert not self._active_name, "active name not supported on ir.attachment"
        hide_field_rows = False
        domain = Domain(domain)
        if (
            not self.env.context.get("skip_res_field_check")
            and not any(
                d.field_expr in ("id", "res_field") for d in domain.iter_conditions()
            )
            and not bypass_access
        ):
            hide_field_rows = True
            domain &= Domain("res_field", "=", False)

        domain = domain.optimize(self)
        if self.env.su or bypass_access or domain.is_false():
            _debug.logic(
                "search_unfiltered",
                su=self.env.su,
                bypass_access=bypass_access,
                empty=domain.is_false(),
                res_field_hidden=hide_field_rows,
            )
            return super()._search(
                domain,
                offset,
                limit,
                order,
                active_test=active_test,
                bypass_access=bypass_access,
            )

        sec_domain = self._public_reach()
        res_ids = pinned_values(self, "res_id", domain)
        if not res_ids or False in res_ids:
            unlinked = Domain("res_id", "=", False) | Domain("res_model", "=", False)
            if self.env.is_system():
                sec_domain |= unlinked
            else:
                sec_domain |= unlinked & Domain("create_uid", "=", self.env.uid)

        asked_fields = pinned_values(self, "res_field", domain)
        within = (
            None
            if hide_field_rows or self.env.is_system()
            else functools.partial(self._attached_field_reach, asked=asked_fields)
        )
        itself = self._attached_reach_itself()

        def reached(only: Collection[str] | None, bounded: bool) -> Domain:
            return sec_domain | owner_reach(
                self,
                "res_model",
                "res_id",
                self._attached_record_reach,
                probe=bounded,
                only=only,
                within=within,
                itself=itself,
            )

        _debug.logic(
            "search_by_owner_reach", uid=self.env.uid, res_field_hidden=hide_field_rows
        )
        return search_by_owner(
            self,
            domain,
            offset,
            limit,
            order,
            super()._search,
            reached,
            "res_model",
            active_test=active_test,
        )

    @api.model
    def _attached_reach_itself(self) -> Domain:
        unlinked = Domain("res_id", "=", False) | Domain("res_model", "=", False)
        if not self.env.is_system():
            unlinked &= Domain("create_uid", "=", self.env.uid)
        return self._public_reach() | unlinked

    @api.model
    def _public_reach(self) -> Domain:
        public = Domain("public", "=", True)
        if withheld := self._withheld_source_maps():
            return public & ~withheld
        return public

    @api.model
    def _attached_record_reach(self, Owner: models.BaseModel) -> Domain:
        reach = Owner._record_access_domain("read")
        if Owner._name == "res.users":
            reach |= Domain("id", "=", self.env.uid)
        return reach

    @api.model
    def _attached_field_reach(
        self, Owner: models.BaseModel, asked: Collection[Any] | None = None
    ) -> Domain:
        readable: list[str | bool] = [False]
        per_record = Domain.FALSE
        fields = Owner._fields.values()
        if asked is not None:
            fields = [Owner._fields[name] for name in asked if name in Owner._fields]
        for field in fields:
            if not Owner._has_field_access(field, "read"):
                continue
            field_domain = (
                Owner._field_access_domain(field, "read") if field.attachment else None
            )
            if field_domain is None:
                readable.append(field.name)
                continue
            per_record |= Domain("res_field", "=", field.name) & Domain(
                "res_id",
                "in",
                Owner._search(field_domain, active_test=False, bypass_access=True),
            )
        return Domain("res_field", "in", readable) | per_record

    @api.model
    def _get_storage_backend_for_key(self, fname: str) -> AttachmentStorage:
        return backend_for_key(self.env, fname)

    def _get_content_checksum(self, bin_data: bytes) -> str:
        return content_hash(bin_data or b"")

    @api.model
    def _get_filestore(self) -> str:
        return config.filestore(self.env.cr.dbname)

    @api.model
    def _get_store_key(self, checksum: str) -> str:
        if ALGO_TAG == "s1":
            return checksum[:2] + "/" + checksum
        return f"{ALGO_TAG}/{checksum[:2]}/{checksum}"

    @api.model
    def _read_file(self, fname: str, size: int | None = None) -> bytes:
        try:
            full_path = self._get_full_path(fname)
        except ValueError:
            _logger.exception("_read_file refused the store key %r", fname)
            _debug.logic("read_file_refused", fname=fname, reason="escapes_filestore")
            return b""
        try:
            with _debug.perf("read_file", fname=fname, size=size):
                with Path(full_path).open("rb") as f:
                    return f.read(size)
        except OSError:
            _logger.info("_read_file could not read %s", full_path, exc_info=True)
            _debug.logic("read_file_missing", fname=fname)
        return b""

    @contextlib.contextmanager
    def _stage_temp_file(self, prefix: str) -> Generator[Path]:
        tmp_dir = self._get_filestore_dir("tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{prefix}-{uuid.uuid4().hex}"
        try:
            yield tmp_path
        except Exception as exc:
            if isinstance(exc, OSError):
                _logger.info("filestore staging failed for %s", tmp_path, exc_info=True)
            _debug.lifecycle(
                "temp_file_discarded", prefix=prefix, error=type(exc).__name__
            )
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise

    @api.model
    def _write_file(self, bin_value: bytes, checksum: str) -> str:
        fname, full_path = self._prepare_file_destination(bin_value, checksum)
        self._mark_for_gc(fname)
        complete = self._is_stored_file_complete(full_path, len(bin_value))
        _debug.logic("write_file", fname=fname, size=len(bin_value), existing=complete)
        if not complete:
            with _debug.perf("write_file_io", fname=fname, size=len(bin_value)):
                with self._stage_temp_file("write") as tmp_path:
                    with tmp_path.open("wb") as fp:
                        fp.write(bin_value)
                    tmp_path.replace(full_path)
        return fname

    @api.model
    def _write_file_stream(
        self, fileobj: Any, *, chunk_size: int | None = None
    ) -> tuple[str, int, str]:
        chunk_size = chunk_size or self._STREAM_CHUNK_SIZE
        digest = prepare_content_hasher()
        size = 0
        with self._stage_temp_file("stream") as tmp_path:
            with tmp_path.open("wb") as out:
                while chunk := fileobj.read(chunk_size):
                    if isinstance(chunk, str):
                        chunk = chunk.encode()
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            checksum = digest.hexdigest()
            if not size:
                _debug.logic("write_file_stream_empty", chunk_size=chunk_size)
                tmp_path.unlink(missing_ok=True)
                return "", 0, checksum
            fname, full_path_str = self._prepare_file_destination(
                None, checksum, source_path=str(tmp_path)
            )
            self._mark_for_gc(fname)
            complete = self._is_stored_file_complete(full_path_str, size)
            _debug.logic("write_file_stream", fname=fname, size=size, existing=complete)
            if complete:
                tmp_path.unlink(missing_ok=True)
            else:
                tmp_path.replace(full_path_str)
        return fname, size, checksum

    @api.model
    def _get_stored_file_size(self, fname: str) -> int | None:
        try:
            return Path(self._get_full_path(fname)).stat().st_size
        except ValueError, OSError:
            return None

    @api.model
    def _is_stored_file_complete(self, full_path: str, size: int) -> bool:
        try:
            return Path(full_path).stat().st_size == size
        except OSError:
            return False

    @api.model
    def _check_admin_access(self) -> None:
        if not self.env.is_admin():
            _debug.logic("admin_access_refused", uid=self.env.uid)
            raise AccessError(
                self.env._("Only administrators can execute this action.")
            )

    @api.model
    def _get_full_path(self, path: str) -> str:
        path = self._normalize_store_key(path)
        configured = self._get_filestore()
        filestore = _get_filestore_root(configured)
        resolved = os.path.realpath(Path(filestore, path))
        if resolved != filestore and not resolved.startswith(filestore + os.sep):
            _debug.logic("store_key_refused", key=path, reason="escapes_filestore")
            raise ValueError(f"Attachment path {path!r} escapes the filestore")
        return str(Path(configured, path))

    @api.model
    def _get_filestore_dir(self, name: str) -> Path:
        return _get_filestore_dir_path(self._get_filestore(), name)

    @api.model
    def _get_image_autoresize_config(self) -> tuple[list[str], int, int, int]:
        ICP = self.env["ir.config_parameter"].sudo().get_param
        subtypes = [
            subtype.strip()
            for subtype in ICP(
                "base.image_autoresize_extensions", "png,jpeg,bmp,tiff"
            ).split(",")
        ]
        max_resolution = ICP("base.image_autoresize_max_px", "1920x1920")
        if not str2bool(max_resolution, True):
            _debug.logic("autoresize_disabled", subtypes=len(subtypes))
            return subtypes, 0, 0, 0
        try:
            max_width, max_height = map(int, max_resolution.split("x"))
        except ValueError:
            _logger.warning(
                "Invalid base.image_autoresize_max_px value: %r, skipping image resize",
                max_resolution,
            )
            _debug.logic("autoresize_config_invalid", value=max_resolution)
            return subtypes, 0, 0, 0
        quality = self.env.registry.settings.get_int(
            self.env, "base.image_autoresize_quality", 80
        )
        return subtypes, max_width, max_height, quality

    @api.model
    def _prepare_file_destination(
        self, bin_data: bytes | None, sha: str, *, source_path: str | None = None
    ) -> tuple[str, str]:
        fname = self._get_store_key(sha)
        full_path = Path(self._get_full_path(fname))
        full_path.parent.mkdir(exist_ok=True, parents=True)

        if self._is_content_collision_check_enabled() and full_path.is_file():
            with _debug.perf(
                "collision_check", fname=fname, streamed=source_path is not None
            ) as span:
                same = (
                    self._is_same_file(source_path, str(full_path))
                    if source_path is not None
                    else self._is_same_bytes_as_file(bin_data or b"", str(full_path))
                )
                span.set(same=same)
            if not same:
                _debug.logic("content_collision_refused", fname=fname)
                raise UserError(
                    self.env._("The attachment collides with an existing file.")
                )
        return fname, str(full_path)

    def _get_pdf_raw(self) -> bytes | None:
        self.check_singleton()
        if self.type == "url" or not (self.mimetype or "").startswith(
            "application/pdf"
        ):
            return None
        return self._get_content() or None

    @api.model
    def _is_content_index_required(self, values: dict[str, Any]) -> bool:
        return not self.env.context.get("attachment_index_from_origin")

    def _store_content_cached(
        self,
        memo: ContentMemo,
        data: bytes,
        mimetype: str,
        backend: AttachmentStorage,
        *,
        verify_collision: bool,
        index: bool = True,
    ) -> dict[str, Any]:
        checksum = self._get_content_checksum(data)
        key = (checksum, mimetype, index)
        cached = memo.get(key)
        if cached is not None and (not verify_collision or cached[0] == data):
            _debug.logic("content_memo_hit", checksum=checksum, size=len(data))
            return cached[1]
        vals = self._store_content(
            data, mimetype, backend, checksum=checksum, index=index
        )
        memo[key] = (data, vals)
        return vals

    def _store_content(
        self,
        data: bytes,
        mimetype: str,
        backend: AttachmentStorage | None = None,
        checksum: str | None = None,
        *,
        index: bool = True,
    ) -> dict[str, Any]:
        if checksum is None:
            checksum = self._get_content_checksum(data)
        _debug.pipeline(
            "content_vals",
            size=len(data),
            mimetype=mimetype,
            indexed=index,
            checksum_given=checksum is not None,
        )
        index_vals = (
            {"index_content": self._extract_index_content(data, mimetype)}
            if index
            else {}
        )
        if backend is None:
            backend = self._get_storage_backend()
        with _debug.perf(
            "store_content",
            size=len(data),
            mimetype=mimetype,
            backend=type(backend).__name__,
            indexed=bool(index_vals.get("index_content")),
        ):
            stored = backend.write(data, checksum)
        return {
            "file_size": len(data),
            "checksum": checksum,
            **index_vals,
            **stored,
        }

    def _get_raw_access_token(self) -> str:
        self.check_singleton()
        return limited_field_access_token(self, "raw", scope="binary")

    @api.model
    def _get_serve_attachment(
        self, url: str, extra_domain: Any = None, order: str | None = None
    ) -> Self:
        domain = (
            Domain("type", "=", "binary")
            & Domain("url", "=", url)
            & Domain(extra_domain or [])
        )
        return self.search(domain, order=order, limit=1)

    @api.model
    def get_groups_allowed_to_serve(self) -> list[str]:
        return ["base.group_system"]

    def _get_mimetype_from_values(self, values: dict[str, Any]) -> str:
        mimetype = None
        if values.get("mimetype"):
            mimetype = values["mimetype"]
        if not mimetype and values.get("name"):
            mimetype = mimetypes.guess_type(values["name"])[0]
        if not mimetype and values.get("url"):
            mimetype = mimetypes.guess_type(values["url"].split("?")[0])[0]
        if not mimetype or mimetype == "application/octet-stream":
            raw = None
            if "raw" in values and values["raw"] is not None:
                raw = values["raw"]
            elif values.get("datas"):
                raw = self._decode_datas(values["datas"])
            if raw:
                mimetype = guess_mimetype(raw)
                _debug.logic("mimetype_sniffed", mimetype=mimetype, size=len(raw))
        return (mimetype and mimetype.lower()) or "application/octet-stream"

    def _get_mimetype_for_write(self, vals: dict[str, Any]) -> str:
        naming = {}
        for key in ("name", "url"):
            if key in vals:
                continue
            values = {record[key] for record in self}
            if len(values) == 1 and (value := values.pop()):
                naming[key] = value
        return self._get_mimetype_from_values(naming | vals)

    def _get_content_prefix(self, size: int | None = None) -> bytes:
        self.check_singleton()
        stored = self._get_stored_content(size)
        if stored is not None:
            return stored
        if static_path := self._get_static_file_path():
            _debug.logic("content_prefix_static", attachment=self.id, size=size)
            with file_open(static_path, "rb") as file:
                return file.read(size)
        return b""

    def _get_content(self, size: int | None = None) -> bytes:
        self.check_singleton()
        return self._get_content_prefix(size)

    def _as_document(self, read_up_to: int = CHEAP, **options: Any) -> Document | None:
        self.check_singleton()
        if self.content_released_at:
            return None
        attachment = self.sudo()
        content = (
            attachment._get_content if self.file_size else attachment._get_content()
        )
        if not content:
            return None
        options.setdefault("seeder", self._reading_seeder())
        return Document(
            content,
            self.mimetype or "",
            self.name or "",
            env=self.env,
            company=self.company_id or self.env.company,
            read_up_to=read_up_to,
            attachment_id=self.id,
            **options,
        )

    def _keep_costly_readings(self, document: Document) -> None:
        self.check_singleton()
        for representation in PERSISTED_READINGS:
            if document.read_cost(representation) < METERED:
                continue
            value = document.read(representation)
            if value:
                self._store_reading(
                    representation, value, read_by=document.read_by(representation)
                )


    def _share_readings(self, origins: list[Self], copies: Self) -> None:
        read_origins = [origin.id for origin in origins if origin.has_readings]
        if not read_origins:
            return
        Reading = self.env["ir.attachment.reading"].with_privilege(
            "base.privilege_keep_readings",
            reason="a copy keeps what its bytes were read as",
        )
        done = Reading.search(
            [("attachment_id", "in", read_origins), ("state", "=", "done")]
        )
        if not done:
            return
        by_origin = defaultdict(list)
        for reading in done:
            by_origin[reading.attachment_id.id].append(reading)
        Reading.create(
            [
                {
                    "attachment_id": copied.id,
                    "representation": reading.representation,
                    "state": "done",
                    "value": reading.value,
                    "checksum": reading.checksum,
                    "read_by": reading.read_by,
                    "purpose": reading.purpose,
                    "language": reading.language,
                    "read_at": reading.read_at,
                }
                for origin, copied in zip(origins, copies, strict=True)
                for reading in by_origin.get(origin.id, ())
            ]
        )

    def _note_readings(self) -> None:
        if not self:
            return
        self.flush_recordset(["has_readings"])
        self.env.cr.execute(
            SQL(
                "UPDATE ir_attachment SET has_readings = true"
                " WHERE id = ANY(%s) AND has_readings IS NOT TRUE",
                self.ids,
            )
        )
        self.invalidate_recordset(["has_readings"], flush=False)

    def _reading(self, representation: str) -> IrAttachmentReading:
        self.check_singleton()
        for reading in self.reading_ids:
            if reading.representation == representation:
                if (
                    reading.checksum
                    and self.checksum
                    and reading.checksum != self.checksum
                    and not self.content_released_at
                ):
                    break
                return reading
        return self.env["ir.attachment.reading"]

    def _reading_seeder(
        self, skip: str | None = None
    ) -> Callable[[str], tuple[Any, str] | None]:
        attachment = self

        def seeder(representation: str) -> tuple[Any, str] | None:
            if representation == skip or representation not in PERSISTED_READINGS:
                return None
            reading = attachment._reading(representation)
            if reading.state != "done":
                return None
            return reading._decoded(), reading.read_by or ""

        return seeder

    def _reading_row(self, representation: str) -> IrAttachmentReading:
        self.check_singleton()
        Reading = self.env["ir.attachment.reading"].with_privilege(
            "base.privilege_keep_readings", reason="keep what a file was read as"
        )
        existing = Reading.search(
            [("attachment_id", "=", self.id), ("representation", "=", representation)]
        )
        if existing:
            return existing
        try:
            with self.env.cr.savepoint():
                return Reading.create(
                    {"attachment_id": self.id, "representation": representation}
                )
        except psycopg.errors.UniqueViolation as exc:
            existing = Reading.search(
                [
                    ("attachment_id", "=", self.id),
                    ("representation", "=", representation),
                ]
            )
            if existing:
                return existing
            _debug.logic("reading_row_raced", attachment=self.id, of=representation)
            msg = f"reading {representation} of attachment {self.id} raced"
            raise psycopg.errors.SerializationFailure(msg) from exc

    def _read(
        self,
        representation: str,
        *,
        purpose: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
        up_to: int = METERED,
    ) -> Any:
        self.check_singleton()
        if representation not in PERSISTED_READINGS:
            raise ValueError(f"{representation!r} is not kept as a reading")
        reading = self._reading_row(representation)
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    SQL(
                        "SELECT id FROM ir_attachment_reading "
                        "WHERE id = %s FOR UPDATE NOWAIT",
                        reading.id,
                    )
                )
        except psycopg.errors.LockNotAvailable:
            _debug.logic("reading_busy", attachment=self.id, of=representation)
            return None
        reading.write(
            {
                "state": "running",
                "error": False,
                "purpose": purpose or False,
                "language": language or False,
            }
        )
        document = self._as_document(
            read_up_to=up_to,
            purpose=purpose,
            language=language,
            prompt=prompt,
            seeder=self._reading_seeder(skip=representation),
        )
        value = document.read(representation) if document is not None else None
        failure = (
            document.errors.get(representation)
            if document is not None
            else self.env._("This file holds no data to read.")
        )
        if not value and failure:
            reading.write({"state": "failed", "error": failure})
        else:
            reading.write(
                {
                    "state": "done",
                    "value": reading._encoded(representation, value),
                    "read_by": document.read_by(representation) or False,
                    "checksum": self.checksum or False,
                    "read_at": fields.Datetime.now(),
                    "error": False,
                }
            )
        self._on_read(representation, reading)
        return value

    def _read_later(
        self,
        representation: str,
        *,
        eta: Any = None,
        priority: int | None = None,
        channel: str = READING_JOB_CHANNEL,
        **options: Any,
    ) -> Any:
        self.check_singleton()
        reading = self._reading_row(representation)
        if reading.state != "running":
            reading.write({"state": "queued", "error": False})
        identity_key = f"reading.{representation}.{self.id}"
        job = self.delayed(
            channel=channel,
            identity_key=identity_key,
            name=f"Read {representation} of {self.name or self.id}",
            priority=priority,
            eta=eta,
        )._job_read(representation, **options)
        if eta is None:
            self.env["ir.job"]._expedite(identity_key)
        return job

    def _await_reading(self, representation: str) -> Any:
        self.check_singleton()
        if self._reading(representation).state in ("done", "failed"):
            return self.env["ir.job"]
        return self._read_later(representation)

    @api.job(channel=READING_JOB_CHANNEL, max_retries=1)
    def _job_read(self, representation: str, **options: Any) -> None:
        self.check_singleton()
        self._read(representation, **options)

    def _store_reading(
        self,
        representation: str,
        value: Any,
        *,
        read_by: str = "",
        language: str | None = None,
        purpose: str | None = None,
        announce: bool = True,
    ) -> IrAttachmentReading:
        self.check_singleton()
        reading = self._reading_row(representation)
        reading.write(
            {
                "state": "done",
                "value": reading._encoded(representation, value),
                "read_by": read_by or False,
                "language": language or False,
                "purpose": purpose or False,
                "checksum": self.checksum or False,
                "read_at": fields.Datetime.now(),
                "error": False,
            }
        )
        if announce:
            self._on_read(representation, reading)
        elif representation in (TEXT, CUES):
            self._index_from_readings()
        return reading

    def _on_read(self, representation: str, reading: IrAttachmentReading) -> None:
        self.check_singleton()
        if reading.state == "done" and representation in (TEXT, CUES):
            self._index_from_readings()

    def _index_from_readings(self) -> None:
        self.check_singleton()
        text = ""
        for representation in (TEXT, CUES):
            reading = self._reading(representation)
            if reading.state != "done":
                continue
            value = reading._decoded()
            text = value if representation == TEXT else cues_as_text(value)
            if text:
                break
        if not text:
            return
        limit = self._get_index_max_chars()
        self.flush_recordset(["index_content"])
        self.env.cr.execute(
            SQL(
                "UPDATE ir_attachment SET index_content = %s WHERE id = %s",
                text[:limit] if limit > 0 else text,
                self.id,
            )
        )
        self.invalidate_recordset(["index_content"], flush=False)

    def _release_content(self) -> None:
        self._check_serving_attachments()
        releasable = self.sudo().filtered(
            lambda attachment: (
                attachment.type == "binary" and not attachment.content_released_at
            )
        )
        if not releasable:
            return
        stored = OrderedSet(releasable.filtered("store_fname").mapped("store_fname"))
        vals = self._store_content(b"", "", index=False)
        super(IrAttachment, releasable).write(
            {**vals, "content_released_at": fields.Datetime.now()}
        )
        _debug.lifecycle("content_released", count=len(releasable), files=len(stored))
        self._remove_stored_file_multi(stored)

    @api.autovacuum
    def _gc_expired_content(self) -> None:
        expired = self.sudo().search(
            [
                ("content_expires_at", "<=", fields.Datetime.now()),
                ("content_released_at", "=", False),
            ]
        )
        expired._release_content()

    def _with_field_rows(self) -> Self:
        return self.with_context(skip_res_field_check=True)

    def _with_bin_size_disabled(self) -> Self:
        if not any(self.env.context.get(key) for key in BIN_SIZE_KEYS):
            return self
        return self.with_context(**BIN_SIZE_KEYS)

    def _get_stored_content(self, size: int | None = None) -> bytes | None:
        self.check_singleton()
        if self.store_fname:
            with _debug.perf(
                "stored_content_read", attachment=self.id, size=size
            ) as span:
                data = self._get_storage_backend_for_key(self.store_fname).read(
                    self.store_fname, size
                )
                span.set(bytes=len(data) if data else 0)
            self._is_content_unreadable(
                data,
                self.file_size if size is None else min(self.file_size, size),
                att_id=self.id,
                key=self.store_fname,
                action="serving empty bytes",
            )
            return data
        if db_datas := self._with_bin_size_disabled().db_datas:
            return db_datas if size is None else db_datas[:size]
        return None

    @api.model
    def _is_content_unreadable(
        self,
        data: bytes,
        expected_size: int,
        *,
        att_id: Any,
        key: Any,
        action: str,
    ) -> bool:
        if data or not expected_size:
            return False
        _logger.error(
            "Unreadable stored content for attachment %s (store_fname=%s); %s",
            att_id,
            key,
            action,
        )
        _debug.logic(
            "content_unreadable", attachment=att_id, expected_size=expected_size
        )
        return True

    def _get_static_file_path(self) -> str | None:
        self.check_singleton()
        if not self.url:
            return None
        host = request.httprequest.environ.get("HTTP_HOST", "") if request else ""
        return root.get_static_file_path(self.url, host=host)

    @api.model
    def _is_same_stream(self, stream_a: Any, stream_b: Any) -> bool:
        chunks = 0
        while True:
            chunk_a = stream_a.read(self._COMPARE_BLOCK_SIZE)
            chunks += 1
            if chunk_a != stream_b.read(self._COMPARE_BLOCK_SIZE):
                _debug.logic("stream_compare_differs", chunk=chunks)
                return False
            if not chunk_a:
                _debug.perf.count("stream_compared", chunks=chunks)
                return True

    @api.model
    def _is_same_stream_as_file(
        self, source: Any, source_size: int, filepath: str
    ) -> bool:
        if Path(filepath).stat().st_size != source_size:
            return False
        with Path(filepath).open("rb") as fd:
            return self._is_same_stream(source, fd)

    @api.model
    def _is_same_bytes_as_file(self, bin_data: bytes, filepath: str) -> bool:
        with io.BytesIO(bin_data) as buf:
            return self._is_same_stream_as_file(buf, len(bin_data), filepath)

    @api.model
    def _is_same_file(self, path_a: str, path_b: str) -> bool:
        with Path(path_a).open("rb") as fa:
            size = os.fstat(fa.fileno()).st_size
            return self._is_same_stream_as_file(fa, size, path_b)

    @api.model
    def _normalize_store_key(self, key: str) -> str:
        return re.sub(r"[.:]", "", key).strip("/\\")

    @api.model
    def _is_canonical_store_key(self, fname: str) -> bool:
        return bool(fname) and self._normalize_store_key(fname) == fname

    def _update_content(self, asbytes: Callable[[Any], bytes]) -> None:
        self._check_serving_attachments()
        old_fnames = []
        wrote_content = False
        backend = self._get_storage_backend()
        verify_collision = self._is_content_collision_check_enabled()
        memo: ContentMemo = {}
        _debug.pipeline(
            "update_content_begin",
            count=len(self),
            backend=type(backend).__name__,
            verify_collision=verify_collision,
        )

        for attach in self._with_bin_size_disabled():
            bin_data = asbytes(attach)
            vals = self._store_content_cached(
                memo,
                bin_data,
                attach.mimetype,
                backend,
                verify_collision=verify_collision,
            )

            if attach.store_fname:
                old_fnames.append(attach.store_fname)

            super(IrAttachment, attach.sudo()).write(vals)

            if bin_data:
                wrote_content = True

        _debug.lifecycle(
            "update_content",
            count=len(self),
            replaced=len(old_fnames),
            wrote_content=wrote_content,
        )
        self._remove_stored_file_multi(OrderedSet(old_fnames))

    @api.model
    def _get_storage_location(self) -> str:
        return self.env.registry.settings.get(
            self.env, "ir_attachment.location", "file"
        )

    @api.model
    def _get_storage_backend(self) -> AttachmentStorage:
        location = self._get_storage_location()
        backend_cls = STORAGE_BACKENDS.get(location, FileStorage)
        _debug.logic(
            "storage_backend",
            location=location,
            backend=backend_cls.__name__,
            fallback=location not in STORAGE_BACKENDS,
        )
        return backend_cls(self.env)

    @api.model
    def _remove_stored_file_multi(self, fnames: Collection[str]) -> None:
        plain_fnames = []
        remote_fnames = []
        for fname in fnames:
            (remote_fnames if "://" in fname else plain_fnames).append(fname)
        _debug.lifecycle(
            "stored_files_released",
            total=len(fnames),
            remote=len(remote_fnames),
            marked_for_gc=len(plain_fnames),
        )
        if plain_fnames:
            self._mark_for_gc_multi(plain_fnames)
        if remote_fnames:
            self.env.cr.postcommit.add(
                functools.partial(self._remove_remote_files, remote_fnames)
            )

    @api.model
    def _remove_remote_files(self, fnames: Collection[str]) -> None:
        self.env.cr.execute(
            "SELECT store_fname FROM ir_attachment WHERE store_fname = ANY(%s)",
            [list(fnames)],
        )
        referenced = {row[0] for row in self.env.cr.fetchall()}
        _debug.lifecycle(
            "remote_files_removed",
            count=len(fnames) - len(referenced),
            still_referenced=len(referenced),
        )
        for fname in fnames:
            if fname not in referenced:
                self._get_storage_backend_for_key(fname).remove(fname)

    @api.model
    def _is_content_collision_check_enabled(self) -> bool:
        default = ALGO_TAG == "s1"
        return str2bool(
            self.env.registry.settings.get(
                self.env, "ir_attachment.verify_content_collision", str(default)
            ),
            default,
        )

    def _prepare_contents_resized(self, values: dict[str, Any]) -> dict[str, Any]:
        mimetype = values.get("mimetype") or self._get_mimetype_from_values(values)
        values["mimetype"] = mimetype
        maintype, _, subtype = mimetype.partition("/")
        if maintype != "image" or not (values.get("datas") or values.get("raw")):
            return values
        subtypes, max_width, max_height, quality = self._get_image_autoresize_config()
        if subtype not in subtypes or not max_width:
            _debug.logic(
                "autoresize_skipped",
                subtype=subtype,
                reason="disabled" if not max_width else "subtype_excluded",
            )
            return values

        is_raw = bool(values.get("raw"))
        try:
            data = values["raw"] if is_raw else base64.b64decode(values["datas"])
            img = image.ImageProcess(data, verify_resolution=False)
            if not img.size:
                _logger.info("Post processing ignored : Empty source, SVG, or WEBP")
                _debug.logic("autoresize_skipped", subtype=subtype, reason="no_image")
                return values
            width, height = img.size
            if width <= max_width and height <= max_height:
                _debug.logic(
                    "autoresize_skipped",
                    subtype=subtype,
                    width=width,
                    height=height,
                    reason="within_bounds",
                )
                return values
            with _debug.perf("image_resize", subtype=subtype, bytes_in=len(data)):
                img = img.resize(max_width, max_height)
                image_data = img.image_quality(
                    quality=quality if subtype == "jpeg" else 0
                )
            _debug.logic(
                "image_autoresized",
                subtype=subtype,
                width=width,
                height=height,
                bytes_in=len(data),
                bytes_out=len(image_data),
            )
            if is_raw:
                values["raw"] = image_data
            else:
                values["datas"] = base64.b64encode(image_data)
        except (UserError, OSError, image.Image.DecompressionBombError) as e:
            _logger.info("Post processing ignored : %s", e)
            _debug.logic("autoresize_skipped", subtype=subtype, reason=type(e).__name__)
        return values

    @api.model
    def _get_index_max_chars(self) -> int:
        return self.env.registry.settings.get_int(
            self.env, "ir_attachment.index_max_chars", self._INDEX_MAX_CHARS
        )

    @api.model
    def _get_index_content(self, bin_data: bytes, file_type: str) -> str | None:
        if not (file_type and file_type.startswith("text/")):
            return None
        text = bin_data[: self._INDEX_MAX_BYTES].decode("utf-8", errors="ignore")
        limit = self._get_index_max_chars()
        if limit <= 0:
            _debug.logic("index_content_unbounded", mimetype=file_type, chars=len(text))
            return "\n".join(_INDEX_WORD_RE.findall(text))
        words = []
        budget = limit
        for match in _INDEX_WORD_RE.finditer(text):
            words.append(match.group()[:budget])
            budget -= len(words[-1]) + 1
            if budget <= 0:
                break
        _debug.perf.count(
            "index_content", mimetype=file_type, words=len(words), limit=limit
        )
        return "\n".join(words)

    @api.model
    def _extract_index_content(self, bin_data: bytes, mimetype: str) -> str | None:
        index_content = self._get_index_content(bin_data, mimetype)
        if not index_content:
            return index_content
        limit = self._get_index_max_chars()
        if limit <= 0 or len(index_content) <= limit:
            return index_content
        _logger.debug(
            "index_content truncated from %d to %d characters",
            len(index_content),
            limit,
        )
        return index_content[:limit]

    @api.model
    def _get_index_read_size(self, mimetype: str) -> int | None:
        if mimetype and mimetype.startswith("text/"):
            return self._INDEX_MAX_BYTES
        return 0

    @api.model
    def _coerce_model_name(self, res_model: Any) -> str | None:
        return res_model if isinstance(res_model, str) and res_model else None

    def _post_add_create(self, **kwargs: Any) -> None:
        pass

    def generate_access_token(self) -> list[str]:
        tokens = []
        new_tokens = {}
        for attachment in self:
            if attachment.access_token:
                tokens.append(attachment.access_token)
                continue
            token = self._prepare_access_token()
            new_tokens[attachment.id] = token
            tokens.append(token)
        for attachment_id, token in new_tokens.items():
            super(IrAttachment, self.browse(attachment_id)).write(
                {"access_token": token}
            )
        _debug.lifecycle(
            "access_tokens_generated", count=len(self), created=len(new_tokens)
        )
        return tokens

    @api.model
    def _get_dedup_owner(self, vals: dict[str, Any]) -> tuple[str | bool, int | bool]:
        return (
            self._coerce_model_name(vals.get("res_model")) or False,
            vals.get("res_id") or False,
        )

    @api.model
    def create_unique(self, values_list: list[dict[str, Any]]) -> list[int]:
        self.browse().check_access("create")

        entries: list[tuple[dict, tuple[str, int, str, Any, Any] | None]] = []
        raw_by_key: dict[tuple, bytes] = {}
        verify_collision = self._is_content_collision_check_enabled()
        model_and_ids = defaultdict(OrderedSet)
        for values in values_list:
            if "mimetype" not in values:
                _debug.logic("create_unique_refused", reason="missing_mimetype")
                raise UserError(self.env._("Attachment is missing its mimetype."))
            vals, has_content = self._normalize_content_vals(dict(values))
            vals = self._prepare_contents(vals)
            model_and_ids[self._coerce_model_name(vals.get("res_model"))].add(
                vals.get("res_id")
            )
            key = None
            if has_content:
                raw = vals["raw"]
                key = (
                    self._get_content_checksum(raw),
                    len(raw),
                    vals["mimetype"],
                    *self._get_dedup_owner(vals),
                )
                if verify_collision and raw_by_key.setdefault(key, raw) != raw:
                    _debug.logic("create_unique_digest_collision", size=len(raw))
                    key = None
            entries.append((vals, key))
        if any(get_inaccessible_owners(self.env, model_and_ids, "write")):
            _debug.logic(
                "create_unique_refused",
                uid=self.env.uid,
                reason="comodel_inaccessible",
            )
            raise AccessError(
                self.env._("Sorry, you are not allowed to access this document.")
            )

        all_checksums = list({key[0] for _vals, key in entries if key})
        _debug.pipeline(
            "create_unique_dedup_lookup",
            entries=len(entries),
            dedupable=sum(1 for _vals, key in entries if key),
            checksums=len(all_checksums),
        )
        existing_by_key: dict[tuple, int] = {}
        if all_checksums:
            for (
                checksum,
                file_size,
                mimetype,
                res_model,
                res_id,
                att_id,
            ) in self.sudo()._read_group(
                self._get_domain_dedup(all_checksums),
                groupby=["checksum", "file_size", "mimetype", "res_model", "res_id"],
                aggregates=["id:max"],
            ):
                existing_by_key[
                    checksum, file_size, mimetype, res_model or False, res_id or False
                ] = att_id
        self._remove_colliding_dedup_matches(existing_by_key, raw_by_key)

        to_create = []
        new_index_by_key: dict[tuple, int] = {}
        own_indexes: list[int | None] = []
        for vals, key in entries:
            if key is None or vals.get("res_field"):
                own_indexes.append(len(to_create))
                to_create.append(vals)
                continue
            own_indexes.append(None)
            if key not in existing_by_key and key not in new_index_by_key:
                new_index_by_key[key] = len(to_create)
                to_create.append(vals)
        created = (
            self.with_context(image_no_postprocess=True).create(to_create)
            if to_create
            else self.browse()
        )
        _debug.logic(
            "create_unique",
            requested=len(values_list),
            reused=len(existing_by_key),
            created=len(created),
        )
        return [
            (
                created[own_index].id
                if own_index is not None
                else existing
                if (existing := existing_by_key.get(key))
                else created[new_index_by_key[key]].id
            )
            for (_vals, key), own_index in zip(entries, own_indexes, strict=True)
        ]

    @api.model
    def _get_domain_dedup(self, checksums: list[str]) -> Domain:
        domain = Domain("checksum", "in", checksums) & Domain("res_field", "=", False)
        if self.env.is_system():
            return domain
        attached = Domain("res_model", "!=", False) & Domain("res_id", ">", 0)
        return domain & (attached | Domain("create_uid", "=", self.env.uid))

    def _remove_colliding_dedup_matches(
        self, existing_by_key: dict[tuple, int], raw_by_key: dict[tuple, bytes]
    ) -> None:
        if not existing_by_key or not self._is_content_collision_check_enabled():
            return
        for key, att_id in list(existing_by_key.items()):
            if self.browse(att_id).sudo()._get_stored_content() != raw_by_key.get(key):
                del existing_by_key[key]
                _debug.logic("dedup_match_dropped", attachment=att_id)
                _logger.warning(
                    "create_unique: attachment %s shares the digest of new "
                    "content but not its bytes; not reusing it",
                    att_id,
                )

    def _prepare_access_token(self) -> str:
        return str(uuid.uuid4())

    def _create_from_request_file(
        self, file: Any, *, mimetype: str = "DERIVE", **vals: Any
    ) -> Self:
        if mimetype == "DERIVE":
            filename = file.filename
            mimetype = mimetypes.guess_type(filename or "")[0] or ""
            if not mimetype or mimetype == "application/octet-stream":
                head = file.read(MIMETYPE_HEAD_SIZE)
                file.seek(-len(head), 1)
                mimetype = guess_mimetype(head)
        elif mimetype == "TRUST":
            mimetype = file.content_type
            filename = file.filename
        elif mimetype == "GUESS":
            head = file.read(MIMETYPE_HEAD_SIZE)
            file.seek(-len(head), 1)
            mimetype = guess_mimetype(head)
            filename = fix_filename_extension(file.filename, mimetype)
            if mimetype in ("application/zip", *OLECF_MIMETYPES):
                mimetype = mimetypes.guess_type(filename)[0] or mimetype
        elif "/" in mimetype and all(mimetype.split("/", 1)):
            filename = fix_filename_extension(file.filename, mimetype)
        else:
            _debug.logic("request_file_refused", reason="bad_mimetype_policy")
            raise ValueError(f"{mimetype=}")

        values = {"name": filename, "type": "binary", "mimetype": mimetype, **vals}
        streamed = self._is_stream_upload_required(mimetype)
        _debug.pipeline("request_file_received", mimetype=mimetype, streamed=streamed)
        if streamed:
            return self._create_from_stream(file, **values)
        return self.create({"raw": file.read(), **values})

    def _create_from_stream(
        self, fileobj: Any, *, name: str, mimetype: str, **vals: Any
    ) -> Self:
        record = self.create(
            {"name": name, "type": "binary", "mimetype": mimetype, **vals}
        )
        with _debug.perf("stream_store", attachment=record.id, mimetype=mimetype):
            store_values = self._get_storage_backend().write_stream(fileobj)
        read_size = self._get_index_read_size(record.mimetype)
        if not self._is_content_index_required(
            {"name": name, "type": "binary", "mimetype": mimetype, **vals}
        ):
            read_size = 0
        index_content = None
        if read_size != 0:
            content = b""
            readable = True
            if store_values.get("store_fname"):
                content = self._get_storage_backend_for_key(
                    store_values["store_fname"]
                ).read(store_values["store_fname"], read_size)
                if self._is_content_unreadable(
                    content,
                    store_values["file_size"],
                    att_id=record.id,
                    key=store_values["store_fname"],
                    action="skipping index extraction",
                ):
                    readable = False
            elif store_values.get("db_datas"):
                db_datas = store_values["db_datas"] or b""
                content = db_datas if read_size is None else db_datas[:read_size]
            if readable:
                index_content = self._extract_index_content(content, record.mimetype)
        store_values["index_content"] = index_content
        _debug.lifecycle(
            "stream_stored",
            attachment=record.id,
            size=store_values.get("file_size"),
            in_db="db_datas" in store_values,
            indexed=bool(index_content),
        )
        super(IrAttachment, record.sudo()).write(store_values)
        return record

    def _to_http_stream(self) -> Stream:
        self.check_singleton()

        stream = Stream(
            mimetype=self.mimetype,
            download_name=self.name,
            etag=self.checksum,
            public=self.public,
        )

        if self.store_fname:
            _debug.logic("http_stream", attachment=self.id, source="storage")
            return self._get_storage_backend_for_key(self.store_fname).to_stream(
                self, stream
            )

        inline = self._with_bin_size_disabled().db_datas
        if inline:
            stream.type = "data"
            stream.data = inline
            stream.last_modified = self.write_date
            stream.size = len(inline)
            _debug.logic(
                "http_stream", attachment=self.id, source="db", size=len(inline)
            )

        elif self.url:
            if static_path := self._get_static_file_path():
                stream = Stream.from_path(static_path, public=True)
                _debug.logic("http_stream", attachment=self.id, source="static")
            else:
                stream.type = "url"
                stream.url = self.url
                _debug.logic("http_stream", attachment=self.id, source="url")

        else:
            stream.type = "data"
            stream.data = b""
            stream.size = 0
            _debug.logic("http_stream", attachment=self.id, source="empty")

        return stream

    def _migrate_remote_to_local(self) -> bool:
        self.check_singleton()
        return self.type == "binary"

    def _get_zip_detached_reader(self) -> Callable[[int], Iterator[bytes]] | None:
        return None

    @api.autovacuum
    def _audit_url_attachments(self) -> None:
        domain = Domain(
            [
                ("type", "=", "binary"),
                ("url", "!=", False),
                ("public", "=", False),
            ]
        )
        total = self.sudo().search_count(domain)
        if not total:
            _debug.logic("url_attachments_audit_skipped", reason="none")
            return
        suspicious = self.sudo().search(
            domain, order="id", limit=self._URL_AUDIT_WINDOW
        )
        ICP = self.env["ir.config_parameter"].sudo()
        param = "ir_attachment.url_audit_seen"
        seen = {
            int(token)
            for token in ICP.get_param(param, "").split(",")
            if token.strip().isdigit()
        }
        new = suspicious.filtered(lambda a: a.id not in seen)
        if new:
            _logger.warning(
                "Found %d non-public binary attachment(s) with `url` set "
                "(showing %d). ir.http._serve_fallback serves public rows only, "
                "so these URLs answer 404; set `public` on the ones meant to be "
                "served, or clear `url` on the rest. First URLs: %s",
                total,
                len(new),
                new.mapped("url"),
            )
        else:
            _logger.info(
                "%d previously reported non-public binary attachment(s) with "
                "`url` set remain unresolved and unserved (showing %d).",
                total,
                len(suspicious),
            )
        current = set(suspicious.ids)
        _debug.pipeline(
            "url_attachments_audited", total=total, new=len(new), seen=len(seen)
        )
        if current != seen:
            ICP.set_param(param, ",".join(map(str, sorted(current))))

    @api.autovacuum
    def _gc_file_store(self) -> tuple[int, int]:
        collected = 0
        capped = 0
        for backend_cls in tuple(STORAGE_BACKENDS.values()):
            with _debug.perf(
                "gc_backend", cr=self.env.cr, backend=backend_cls.__name__
            ) as span:
                swept = backend_cls(self.env).autovacuum()
                span.set(locked=swept is False)
            if swept is False:
                _logger.warning(
                    "filestore gc: %s could not take its lock and swept nothing "
                    "this run; unreferenced content stays on disk until the next "
                    "one",
                    backend_cls.__name__,
                )
            elif isinstance(swept, tuple):
                collected += swept[0]
                capped |= int(bool(swept[1]))
            elif swept:
                collected += swept
        _debug.lifecycle("gc_file_store", collected=collected, capped=bool(capped))
        return collected, capped

    @api.model
    def _get_domain_legacy_keys(self) -> Domain:
        return Domain(
            [
                ("store_fname", "!=", False),
                (
                    "store_fname",
                    "not =like",
                    self._get_store_key("_" * CONTENT_DIGEST_LEN),
                ),
                ("store_fname", "not like", "://"),
            ]
        )

    @api.autovacuum
    def _gc_rehash_legacy_keys(self, limit: int | None = None) -> tuple[int, int]:
        if ALGO_TAG == "s1":
            return 0, 0
        if limit is None:
            limit = self.env.registry.settings.get_int(
                self.env, "ir_attachment.rehash_legacy_keys_limit", 0
            )
        if limit <= 0:
            _debug.logic("rehash_skipped", reason="no_limit")
            return 0, 0
        if self._get_storage_location() != "file":
            _debug.logic("rehash_skipped", reason="not_file_storage")
            return 0, 0

        ICP = self.env["ir.config_parameter"].sudo()
        after = ICP.get_param_int(_REHASH_CURSOR_PARAM, 0)
        domain = self._get_domain_legacy_keys()
        model = self.sudo()._with_field_rows()
        legacy = model.search(
            domain & Domain("id", ">", after), order="id", limit=limit
        )
        if not legacy:
            if after:
                _debug.lifecycle("legacy_keys_pass_done", after=after)
                ICP.set_param(_REHASH_CURSOR_PARAM, 0)
            return 0, 0
        ICP.set_param(_REHASH_CURSOR_PARAM, legacy[-1].id)
        released_fnames = []
        backend = self._get_storage_backend()
        for attach in legacy:
            raw = attach._with_bin_size_disabled().raw
            expected_size = attach.file_size or self._get_stored_file_size(
                attach.store_fname
            )
            if expected_size is None or self._is_content_unreadable(
                raw,
                expected_size,
                att_id=attach.id,
                key=attach.store_fname,
                action="skipping rehash",
            ):
                continue
            old_fname = attach.store_fname
            checksum = self._get_content_checksum(raw)
            super(IrAttachment, attach.sudo()).write(
                {**backend.write(raw, checksum), "checksum": checksum}
            )
            released_fnames.append(old_fname)
            attach.invalidate_recordset()
            _debug.lifecycle(
                "legacy_key_rehashed", attachment=attach.id, old_key=old_fname
            )
        self._remove_stored_file_multi(released_fnames)
        rekeyed = len(released_fnames)
        _debug.lifecycle(
            "legacy_keys_rehashed", candidates=len(legacy), rekeyed=rekeyed
        )
        remaining = model.search_count(
            domain & Domain("id", ">", legacy[-1].id), limit=limit + 1
        )
        if not rekeyed:
            return 0, remaining
        _logger.info(
            "filestore rehash: re-keyed %d attachment(s) to the %s digest "
            "(%s%d still on a legacy key)",
            rekeyed,
            ALGO_TAG,
            "at least " if remaining > limit else "",
            remaining,
        )
        return rekeyed, remaining

    @api.autovacuum
    def _gc_stale_filestore_temps(self) -> tuple[int, int]:
        tmp_dir = self._get_filestore_dir("tmp")
        if not tmp_dir.is_dir():
            _debug.logic("gc_stale_temps_skipped", reason="no_tmp_dir")
            return 0, 0
        cutoff = time.time() - self._FILESTORE_TMP_MAX_AGE
        removed = 0
        remaining = 0
        for entry in tmp_dir.iterdir():
            if removed >= self._GC_MAX_ENTRIES:
                remaining = 1
                break
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                _logger.info("temp gc could not remove %s", entry, exc_info=True)
        if removed:
            _logger.info("filestore temp gc: removed %d stale temp file(s)", removed)
        _debug.lifecycle("gc_stale_temps", removed=removed, capped=bool(remaining))
        return removed, remaining

    def _get_gc_checklist(
        self, limit: int | None = None, grace: float | None = None
    ) -> dict[str, Path]:
        if grace is None:
            grace = self._GC_CHECKLIST_GRACE
        cutoff = time.time() - grace
        checklist = {}
        checklist_root = self._get_filestore_dir("checklist")
        skipped = 0
        capped = False
        for dirpath, _subdirs, filenames in checklist_root.walk():
            for filename in filenames:
                marker = dirpath / filename
                if grace:
                    try:
                        if marker.stat().st_mtime > cutoff:
                            skipped += 1
                            continue
                    except OSError:
                        skipped += 1
                        continue
                fname = str(marker.relative_to(checklist_root))
                checklist[fname] = marker
                if limit is not None and len(checklist) >= limit:
                    capped = True
                    break
            if capped:
                break
        if skipped:
            _logger.debug(
                "filestore gc: %d checklist marker(s) within the grace window "
                "left for a later run",
                skipped,
            )
        _debug.perf.count(
            "gc_checklist", entries=len(checklist), skipped=skipped, capped=capped
        )
        return checklist

    def _gc_file_store_unsafe(
        self, checklist: dict[str, Path] | None = None, grace: float | None = None
    ) -> int:
        if checklist is None:
            checklist = self._get_gc_checklist()
        if grace is None:
            grace = self._GC_CHECKLIST_GRACE

        removed = 0
        dropped = 0
        self.flush_model(["store_fname"])
        for names in batched(checklist, self.env.cr.BATCH_SIZE, strict=False):
            self.env.cr.execute(
                "SELECT store_fname FROM ir_attachment WHERE store_fname = ANY(%s)",
                [list(names)],
            )
            whitelist = {row[0] for row in self.env.cr.fetchall()}
            _debug.perf.count("gc_batch", names=len(names), referenced=len(whitelist))

            for fname in names:
                filepath = checklist[fname]
                if not self._is_canonical_store_key(fname):
                    _logger.info(
                        "filestore gc: dropping checklist entry %s, whose name is "
                        "not a store key this filestore writes",
                        filepath,
                    )
                    with contextlib.suppress(OSError):
                        filepath.unlink()
                    dropped += 1
                    continue
                if fname not in whitelist:
                    seen = self._get_marker_mtime_ns(filepath)
                    if (
                        grace
                        and seen is not None
                        and seen > (time.time() - grace) * 1e9
                    ):
                        continue
                    try:
                        full_path = self._get_full_path(fname)
                    except ValueError:
                        _logger.warning(
                            "filestore gc: dropping checklist entry %s, whose "
                            "store key resolves outside the filestore",
                            filepath,
                        )
                        with contextlib.suppress(OSError):
                            filepath.unlink()
                        dropped += 1
                        continue
                    try:
                        if not self._sweep_stored_file(
                            fname, Path(full_path), filepath, seen
                        ):
                            continue
                        _logger.debug("filestore gc unlinked %s", full_path)
                        removed += 1
                    except OSError:
                        _logger.info(
                            "filestore gc could not unlink %s",
                            full_path,
                            exc_info=True,
                        )
                        continue
                with contextlib.suppress(OSError):
                    filepath.unlink()

        _logger.debug("filestore gc %d checked, %d removed", len(checklist), removed)
        _debug.lifecycle(
            "gc_file_store_sweep",
            checked=len(checklist),
            removed=removed,
            dropped=dropped,
        )
        return removed

    @api.model
    def _get_marker_mtime_ns(self, marker: Path) -> int | None:
        try:
            return marker.stat().st_mtime_ns
        except OSError:
            return None

    @api.model
    def _sweep_stored_file(
        self, fname: str, full_path: Path, marker: Path, seen: int | None
    ) -> bool:
        aside = self._get_filestore_dir("gc") / fname
        aside.parent.mkdir(parents=True, exist_ok=True)
        try:
            full_path.rename(aside)
        except FileNotFoundError:
            return True
        if self._get_marker_mtime_ns(marker) != seen:
            aside.replace(full_path)
            _debug.logic("gc_sweep_restored", key=full_path.name, reason="remarked")
            return False
        aside.unlink()
        return True

    @api.model
    def _restore_set_aside_files(self) -> int:
        aside_root = self._get_filestore_dir("gc")
        restored = []
        for dirpath, _subdirs, filenames in aside_root.walk():
            for filename in filenames:
                aside = dirpath / filename
                fname = str(aside.relative_to(aside_root))
                try:
                    full_path = Path(self._get_full_path(fname))
                except ValueError:
                    _logger.warning(
                        "filestore gc: leaving %s set aside, its store key "
                        "resolves outside the filestore",
                        aside,
                    )
                    continue
                try:
                    if full_path.exists():
                        aside.unlink()
                    else:
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        aside.replace(full_path)
                except OSError:
                    _logger.warning(
                        "filestore gc: could not put back %s", aside, exc_info=True
                    )
                    continue
                restored.append(fname)
        if restored:
            self._mark_for_gc_multi(restored)
            _logger.warning(
                "filestore gc: put back %d file(s) an interrupted sweep had set "
                "aside; the next sweeps decide on them again",
                len(restored),
            )
        _debug.lifecycle("gc_set_aside_restored", count=len(restored))
        return len(restored)

    def _mark_for_gc(self, fname: str) -> None:
        self._mark_for_gc_multi((fname,))

    def _mark_for_gc_multi(self, fnames: Collection[str]) -> None:
        checklist_dir = self._get_filestore_dir("checklist")
        by_shard_dir: dict[Path, list[Path]] = defaultdict(list)
        for fname in fnames:
            full_path = checklist_dir / self._normalize_store_key(fname)
            by_shard_dir[full_path.parent].append(full_path)
        _debug.lifecycle("marked_for_gc", count=len(fnames), shards=len(by_shard_dir))
        for shard_dir, paths in by_shard_dir.items():
            with contextlib.suppress(OSError):
                shard_dir.mkdir(parents=True, exist_ok=True)
            for full_path in paths:
                try:
                    with full_path.open("ab"):
                        pass
                    os.utime(full_path)
                except OSError:
                    _logger.warning(
                        "filestore gc: could not mark %s for collection; its "
                        "content is now unreferenced and will not be swept",
                        full_path,
                        exc_info=True,
                    )

    def _can_return_content(
        self, field_name: str | None = None, access_token: str | None = None
    ) -> bool:
        self.check_singleton()
        attachment_sudo = self.sudo().with_context(prefetch_fields=False)
        if access_token:
            if not attachment_sudo._access_token_opens(access_token):
                _debug.logic(
                    "return_content_refused", attachment=self.id, reason="bad_token"
                )
                msg = "Invalid access token"
                raise AccessError(msg)
            _debug.logic("return_content", attachment=self.id, via="token")
            return True
        if attachment_sudo.public and not self._withholds(
            attachment_sudo.url, attachment_sudo.res_model
        ):
            _debug.logic("return_content", attachment=self.id, via="public")
            return True
        if self.env.user._is_portal():
            self.check_access("read")
            _debug.logic("return_content", attachment=self.id, via="portal_read")
            return True
        return super()._can_return_content(field_name, access_token)

    def _field_attachments_outside(
        self, scoped: dict[tuple[str, str], list[tuple[int, int]]], operation: str
    ) -> list[int]:
        outside: list[int] = []
        for (res_model, res_field), pairs in scoped.items():
            comodel = self.env[res_model]
            records = comodel.browse({res_id for _att, res_id in pairs})
            within = set(
                records._filtered_field_access(
                    comodel._fields[res_field], operation
                )._ids
            )
            outside.extend(att for att, res_id in pairs if res_id not in within)
        return outside

    def _check_access(self, operation: str) -> tuple[Self, Callable] | None:
        res = super()._check_access(operation)
        remaining = self
        error_func = None
        forbidden_ids = OrderedSet()
        if res:
            forbidden, error_func = res
            if forbidden == self:
                _debug.logic(
                    "check_access",
                    operation=operation,
                    uid=self.env.uid,
                    count=len(self),
                    forbidden=len(self),
                    reason="base_rules",
                )
                return res
            remaining -= forbidden
            forbidden_ids.update(forbidden._ids)
        elif not self:
            return None

        if operation in ("create", "unlink"):
            operation = "write"

        model_ids = defaultdict(set)
        att_model_ids = []
        field_access: dict[tuple[str, str], bool | str] = {}
        field_scoped: defaultdict[tuple[str, str], list[tuple[int, int]]] = defaultdict(
            list
        )
        remaining = remaining.sudo()
        remaining.fetch(SECURITY_FIELDS)
        for attachment in remaining:
            if (
                attachment.public
                and operation == "read"
                and not self._withholds(attachment.url, attachment.res_model)
            ):
                continue
            att_id = attachment.id
            res_model, res_id = attachment.res_model, attachment.res_id
            if not self.env.is_system():
                linked = bool(res_model and res_id)
                if not linked and attachment.create_uid.id != self.env.uid:
                    forbidden_ids.add(att_id)
                    continue
                if res_field := attachment.res_field:
                    if res_model not in self.env:
                        forbidden_ids.add(att_id)
                        continue
                    if (cache_key := (res_model, res_field)) not in field_access:
                        comodel = self.env[res_model]
                        field = comodel._fields.get(res_field)
                        field_access[cache_key] = (
                            field is not None
                            and comodel._has_field_access(field, operation)
                            and (
                                comodel._field_access_domain(field, operation) is None
                                or PER_RECORD
                            )
                        )
                    if not field_access[cache_key]:
                        forbidden_ids.add(att_id)
                        continue
                    if field_access[cache_key] is PER_RECORD and res_id:
                        field_scoped[cache_key].append((att_id, res_id))
            if res_model and res_id:
                model_ids[res_model].add(res_id)
                att_model_ids.append((att_id, (res_model, res_id)))
        forbidden_res_model_id = set(
            get_inaccessible_owners(self.env, model_ids, operation)
        )
        forbidden_ids.update(
            att_id for att_id, res in att_model_ids if res in forbidden_res_model_id
        )
        forbidden_ids.update(self._field_attachments_outside(field_scoped, operation))
        _debug.logic(
            "check_access",
            operation=operation,
            uid=self.env.uid,
            count=len(self),
            forbidden=len(forbidden_ids),
            linked_models=len(model_ids),
        )

        if forbidden_ids:
            forbidden = self.browse(forbidden_ids)
            forbidden.invalidate_recordset(SECURITY_FIELDS)
            if error_func is None:

                def error_func():
                    return AccessError(
                        self.env._(
                            "Sorry, you are not allowed to access this document. "
                            "Please contact your system administrator.\n\n"
                            "(Operation: %(operation)s)\n\n"
                            "Records: %(records)s, User: %(user)s",
                            operation=operation,
                            records=forbidden[:6],
                            user=self.env.uid,
                        )
                    )

            return forbidden, error_func
        return None

    @api.constrains("res_model", "res_id")
    def _check_circular_attachment(self) -> None:
        for record in self.sudo():
            if record.res_model == "ir.attachment" and record.id == record.res_id:
                _debug.logic("circular_attachment_refused", attachment=record.id)
                raise ValidationError(
                    self.env._(
                        "You cannot attach an attachment to itself.\n"
                        "Attachment %(record)s cannot have res_id: %(res_id)s",
                        record=record.display_name,
                        res_id=record.res_id,
                    )
                )

    def _prepare_contents(self, values: dict[str, Any]) -> dict[str, Any]:
        mimetype = values["mimetype"] = self._get_mimetype_from_values(values)
        if self._is_xml_like_mimetype(mimetype) and not self._can_store_markup():
            values["mimetype"] = "text/plain"
            _debug.logic("xml_mimetype_forced_text", original=mimetype)
        if not self.env.context.get("image_no_postprocess"):
            values = self._prepare_contents_resized(values)
        return values

    def _can_store_markup(self) -> bool:
        if self.env.context.get("attachments_mime_plainxml"):
            return False
        return self.env["ir.ui.view"].sudo(False).has_access("write")

    def _check_serving_attachments(self) -> None:
        if self.env.is_admin():
            return
        served = self.filtered(lambda a: a.type == "binary" and a.url)
        if not served:
            return
        _debug.logic(
            "serving_attachments_checked", uid=self.env.uid, served=len(served)
        )
        has_group = self.env.user.has_group
        if not any(has_group(g) for g in self.get_groups_allowed_to_serve()):
            _debug.logic(
                "serving_write_refused", uid=self.env.uid, attachments=served.ids
            )
            raise ValidationError(
                self.env._("Sorry, you are not allowed to write on this document")
            )

    @api.model
    def _is_xml_like_mimetype(self, mimetype: str) -> bool:
        if mimetype.startswith("application/vnd.openxmlformats"):
            return False
        subtype = mimetype.partition("/")[2]
        return "html" in subtype or "xml" in subtype or subtype == "hta"

    def _is_remote_source(self) -> bool:
        self.check_singleton()
        return bool(
            self.url
            and not self.file_size
            and self.url.startswith(("http://", "https://", "ftp://"))
        )

    def _is_stream_upload_required(self, mimetype: str) -> bool:
        if self.env.context.get("image_no_postprocess"):
            return True
        maintype, _, subtype = (mimetype or "").partition("/")
        if maintype != "image":
            return True
        subtypes, max_width, _height, _quality = self._get_image_autoresize_config()
        streamed = not (max_width and subtype in subtypes)
        _debug.logic("stream_upload_decided", mimetype=mimetype, streamed=streamed)
        return streamed
