import itertools
import logging
import operator
import typing
from collections import defaultdict
from typing import Any

from odoo import http
from odoo.exceptions import UserError
from odoo.http import (
    InternalServerError,
    Response,
    prepare_content_disposition_header,
    request,
)
from odoo.libs.accel import csv_export as _rust_csv_export
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import mimetype_for
from odoo.libs.filesystem import osutil
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.models import PREFETCH_MAX
from odoo.tools.authority_keys import strip_authority_keys

from .export_writers import (
    ExportXlsxWriter,
    GroupExportXlsxWriter,
    GroupsTreeNode,
)
from .utils import get_model

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_EXPORT_MAX_ROWS_DEFAULT = 100_000

_EXPORT_FIELD_ATTRIBUTES = [
    "type",
    "string",
    "required",
    "relation_field",
    "default_export_compatible",
    "relation",
    "definition_record",
    "definition_record_field",
    "exportable",
    "readonly",
]


class Export(http.Controller):
    @http.route("/web/export/formats", type="jsonrpc", auth="user", readonly=True)
    def formats(self) -> list[dict[str, Any]]:
        _debug.lifecycle("formats")
        return [
            {"tag": "xlsx", "label": "XLSX"},
            {"tag": "csv", "label": "CSV"},
        ]

    @_debug.perf.timed
    def _get_property_fields(
        self,
        fields: dict[str, dict[str, Any]],
        model: str,
        domain: list | None = None,
    ) -> dict[str, dict[str, Any]]:
        property_fields = {}
        Model = get_model(request.env, model)
        for fname, field in fields.items():
            if field.get("type") != "properties":
                continue

            definition_record = field["definition_record"]
            definition_record_field = field["definition_record_field"]

            target_model = Model.env[
                Model._fields[definition_record].comodel_name
            ].sudo()
            domain_definition = [(definition_record_field, "!=", False)]
            if domain:
                self_subquery = Model.with_context(active_test=False)._search(domain)
                field_to_get = Model._field_to_sql(
                    Model._table, definition_record, self_subquery
                )
                domain_definition.append(
                    ("id", "in", self_subquery.subselect(field_to_get))
                )
            _debug.logic(
                "property_definitions_source",
                model=model,
                field=fname,
                definition_model=target_model._name,
                definition_field=definition_record_field,
                scoped=bool(domain),
            )

            definition_records = target_model.search_fetch(  # noqa: E8507 - one query per properties field of the export
                domain_definition,
                [definition_record_field, "display_name"],
                order="id",
            )
            _debug.perf.count(
                "property_definition_records",
                model=model,
                field=fname,
                records=len(definition_records),
            )

            for record in definition_records:
                for definition in record[definition_record_field]:
                    if definition["type"] == "separator" or (
                        definition["type"] in ("many2one", "many2many")
                        and definition.get("comodel") not in Model.env
                    ):
                        continue
                    id_field = f"{fname}.{definition['name']}"
                    property_fields[id_field] = {
                        "type": definition["type"],
                        "string": Model.env._(
                            "%(property_string)s (%(parent_name)s)",
                            property_string=definition["string"],
                            parent_name=record.display_name,
                        ),
                        "default_export_compatible": field["default_export_compatible"],
                    }
                    if definition["type"] in ("many2one", "many2many"):
                        property_fields[id_field]["relation"] = definition["comodel"]

        _debug.pipeline(
            "property_fields_expanded", model=model, fields=len(property_fields)
        )
        return property_fields

    @http.route("/web/export/get_fields", type="jsonrpc", auth="user", readonly=True)
    def get_fields(
        self,
        model: str,
        domain: list,
        prefix: str = "",
        parent_name: str = "",
        import_compat: bool = True,
        parent_field_type: str | None = None,
        parent_field: dict[str, Any] | None = None,
        exclude: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        _debug.lifecycle(
            "get_fields",
            model=model,
            prefix=prefix,
            import_compat=import_compat,
            parent_type=parent_field_type,
            exclude=len(exclude or ()),
            domain_terms=len(domain),
        )

        Model = get_model(request.env, model)
        fields = Model.fields_get(attributes=_EXPORT_FIELD_ATTRIBUTES)

        _debug.perf.count("get_fields_fields_get", model=model, fields=len(fields))

        relation_name = None
        if import_compat:
            if parent_field_type in ("many2one", "many2many"):
                rec_name = Model._get_rec_name_fallback()
                if rec_name != "id":
                    relation_name = rec_name
                _debug.logic(
                    "get_fields_import_compat_relational_child",
                    model=model,
                    rec_name=rec_name,
                )
                fields = {"id": fields["id"], rec_name: fields[rec_name]}
        else:
            fields[".id"] = {**fields["id"]}

        fields["id"]["string"] = request.env._("External ID")

        if not Model._is_an_ordinary_table():
            _debug.logic("get_fields_not_ordinary_table", model=model)
            fields.pop("id", None)
        elif parent_field:
            parent_field["string"] = request.env._("External ID")
            fields["id"] = parent_field
            fields["id"]["type"] = parent_field.get("field_type")

        exportable_fields = {}
        for field_name, field in fields.items():
            if import_compat and field_name != "id":
                if exclude and field_name in exclude:
                    continue
                if field.get("readonly"):
                    continue
            if not field.get("exportable", True):
                continue
            exportable_fields[field_name] = field

        exportable_fields.update(
            self._get_property_fields(fields, model, domain=domain)
        )

        fields_sequence = sorted(
            exportable_fields.items(),
            key=lambda field: field[1]["string"].lower(),
        )
        _debug.pipeline(
            "get_fields_exportable",
            model=model,
            exportable=len(fields_sequence),
            fields=len(fields),
        )

        return [
            self._get_export_field_entry(
                field_name,
                field,
                prefix=prefix,
                parent_name=parent_name,
                import_compat=import_compat,
                relation_name=relation_name,
            )
            for field_name, field in fields_sequence
        ]

    def _get_export_field_entry(
        self,
        field_name: str,
        field: dict[str, Any],
        *,
        prefix: str,
        parent_name: str,
        import_compat: bool,
        relation_name: str | None,
    ) -> dict[str, Any]:
        ident = prefix + ("/" if prefix else "") + field_name
        # an import-compatible export names a related record by its rec_name
        # through the relation itself, which is what the import matches on
        val = prefix if field_name == relation_name else ident
        name = parent_name + ((parent_name and "/") or "") + field["string"]
        field_dict = {
            "id": ident,
            "string": name,
            "value": val,
            "children": False,
            "field_type": field.get("type"),
            "required": field.get("required"),
            "relation_field": field.get("relation_field"),
            "default_export": import_compat and field.get("default_export_compatible"),
        }
        if ident.count("/") < 2 and "relation" in field:
            field_dict["value"] += "/id"
            field_dict["params"] = {
                "model": field["relation"],
                "prefix": ident,
                "name": name,
                "parent_field": field,
            }
            field_dict["children"] = True
        return field_dict

    @http.route("/web/export/namelist", type="jsonrpc", auth="user", readonly=True)
    def namelist(self, model: str, export_id: int) -> list[dict[str, Any]]:
        _debug.lifecycle("namelist", model=model, export_id=export_id)
        export = request.env["ir.exports"].browse([export_id])
        return self._get_fields_info(model, export.export_fields.mapped("name"))

    @_debug.perf.timed
    def _get_fields_info(
        self, model: str, export_fields: list[str]
    ) -> list[dict[str, Any]]:
        _debug.pipeline("fields_info", model=model, paths=len(export_fields))
        field_info: list[dict[str, Any]] = []
        fields = get_model(request.env, model).fields_get(
            attributes=_EXPORT_FIELD_ATTRIBUTES
        )
        fields.update(self._get_property_fields(fields, model))
        if ".id" in export_fields:
            fields[".id"] = fields.get("id", {"string": "ID"})

        for (base, length), grouped in itertools.groupby(
            sorted(export_fields),
            lambda field: (field.split("/", 1)[0], len(field.split("/", 1))),
        ):
            subfields = list(grouped)
            if length == 2:
                if base not in fields or "relation" not in fields[base]:
                    _debug.logic("fields_info_stale_subpaths", model=model, base=base)
                    _logger.debug(
                        "Skipping stale export paths %s on %s: field %r is "
                        "missing or not relational",
                        subfields,
                        model,
                        base,
                    )
                    continue
                _debug.logic(
                    "fields_info_graft",
                    model=model,
                    subpaths=len(subfields),
                    base=base,
                    relation=fields[base]["relation"],
                )
                field_info.extend(
                    self._graft_subfields(
                        fields[base]["relation"],
                        base,
                        fields[base]["string"],
                        subfields,
                    ),
                )
            elif base in fields:
                field_dict = fields[base]
                field_info.append(
                    {
                        "id": base,
                        "string": field_dict["string"],
                        "field_type": field_dict["type"],
                    }
                )

        indexes_dict = {fname: i for i, fname in enumerate(export_fields)}
        return sorted(field_info, key=lambda field_dict: indexes_dict[field_dict["id"]])

    def _graft_subfields(
        self,
        model: str,
        prefix: str,
        prefix_string: str,
        fields: list[str],
    ) -> typing.Iterator[dict[str, Any]]:
        export_fields = [field.split("/", 1)[1] for field in fields]
        return (
            dict(
                field_info,
                id=f"{prefix}/{field_info['id']}",
                string=f"{prefix_string}/{field_info['string']}",
            )
            for field_info in self._get_fields_info(model, export_fields)
        )


class ExportFormat:
    format_key: str = ""

    @property
    def content_type(self) -> str:
        mimetype = mimetype_for(self.format_key)
        if not mimetype:
            raise NotImplementedError(
                f"{type(self).__name__} exports {self.format_key!r}, which no "
                f"module registers as a format"
            )
        return mimetype

    @property
    def extension(self) -> str:
        return f".{self.format_key}"

    def filename(self, base: str) -> str:
        if base not in request.env:
            _debug.logic("filename_unknown_model", model=base)
            return base

        model_description = request.env["ir.model"]._get(base).name
        return f"{model_description} ({base})"

    def from_data(
        self,
        fields: list[dict[str, Any]],
        columns_headers: list[str],
        rows: list[list[Any]],
    ) -> str | bytes:
        raise NotImplementedError

    def from_group_data(
        self,
        fields: list[dict[str, Any]],
        columns_headers: list[str],
        groups: GroupsTreeNode,
    ) -> str | bytes:
        raise NotImplementedError

    def base_response(self, data: str) -> Response:
        _debug.lifecycle("export", export_format=self.format_key, payload=len(data))
        try:
            with _debug.perf(
                "export_request", cr=request.env.cr, export_format=self.format_key
            ):
                return self.base(data)
        except Exception as exc:
            _debug.logic(
                "export_failed",
                export_format=self.format_key,
                error=type(exc).__name__,
            )
            if isinstance(exc, UserError):
                _logger.warning("%s", exc)
            else:
                _logger.exception("Exception during request handling.")
            payload = json_dumps(
                {
                    "code": 0,
                    "message": "Odoo Server Error",
                    "data": http.serialize_exception(exc),
                }
            )
            raise InternalServerError(payload) from exc

    def _check_export_order(self, Model: Any, order: str | None) -> None:
        if not order:
            return
        order_root = []
        for term in order.split(","):
            parts = term.split()
            if (
                not parts
                or len(parts) > 2
                or (len(parts) == 2 and parts[1].lower() not in ("asc", "desc"))
            ):
                raise UserError(
                    request.env._(
                        "Invalid order clause %(order)s for %(model)s.",
                        order=order,
                        model=Model._name,
                    )
                )
            order_root.append(parts[0].split(":", 1)[0])
        unknown = [
            f
            for f in order_root
            if (field := Model._fields.get(f.split(".", 1)[0])) is None
            or ("." in f and field.type != "properties")
        ]
        if unknown:
            _debug.logic(
                "export_order_unknown_fields",
                model=Model._name,
                order=order,
                unknown=unknown,
            )
            raise UserError(
                request.env._(
                    "Unknown order fields for %(model)s: %(fields)s",
                    model=Model._name,
                    fields=", ".join(unknown),
                )
            )

    def _check_export_fields(self, Model: Any, field_names: list[str]) -> None:
        unknown = []
        for name in field_names:
            model = Model
            for part in name.split("/"):
                if part in ("id", ".id"):
                    break
                field = model._fields.get(part.split(".", 1)[0])
                if field is None:
                    unknown.append(name)
                    break
                if not field.relational:
                    break
                model = model.env[field.comodel_name]
        if unknown:
            _debug.logic(
                "export_unknown_field_paths", model=Model._name, unknown=unknown
            )
            raise UserError(
                request.env._(
                    "Unknown fields for %(model)s: %(fields)s",
                    model=Model._name,
                    fields=", ".join(unknown),
                )
            )

    def _iter_export_rows(
        self, Model: Any, records: Any, field_names: list[str]
    ) -> typing.Iterator[list]:
        batches = rows = 0
        for batch_ids in itertools.batched(records.ids, PREFETCH_MAX, strict=False):
            batch = Model.browse(batch_ids)
            with _debug.perf(
                "export_data_batch", cr=Model.env.cr, model=Model._name, batch=batches
            ):
                batch_rows = batch.export_data(field_names).get("datas", [])
            batch.invalidate_recordset()
            batches += 1
            rows += len(batch_rows)
            yield from batch_rows
        _debug.pipeline(
            "export_rows",
            model=Model._name,
            records=len(records),
            rows=rows,
            batches=batches,
            batch_size=PREFETCH_MAX,
        )

    def _get_export_groups_tree(
        self,
        Model: Any,
        records: Any,
        field_names: list[str],
        groupby: list[str],
        ids: list[int] | None,
        domain: list,
    ) -> GroupsTreeNode:
        groupby_root = [x.split(":", 1)[0].split(".", 1)[0] for x in groupby]
        unknown = [f for f in groupby_root if f not in Model._fields]
        if unknown:
            _debug.logic(
                "export_groupby_unknown_fields",
                model=Model._name,
                groupby=groupby,
                unknown=unknown,
            )
            raise UserError(
                request.env._(
                    "Unknown groupby fields for %(model)s: %(fields)s",
                    model=Model._name,
                    fields=", ".join(unknown),
                )
            )
        groupby_type = [Model._fields[f].type for f in groupby_root]
        tree = GroupsTreeNode(Model, field_names, groupby, groupby_type)
        if ids:
            domain = [("id", "in", ids)]
            SearchModel = Model.with_context(active_test=False)
        else:
            SearchModel = Model
        _debug.logic(
            "export_grouped",
            model=Model._name,
            groupby=groupby,
            groupby_type=groupby_type,
            scope="ids" if ids else "domain",
        )
        with _debug.perf(
            "export_formatted_read_group", cr=Model.env.cr, model=Model._name
        ):
            groups_data = SearchModel.formatted_read_group(
                domain, groupby, ["__count", "id:array_agg"]
            )

        record_rows: dict[int, list[list[Any]]] = {}
        current_id = None
        with _debug.perf("export_grouped_data", cr=Model.env.cr, model=Model._name):
            for row in self._iter_export_rows(Model, records, [".id", *field_names]):
                if row[0]:
                    current_id = int(row[0])
                    record_rows[current_id] = []
                record_rows[current_id].append(row[1:])

        groups = [group["id:array_agg"] for group in groups_data]
        record_to_group = defaultdict(list)
        for group_index, group_record_ids in enumerate(groups):
            for record_id in group_record_ids:
                record_to_group[record_id].append(group_index)

        grouped_rows: list[list[list[Any]]] = [[] for _ in groups]
        for record_id, rows in record_rows.items():
            for group_index in record_to_group[record_id]:
                grouped_rows[group_index].extend(rows)

        for group_info, group_rows in zip(groups_data, grouped_rows, strict=True):
            tree.add_leaf(group_info, group_rows)
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "export_groups_tree",
                model=Model._name,
                groups=len(groups),
                records=len(record_rows),
                rows=sum(len(rows) for rows in grouped_rows),
                count=tree.count,
            )
        return tree

    def base(self, data: str) -> Response:
        params = json_loads(data)
        model, fields, ids, domain, import_compat = operator.itemgetter(
            "model", "fields", "ids", "domain", "import_compat"
        )(params)

        Model = get_model(request.env, model).with_context(
            import_compat=import_compat,
            **strip_authority_keys(params.get("context", {}), door="export"),
        )
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "export_params",
                model=model,
                export_format=self.format_key,
                fields=len(fields),
                ids=len(ids or ()),
                domain_terms=len(domain or ()),
                import_compat=import_compat,
                groupby=params.get("groupby"),
                order=params.get("order"),
                context=sorted(params.get("context", {})),
            )
        if not Model._is_an_ordinary_table():
            _debug.logic("export_not_ordinary_table", model=model)
            fields = [field for field in fields if field["name"] != "id"]

        field_names = [f["name"] for f in fields]
        self._check_export_fields(Model, field_names)
        if import_compat:
            columns_headers = field_names
        else:
            columns_headers = [val["label"].strip() for val in fields]

        order = params.get("order") or None
        self._check_export_order(Model, order)

        if ids:
            records = Model.browse(ids)
        else:
            max_rows = int(
                request.env.registry.settings.get(
                    request.env, "web.export_max_rows", _EXPORT_MAX_ROWS_DEFAULT
                )
            )
            with _debug.perf(
                "export_search", cr=Model.env.cr, model=model, limit=max_rows
            ):
                records = Model.search(domain, order=order, limit=max_rows + 1)
            _debug.logic(
                "export_search_result", model=model, records=len(records), cap=max_rows
            )
            if len(records) > max_rows:
                raise UserError(
                    request.env._(
                        "This export has more than %(limit)s records. Narrow the "
                        "search, or ask an administrator to raise the "
                        "web.export_max_rows limit.",
                        limit=max_rows,
                    )
                )

        groupby = params.get("groupby")
        if not import_compat and groupby:
            tree = self._get_export_groups_tree(
                Model, records, field_names, groupby, ids, domain
            )
            with _debug.perf(
                "export_from_group_data",
                cr=Model.env.cr,
                model=model,
                export_format=self.format_key,
            ):
                response_data = self.from_group_data(fields, columns_headers, tree)
        else:
            all_rows = list(self._iter_export_rows(Model, records, field_names))
            with _debug.perf(
                "export_from_data",
                cr=Model.env.cr,
                model=model,
                export_format=self.format_key,
            ):
                response_data = self.from_data(fields, columns_headers, all_rows)
        _debug.perf.count(
            "export_size",
            model=model,
            export_format=self.format_key,
            size=len(response_data),
        )

        _logger.info(
            "User %d exported %d %r records from %s. Fields: %s. %s: %s",
            request.env.user.id,
            len(records.ids),
            records._name,
            request.httprequest.remote_addr,
            ",".join(field_names),
            "IDs sample" if ids else "Domain",
            records.ids[:10] if ids else domain,
        )

        return request.prepare_response(
            response_data,
            headers=[
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(
                        osutil.clean_filename(self.filename(model) + self.extension)
                    ),
                ),
                ("Content-Type", self.content_type),
            ],
        )


class CSVExport(ExportFormat, http.Controller):
    format_key = "csv"

    @http.route("/web/export/csv", type="http", auth="user", readonly=True)
    def web_export_csv(self, data: str) -> Response:
        return self.base_response(data)

    @property
    def content_type(self) -> str:
        return f"{super().content_type}; charset=utf-8"

    def from_group_data(
        self,
        fields: list[dict[str, Any]],
        columns_headers: list[str],
        groups: GroupsTreeNode,
    ) -> str | bytes:
        _debug.logic("csv_grouped_export_refused")
        raise UserError(
            request.env._("Exporting grouped data to csv is not supported.")
        )

    def from_data(
        self,
        fields: list[dict[str, Any]],
        columns_headers: list[str],
        rows: list[list[Any]],
    ) -> bytes:
        return _rust_csv_export(columns_headers, rows)


class ExcelExport(ExportFormat, http.Controller):
    format_key = "xlsx"

    @http.route("/web/export/xlsx", type="http", auth="user", readonly=True)
    def web_export_xlsx(self, data: str) -> Response:
        return self.base_response(data)

    def from_group_data(
        self,
        fields: list[dict[str, Any]],
        columns_headers: list[str],
        groups: GroupsTreeNode,
    ) -> bytes:
        with GroupExportXlsxWriter(
            fields, columns_headers, groups.count
        ) as xlsx_writer:
            row, column = 1, 0
            for group_name, group in groups.children.items():
                row, column = xlsx_writer.write_group(row, column, group_name, group)
        _debug.pipeline(
            "xlsx_grouped_written", top_groups=len(groups.children), rows=row
        )

        return xlsx_writer.value

    def from_data(
        self,
        fields: list[dict[str, Any]],
        columns_headers: list[str],
        rows: list[list[Any]],
    ) -> bytes:
        with ExportXlsxWriter(fields, columns_headers, len(rows)) as xlsx_writer:
            for row_index, row in enumerate(rows):
                for cell_index, cell_value in enumerate(row):
                    xlsx_writer.write_cell(row_index + 1, cell_index, cell_value)

        return xlsx_writer.value
