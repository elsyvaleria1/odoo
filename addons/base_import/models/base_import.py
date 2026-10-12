import base64
import collections
import contextlib
import csv
import datetime
import difflib
import functools
import hashlib
import importlib.util
import io
import itertools
import logging
import operator
import re
import threading
import unicodedata
from collections.abc import Sequence
from pathlib import Path

import psycopg
from PIL import Image

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.documents import (
    ROWS,
    BaseReader,
    decode,
    guess_encoding,
    mimetype_for,
    mimetypes_for,
    normalize_number,
    register_reader,
    strip_currency_symbol,
)
from odoo.libs.filesystem import guess_mimetype
from odoo.tools import (
    DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_DATETIME_FORMAT,
    config,
)
from odoo.tools.translate import LazyGettext, LazyTranslate

FIELDS_RECURSION_LIMIT = 3
ERROR_PREVIEW_BYTES = 200
DEFAULT_CHUNK_SIZE = 32768
SEPARATOR_SNIFF_ROWS = 100
_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)
MIMETYPE_TO_READER = {
    mimetype_for(extension): extension for extension in ("csv", "xls", "xlsx", "ods")
}

EXTENSION_TO_READER = {
    "csv": "_read_csv",
    "ods": "_read_ods",
    "xls": "_read_xls",
    "xlsm": "_read_xlsx",
    "xlsx": "_read_xlsx",
}

PARSE_OPTION_KEYS = ("encoding", "separator", "quoting", "sheet")
PARSE_OPTION_OUTPUTS = (*PARSE_OPTION_KEYS, "sheets")
PARSED_FILE_CACHE_ENTRIES = 4
PARSED_FILE_CACHE_MAX_CELLS = 500_000


def _copy_option_outputs(outputs) -> dict:
    return {
        name: list(value) if isinstance(value, list) else value
        for name, value in outputs.items()
    }


class _ParsedFileCache:
    def __init__(self, entries, max_cells) -> None:
        self._entries = entries
        self._max_cells = max_cells
        self._store = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._store.get(key)
            if hit is not None:
                self._store.move_to_end(key)
            return hit

    def set(self, key, rows, outputs):
        if sum(len(row) for row in rows) > self._max_cells:
            return
        with self._lock:
            self._store[key] = (rows, outputs)
            self._store.move_to_end(key)
            while len(self._store) > self._entries:
                self._store.popitem(last=False)

    def clear(self):
        with self._lock:
            self._store.clear()


PARSED_FILE_CACHE = _ParsedFileCache(
    PARSED_FILE_CACHE_ENTRIES, PARSED_FILE_CACHE_MAX_CELLS
)

CONCAT_SEPARATOR_IMPORT = {
    "char": " ",
    "text": "\n",
    "html": "<br>",
    "many2many": ",",
}


class _StoredCurrencySymbols:
    def __init__(self, env) -> None:
        self.env = env

    def __contains__(self, symbol) -> bool:
        return bool(
            self.env["res.currency"].search_count([("symbol", "=", symbol)], limit=1)
        )


class ImportValidationError(Exception):
    def __init__(self, message, **kwargs) -> None:
        super().__init__(message)
        self.type = kwargs.get("error_type", "error")
        self.message = message
        self.record = False
        self.not_matching_error = True
        self.field_path = [kwargs["field"]] if kwargs.get("field") else False
        self.field_type = kwargs.get("field_type")


def read_xls_rows(data, options):
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    sheets = options["sheets"] = book.sheet_names()
    sheet_name = options["sheet"] = options.get("sheet") or sheets[0]
    sheet = book.sheet_by_name(sheet_name)
    rows = []
    for rowx, row in enumerate(map(sheet.row, range(sheet.nrows)), 1):
        values = []
        for colx, cell in enumerate(row, 1):
            if cell.ctype is xlrd.XL_CELL_NUMBER:
                if cell.value % 1 == 0:
                    values.append(str(int(cell.value)))
                else:
                    values.append(str(cell.value))
            elif cell.ctype is xlrd.XL_CELL_DATE:
                dt = datetime.datetime(
                    *xlrd.xldate.xldate_as_tuple(cell.value, book.datemode)
                )
                values.append(dt if cell.value % 1 else dt.date())
            elif cell.ctype is xlrd.XL_CELL_BOOLEAN:
                values.append("True" if cell.value else "False")
            elif cell.ctype is xlrd.XL_CELL_ERROR:
                raise ImportValidationError(
                    _lt(
                        "Invalid cell value at row %(row)s, column %(col)s: %(cell_value)s",
                        row=rowx,
                        col=colx,
                        cell_value=xlrd.error_text_from_code.get(
                            cell.value, _lt("unknown error code %s", cell.value)
                        ),
                    )
                )
            else:
                values.append(cell.value)
        if any(x and (not isinstance(x, str) or x.strip()) for x in values):
            rows.append(values)
    return rows


def read_xlsx_rows(data, options):
    import openpyxl
    import openpyxl.cell.cell as types
    import openpyxl.styles.numbers as styles

    from .zip_guard import check_zip_member_sizes

    check_zip_member_sizes(io.BytesIO(data))
    book = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheets = options["sheets"] = book.sheetnames
        sheet_name = options["sheet"] = options.get("sheet") or sheets[0]
        sheet = book[sheet_name]
        rows = []
        for rowx, row in enumerate(sheet.rows, 1):
            values = []
            for colx, cell in enumerate(row, 1):
                if cell.data_type == types.TYPE_ERROR:
                    raise ImportValidationError(
                        _lt(
                            "Invalid cell value at row %(row)s, column %(col)s: %(cell_value)s",
                            row=rowx,
                            col=colx,
                            cell_value=cell.value,
                        )
                    )

                if cell.value is None:
                    values.append("")
                elif isinstance(cell.value, float):
                    if cell.value % 1 == 0:
                        values.append(str(int(cell.value)))
                    else:
                        values.append(str(cell.value))
                elif cell.is_date:
                    d_fmt = styles.is_datetime(cell.number_format)
                    if d_fmt == "datetime":
                        values.append(cell.value)
                    elif d_fmt == "date":
                        values.append(cell.value.date())
                    else:
                        raise ImportValidationError(
                            _lt(
                                "Invalid cell format at row %(row)s, column %(col)s: %(cell_value)s, with format: %(cell_format)s, as (%(format_type)s) formats are not supported.",
                                row=rowx,
                                col=colx,
                                cell_value=cell.value,
                                cell_format=cell.number_format,
                                format_type=d_fmt,
                            )
                        )
                else:
                    values.append(str(cell.value))

            if any(x and (not isinstance(x, str) or x.strip()) for x in values):
                rows.append(values)
        return rows
    finally:
        book.close()


class _SpreadsheetReader(BaseReader):
    module = "base_import"

    yields = (ROWS,)

    def __init__(self, name, mimetypes, reader, module) -> None:
        self.name = name
        self.mimetypes = frozenset(mimetypes)
        self._reader = reader
        self._module = module

    def read(self, document):
        return self._reader(document.data, document.options)

    def provides(self, document):
        return importlib.util.find_spec(self._module) is not None


def read_ods_rows(data, options):
    from . import odf_ods_reader

    doc = odf_ods_reader.ODSReader(file=io.BytesIO(data))
    sheets = options["sheets"] = list(doc.sheets)
    if not sheets:
        raise ImportValidationError(_lt("Import file has no content or is corrupt"))
    sheet = options.get("sheet")
    if sheet not in doc.sheets:
        sheet = sheets[0]
    options["sheet"] = sheet

    return doc.get_sheet(sheet)


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def get_import_templates(self):
        return []


class Base_ImportMapping(models.Model):
    _name = "base_import.mapping"
    _description = "Base Import Mapping"

    res_model = fields.Char(
        index=True,
        required=True,
    )
    column_name = fields.Char(required=True)
    field_name = fields.Char(required=True)

    _column_unique_per_model = models.Constraint(
        "UNIQUE(res_model, column_name)",
        "A column name can only be mapped to one field per model.",
    )


class ResUsers(models.Model):
    _inherit = "res.users"

    def _can_import_remote_urls(self) -> bool:
        self.check_singleton()
        return self._is_admin()


class Base_ImportImport(models.TransientModel):
    _name = "base_import.import"
    _description = "Base Import"

    _transient_max_hours = 12.0
    FUZZY_MATCH_DISTANCE = 0.2

    res_model = fields.Char(string="Model")
    file = fields.Binary(
        attachment=False,
        help="File to check and/or import, raw binary (not base64)",
    )
    file_name = fields.Char()
    file_type = fields.Char()

    @api.model
    def get_fields_tree(self, model, depth=FIELDS_RECURSION_LIMIT):
        depth = min(depth, FIELDS_RECURSION_LIMIT)
        self._check_model_name(model)
        self.env[model].check_access("read")
        return self._get_fields_tree(model, depth)

    @api.model
    def _check_model_name(self, model):
        if not model or model not in self.env:
            raise UserError(
                self.env._(
                    "Cannot import into %(model)s: no such model.",
                    model=model or self.env._("(none)"),
                )
            )

    def _expand_properties_fields(self, Model, model_fields) -> None:
        for name, field in dict(model_fields).items():
            if field["type"] != "properties":
                continue
            definition_record = field["definition_record"]
            definition_record_field = field["definition_record_field"]

            target_model = Model.env[Model._fields[definition_record].comodel_name]

            if not target_model.has_access("read"):
                continue
            if not target_model._has_field_access(
                target_model._fields[definition_record_field], "read"
            ):
                continue

            definition_records = target_model.search_fetch(  # noqa: E8507 -- one query per properties field of the import
                [(definition_record_field, "!=", False)],
                [definition_record_field, "display_name"],
                order="id",
            )

            for record in definition_records:
                for definition in record[definition_record_field]:
                    definition_type = definition["type"]
                    if definition_type == "separator" or (
                        definition_type in ("many2one", "many2many")
                        and definition.get("comodel") not in Model.env
                    ):
                        continue
                    id_field = f"{name}.{definition['name']}"
                    model_fields[id_field] = {
                        "type": definition_type,
                        "string": self.env._(
                            "%(property_string)s (%(parent_name)s)",
                            property_string=definition["string"],
                            parent_name=record.display_name,
                        ),
                    }
                    if definition_type in ("many2one", "many2many"):
                        model_fields[id_field]["relation"] = definition["comodel"]
                    elif definition_type == "selection":
                        model_fields[id_field]["selection"] = (
                            definition.get("selection") or []
                        )

    def _get_field_tree_node(self, model, name, field, depth):
        field_value = {
            "id": name,
            "name": name,
            "string": field["string"],
            "required": bool(field.get("required")),
            "fields": [],
            "type": field["type"],
            "model_name": model,
        }

        if field["type"] == "selection":
            field_value["selection"] = field.get("selection") or []

        if field["type"] in ("many2many", "many2one"):
            field_value["fields"] = [
                dict(
                    field_value,
                    model_name=field["relation"],
                    name="id",
                    string=self.env._("External ID"),
                    type="id",
                ),
                dict(
                    field_value,
                    model_name=field["relation"],
                    name=".id",
                    string=self.env._("Database ID"),
                    type="id",
                ),
            ]
            field_value["comodel_name"] = field["relation"]
        elif field["type"] == "one2many":
            field_value["fields"] = self._get_fields_tree(
                field["relation"], depth=depth - 1
            )
            if self.env.user.has_group("base.group_no_one"):
                field_value["fields"].append(
                    dict(
                        field_value,
                        model_name=field["relation"],
                        fields=[],
                        name=".id",
                        string=self.env._("Database ID"),
                        type="id",
                    )
                )
            field_value["comodel_name"] = field["relation"]

        return field_value

    def _get_fields_tree(self, model, depth):
        Model = self.env[model]
        importable_fields = [
            {
                "id": "id",
                "name": "id",
                "string": self.env._("External ID"),
                "required": False,
                "fields": [],
                "type": "id",
                "model_name": model,
            }
        ]
        if not depth:
            return importable_fields

        model_fields = Model.fields_get(
            attributes=[
                "string",
                "required",
                "type",
                "readonly",
                "relation",
                "selection",
                "definition_record",
                "definition_record_field",
            ]
        )
        self._expand_properties_fields(Model, model_fields)

        for name, field in model_fields.items():
            if name in models.MAGIC_COLUMNS or field.get("readonly"):
                continue
            importable_fields.append(
                self._get_field_tree_node(model, name, field, depth)
            )

        return importable_fields

    def _filter_fields_by_types(self, model_fields_tree, header_types):
        if "all" in header_types:
            return model_fields_tree

        most_likely_fields_tree = []
        for field in model_fields_tree:
            subfields = field.get("fields")
            if subfields:
                filtered_field = dict(field)
                filtered_field["fields"] = self._filter_fields_by_types(
                    subfields, header_types
                )
                most_likely_fields_tree.append(filtered_field)
            elif field.get("type") in header_types:
                most_likely_fields_tree.append(field)
        return most_likely_fields_tree

    @api.model
    def _normalize_row_window_options(self, options):
        for name in ("skip", "limit"):
            if name not in options:
                continue
            value = options[name]
            if not value:
                options[name] = 0 if name == "skip" else None
                continue
            if isinstance(value, bool) or not isinstance(value, int | str):
                raise ImportValidationError(self._bad_row_window_message(name, value))
            try:
                coerced = int(value)
            except ValueError:
                raise ImportValidationError(
                    self._bad_row_window_message(name, value)
                ) from None
            if coerced < 0:
                raise ImportValidationError(self._bad_row_window_message(name, value))
            options[name] = coerced
        return options

    @api.model
    def _bad_row_window_message(self, name, value) -> str:
        labels = {
            "skip": self.env._("Start at line"),
            "limit": self.env._("Batch limit"),
        }
        return self.env._(
            "%(option)s must be a whole number of rows, not %(value)s.",
            option=labels[name],
            value=value,
        )

    def _read_file(self, options):
        self.check_singleton()

        key = self._parsed_file_key(options)
        hit = PARSED_FILE_CACHE.get(key)
        if hit is not None:
            rows, outputs = hit
            options.update(_copy_option_outputs(outputs))
            return list(rows)

        before = {name: options.get(name) for name in PARSE_OPTION_OUTPUTS}
        rows = self._read_file_uncached(options)
        outputs = {
            name: options[name]
            for name in PARSE_OPTION_OUTPUTS
            if name in options and options[name] != before[name]
        }
        PARSED_FILE_CACHE.set(key, rows, _copy_option_outputs(outputs))
        return list(rows)

    def _parsed_file_key(self, options) -> tuple:
        return (
            hashlib.blake2b(self.file or b"", digest_size=16).digest(),
            self.file_name or "",
            self.file_type or "",
            tuple(options.get(name) for name in PARSE_OPTION_KEYS),
        )

    def _read_file_uncached(self, options):
        mimetype = guess_mimetype(self.file or b"")
        extensions_to_try = [
            (MIMETYPE_TO_READER.get(mimetype), f"guessed using mimetype {mimetype!r}"),
            (
                MIMETYPE_TO_READER.get(self.file_type),
                f"decided from user-provided mimetype {self.file_type!r}",
            ),
        ]
        if self.file_name:
            ext = Path(self.file_name).suffix
            extensions_to_try.append(
                (ext.removeprefix(".").lower(), f"decided from file extension {ext!r}")
            )

        e = None
        requires = None
        requires_extension = None
        tried_extensions = set()
        for file_extension, guess_message in extensions_to_try:
            if not file_extension or file_extension in tried_extensions:
                continue
            tried_extensions.add(file_extension)
            handler_name = EXTENSION_TO_READER.get(file_extension)
            if not handler_name:
                continue
            try:
                return getattr(self, handler_name)(options)
            except ImportError as exc:
                requires = str(getattr(exc, "name_from", None) or exc.name)
                requires_extension = file_extension
            except ImportValidationError, UserError, ValueError:
                raise
            except Exception as exc:
                e = _prepare_read_file_error(
                    exc,
                    f"Unable to read file {self.file_name or '<unknown>'!r} as {file_extension!r} ({guess_message}).",
                )

        if e is not None:
            raise e

        if requires:
            raise UserError(
                self.env._(
                    'Unable to load "%(extension)s" file: requires Python module "%(modname)s"',
                    extension=requires_extension,
                    modname=requires,
                )
            )
        raise UserError(
            self.env._(
                'Unsupported file format "%(file_type)s", import only supports %(supported)s',
                file_type=self.file_type or (self.file_name or ""),
                supported=", ".join(sorted(EXTENSION_TO_READER)),
            )
        )

    def _check_csv_quoting(self, options):
        quoting = options.setdefault("quoting", '"')
        if not isinstance(quoting, str) or len(quoting) != 1:
            raise ImportValidationError(
                self.env._(
                    "Error while importing records: Text Delimiter should be a single character."
                )
            )
        return quoting

    def _decode_csv_text(self, csv_data, options):
        encoding = options.get("encoding")
        encoding_guessed = not encoding
        if encoding_guessed:
            encoding = guess_encoding(csv_data)
            if not encoding:
                raise ImportValidationError(
                    self.env._(
                        "Could not detect the file's encoding, please select it manually."
                    )
                )
            options["encoding"] = encoding

        try:
            return decode(csv_data, encoding)
        except UnicodeDecodeError as exc:
            if encoding_guessed:
                msg = self.env._(
                    "There was an issue decoding the file using encoding “%s”.\nThis encoding was automatically detected.",
                    encoding,
                )
            else:
                msg = self.env._(
                    "There was an issue decoding the file using encoding “%s”.\nThis encoding was manually selected.",
                    encoding,
                )
            raise ImportValidationError(msg) from exc

    def _guess_csv_separator(self, csv_text, quoting, options):
        for candidate in (
            ",",
            ";",
            "\t",
            " ",
            "|",
            unicodedata.lookup("unit separator"),
        ):
            it = csv.reader(
                io.StringIO(csv_text), quotechar=quoting, delimiter=candidate
            )
            w = None
            for row in itertools.islice(it, SEPARATOR_SNIFF_ROWS):
                width = len(row)
                if w is None:
                    w = width
                if width == 1 or width != w:
                    break
            else:
                options["separator"] = candidate
                return candidate
        return ","

    def _read_xls(self, options):
        return read_xls_rows(self.file or b"", options)

    def _read_xlsx(self, options):
        return read_xlsx_rows(self.file or b"", options)

    def _read_ods(self, options):
        return read_ods_rows(self.file or b"", options)

    def _read_csv(self, options):
        quoting = self._check_csv_quoting(options)

        csv_data = self.file or b""
        if not csv_data:
            return []

        csv_text = self._decode_csv_text(csv_data, options)
        separator = options.get("separator") or self._guess_csv_separator(
            csv_text, quoting, options
        )

        csv_iterator = csv.reader(
            io.StringIO(csv_text), quotechar=quoting, delimiter=separator
        )

        return [row for row in csv_iterator if any(x for x in row if x.strip())]

    @api.model
    def _match_float_separators(self, preview_values, options) -> bool:
        thousand_separator = decimal_separator = False
        currency_symbols = None
        for val in preview_values:
            val = val.strip()
            if not val:
                continue
            if currency_symbols is None:
                currency_symbols = self._currency_symbols()
            val = self._remove_currency_symbol(val, currency_symbols)
            if not val:
                return False
            if options.get("float_thousand_separator") and options.get(
                "float_decimal_separator"
            ):
                if options["float_decimal_separator"] == "." and val.count(".") > 1:
                    return False
                val = val.replace(options["float_thousand_separator"], "").replace(
                    options["float_decimal_separator"], "."
                )
            elif val.count(".") > 1:
                options["float_thousand_separator"] = "."
                options["float_decimal_separator"] = ","
            elif val.count(",") > 1:
                options["float_thousand_separator"] = ","
                options["float_decimal_separator"] = "."
            elif val.find(".") > val.find(","):
                thousand_separator = ","
                decimal_separator = "."
            elif val.find(",") > val.find("."):
                thousand_separator = "."
                decimal_separator = ","
        if thousand_separator and not options.get("float_decimal_separator"):
            options["float_thousand_separator"] = thousand_separator
            options["float_decimal_separator"] = decimal_separator
        return True

    def _match_string_column_types(self, preview_values, options):
        values = set(preview_values)
        if values == {""}:
            return ["all"]

        if all(v.startswith("__export__") for v in values):
            return ["id", "many2many", "many2one", "one2many"]

        if all(_is_integer_literal(v) for v in values if v):
            field_type = ["integer", "float", "monetary"]
            if {"0", "1", ""}.issuperset(values):
                field_type.append("boolean")
            return field_type

        if all(
            val.lower() in ("true", "false", "t", "f", "") for val in preview_values
        ):
            return ["boolean"]

        if self._match_float_separators(preview_values, options):
            return ["float", "monetary"]

        return None

    def _extract_header_types(self, preview_values, options):
        if not preview_values:
            return ["all"]

        if all(isinstance(v, str) for v in preview_values):
            preview_values = [v.strip() for v in preview_values]
            field_types = self._match_string_column_types(preview_values, options)
            if field_types:
                return field_types

        if _is_native_date_column(preview_values):
            return ["date", "datetime"]

        results = self._try_match_date_time(preview_values, options)
        if results:
            return results

        return ["text", "char", "binary", "selection", "html", "tags"]

    def _try_match_date_time(self, preview_values, options) -> list:
        date_patterns = [options["date_format"]] if options.get("date_format") else []
        user_date_format = (
            self.env["res.lang"]._get_data(code=self.env.user.lang).date_format
        )
        if user_date_format:
            try:
                to_re(user_date_format)
                date_patterns.append(user_date_format)
            except KeyError:
                pass
        date_patterns.extend(DATE_PATTERNS)
        match = get_matching_pattern(date_patterns, preview_values)
        if match:
            options["date_format"] = match
            return ["date", "datetime"]

        datetime_patterns = (
            [options["datetime_format"]] if options.get("datetime_format") else []
        )
        datetime_patterns.extend(
            "%s %s" % (d, t) for d in date_patterns for t in TIME_PATTERNS
        )
        match = get_matching_pattern(datetime_patterns, preview_values)
        if match:
            options["datetime_format"] = match
            return ["datetime"]

        return []

    @api.model
    def _extract_headers_types(self, headers, preview, options):
        headers_types = {}
        for column_index, header_name in enumerate(headers):
            preview_values = [
                record[column_index] if column_index < len(record) else ""
                for record in preview
            ]
            type_field = self._extract_header_types(preview_values, options)
            headers_types[(column_index, header_name)] = type_field
        return headers_types

    def _get_saved_mapping_suggestion(
        self, header, fields_tree, mapping_fields
    ) -> dict:
        mapping_field_name = mapping_fields.get(_normalize_column_name(header))
        if mapping_field_name and self._mapping_path_exists(
            mapping_field_name, fields_tree
        ):
            return {
                "field_path": mapping_field_name.split("/"),
                "distance": -1,
            }
        return {}

    def _get_exact_field_match(self, header, fields_tree, field_strings_en):
        for field in fields_tree:
            fname = field["name"]
            if header.casefold() == fname.casefold():
                return field
            if header.casefold() == field["string"].casefold():
                return field
            strings_en = field_strings_en(field["model_name"])
            if (
                fname in strings_en
                and header.casefold() == strings_en[fname].casefold()
            ):
                return field
        return None

    def _get_fuzzy_field_match(
        self, header, fields_tree, header_types, field_strings_en
    ) -> dict:
        filtered_fields = self._filter_fields_by_types(fields_tree, header_types)
        if not filtered_fields:
            return {}

        min_dist = 1
        min_dist_field = False
        for field in filtered_fields:
            fname = field["name"]
            distances = [
                self._get_distance(header.casefold(), fname.casefold()),
                self._get_distance(header.casefold(), field["string"].casefold()),
            ]

            if field_string_en := field_strings_en(field["model_name"]).get(fname):
                distances.append(
                    self._get_distance(header.casefold(), field_string_en.casefold()),
                )

            current_field_dist = min(distances)
            if current_field_dist < min_dist:
                min_dist_field = fname
                min_dist = current_field_dist

        if min_dist < self.FUZZY_MATCH_DISTANCE:
            return {"field_path": [min_dist_field], "distance": min_dist}

        return {}

    def _get_relational_mapping_suggestion(
        self, header, fields_tree, header_types
    ) -> dict:
        field_path = []
        subfields_tree = fields_tree
        for sub_header in header.split("/"):
            match = self._get_mapping_suggestion(
                sub_header.strip(), subfields_tree, header_types, {}
            )
            if not match:
                return {}
            field_name = match["field_path"][0]
            subfields_tree = next(
                item["fields"] for item in subfields_tree if item["name"] == field_name
            )
            field_path.append(field_name)
        return {"field_path": field_path}

    def _get_mapping_suggestion(
        self, header, fields_tree, header_types, mapping_fields
    ):
        if not fields_tree:
            return {}

        if saved_match := self._get_saved_mapping_suggestion(
            header, fields_tree, mapping_fields
        ):
            return saved_match

        if "/" in header:
            return self._get_relational_mapping_suggestion(
                header, fields_tree, header_types
            )

        field_strings_en = self._get_field_strings_en()

        if field := self._get_exact_field_match(header, fields_tree, field_strings_en):
            return {"field_path": [field["name"]], "distance": 0}

        return self._get_fuzzy_field_match(
            header, fields_tree, header_types, field_strings_en
        )

    def _get_field_strings_en(self):
        IrModelFieldsUs = self.with_context(lang="en_US").env["ir.model.fields"]

        @functools.cache
        def get_field_string(model_name):
            return IrModelFieldsUs.get_field_string(model_name)

        return get_field_string

    def _mapping_path_exists(self, field_path, fields_tree) -> bool:
        subtree = fields_tree
        for name in field_path.split("/"):
            match = next((f for f in subtree if f["name"] == name), None)
            if match is None:
                return False
            subtree = match.get("fields") or []
        return True

    def _get_distance(self, a, b):
        return 1 - difflib.SequenceMatcher(None, a, b).ratio()

    def _get_mapping_suggestions(self, headers, header_types, fields_tree):
        mapping_suggestions = {}
        mapping_records = self.env["base_import.mapping"].search_read(
            [("res_model", "=", self.res_model)], ["column_name", "field_name"]
        )
        mapping_fields = {
            _normalize_column_name(rec["column_name"]): rec["field_name"]
            for rec in mapping_records
        }
        for index, header in enumerate(headers):
            match_field = self._get_mapping_suggestion(
                header, fields_tree, header_types[(index, header)], mapping_fields
            )
            mapping_suggestions[(index, header)] = match_field or None

        self._deduplicate_mapping_suggestions(mapping_suggestions)
        return mapping_suggestions

    def _deduplicate_mapping_suggestions(self, mapping_suggestions) -> None:
        min_dist_per_field = {}
        headers_to_keep = []
        for header, suggestion in mapping_suggestions.items():
            if suggestion is None or len(suggestion["field_path"]) > 1:
                headers_to_keep.append(header)
                continue

            field_name = suggestion["field_path"][0]
            field_distance = suggestion["distance"]

            best_distance, _best_header = min_dist_per_field.get(field_name, (1, None))
            if field_distance < best_distance:
                min_dist_per_field[field_name] = (field_distance, header)

        headers_to_keep += [value[1] for value in min_dist_per_field.values()]
        for header in mapping_suggestions.keys() - headers_to_keep:
            del mapping_suggestions[header]

    def _get_preview_matches(self, headers, header_types, fields_tree, options):
        matches = {}
        if options.get("keep_matches") and options.get("fields"):
            for index, match in enumerate(options.get("fields", [])):
                if match:
                    matches[index] = match.split("/")
        elif options.get("has_headers"):
            suggestions = self._get_mapping_suggestions(
                headers, header_types, fields_tree
            )
            matches = {
                header_key[0]: suggestion["field_path"]
                for header_key, suggestion in suggestions.items()
                if suggestion
            }
        return matches

    def _is_advanced_mode(self, headers, matches, options) -> bool:
        if options.get("keep_matches"):
            return bool(options.get("advanced"))
        has_relational_header = any(
            len(models.fix_import_export_id_paths(col)) > 1 for col in headers
        )
        has_relational_match = any(
            len(match) > 1 for match in matches.values() if match
        )
        return has_relational_header or has_relational_match

    def _prepare_error_message(self, error) -> str:
        message = error.args[0] if error.args else ""
        if isinstance(message, LazyGettext):
            return self.env._(message)  # noqa: E8502 -- a LazyGettext, extracted where _lt declares it
        return str(error)

    def _get_preview_error(self, error) -> dict:
        if isinstance(
            error, ImportValidationError | UserError | ValueError | csv.Error
        ):
            message = self._prepare_error_message(error)
        else:
            _logger.error(
                "Unexpected error while parsing the import preview", exc_info=error
            )
            message = self.env._(
                "The file could not be read. Please check the format options, or contact your administrator if the problem persists."
            )
        preview = None
        if self.file_type == "text/csv" and self.file:
            preview = self.file[:ERROR_PREVIEW_BYTES].decode("iso-8859-1")
        return {
            "error": message,
            "preview": preview,
        }

    def _get_preview(self, options, count, fields_tree) -> dict:
        self._normalize_row_window_options(options)
        data_rows = self._read_file(options)
        if not data_rows:
            raise ImportValidationError(
                self.env._("Import file has no content or is corrupt")
            )

        preview = data_rows[:count]

        if options.get("has_headers") and preview:
            headers = preview.pop(0)
            header_types = self._extract_headers_types(headers, preview, options)
        else:
            header_types, headers = {}, []

        matches = self._get_preview_matches(headers, header_types, fields_tree, options)
        advanced_mode = self._is_advanced_mode(headers, matches, options)
        column_example = self._prepare_column_examples(headers, preview, options)

        num_rows = len(data_rows) - (1 if headers else 0)
        batch_cutoff = options.get("limit")
        batch = bool(batch_cutoff) and num_rows > batch_cutoff

        return {
            "fields": fields_tree,
            "matches": matches or False,
            "headers": headers or False,
            "header_types": list(header_types.values()) or False,
            "preview": column_example,
            "options": options,
            "advanced_mode": advanced_mode,
            "debug": self.env.user.has_group("base.group_no_one"),
            "batch": batch,
            "num_rows": num_rows,
        }

    def parse_preview(self, options, count=10):
        self.check_singleton()
        self._check_model_name(self.res_model)
        fields_tree = self.get_fields_tree(self.res_model)
        try:
            return self._get_preview(options, count, fields_tree)
        except Exception as error:
            return self._get_preview_error(error)

    def _prepare_column_examples(self, headers, preview, options):
        column_count = max(len(headers), *(len(row) for row in preview or [[]]))
        datetime_format = (
            options.get("datetime_format") or DEFAULT_SERVER_DATETIME_FORMAT
        )
        date_format = options.get("date_format") or DEFAULT_SERVER_DATE_FORMAT

        column_examples = []
        for column_index in range(column_count):
            values = []
            for record in preview:
                value = record[column_index] if column_index < len(record) else ""
                if value and isinstance(value, str):
                    values.append(
                        "%s%s" % (value[:50], "..." if len(value) > 50 else "")
                    )
                elif isinstance(value, datetime.datetime):
                    values.append(value.strftime(datetime_format))
                elif isinstance(value, datetime.date):
                    values.append(value.strftime(date_format))
                if len(values) == 5:
                    break
            column_examples.append(values or [""])
        return column_examples

    @api.model
    def _check_field_mapping(self, fields) -> None:
        for position, field in enumerate(fields, start=1):
            if field and not isinstance(field, str):
                raise ImportValidationError(
                    self.env._(
                        "Column %(column)s is not mapped to a field name.",
                        column=position,
                    )
                )

    def _map_import_rows(
        self, rows_to_import, mapper, max_index, title_row_entries, options
    ):
        data = []
        for row_number, row in enumerate(
            rows_to_import, start=2 if options.get("has_headers") else 1
        ):
            if len(row) <= max_index:
                raise ImportValidationError(
                    self.env._(
                        "Error while importing records: all rows should be of the same size, "
                        "but the title row has %(title_row_entries)d entries while row "
                        "%(row_number)d has %(row_entries)d. You may need to change the "
                        "separator character.",
                        title_row_entries=title_row_entries,
                        row_number=row_number,
                        row_entries=len(row),
                    )
                )
            mapped = list(mapper(row))
            if any(mapped):
                data.append(mapped)
        return data

    def _convert_import_data(
        self,
        fields: Sequence[str | bool],
        options,
    ) -> tuple[
        list[list[str]],
        list[str],
    ]:
        self._check_field_mapping(fields)
        indices = [index for index, field in enumerate(fields) if field]
        if not indices:
            raise ImportValidationError(
                self.env._("You must configure at least one field to import")
            )
        if len(indices) == 1:

            def mapper(row):
                return [row[indices[0]]]
        else:
            mapper = operator.itemgetter(*indices)
        import_fields = [f for f in fields if f]

        rows_to_import = self._read_file(options)
        if not rows_to_import:
            raise ImportValidationError(
                self.env._("Import file has no content or is corrupt")
            )
        if len(rows_to_import[0]) != len(fields):
            raise ImportValidationError(
                self.env._(
                    "Error while importing records: all rows should be of the same size, but the title row has %(title_row_entries)d entries while the first row has %(first_row_entries)d. You may need to change the separator character.",
                    title_row_entries=len(fields),
                    first_row_entries=len(rows_to_import[0]),
                ),
            )

        if options.get("has_headers"):
            rows_to_import = rows_to_import[1:]

        data = self._map_import_rows(
            rows_to_import, mapper, indices[-1], len(fields), options
        )

        return data[options.get("skip") or 0 :], import_fields

    def _batch_window(self, import_fields, data, limit):
        if not limit or limit >= len(data):
            return len(data)

        continuation = self._continuation_rows(import_fields, data)
        window = limit
        while window < len(data) and continuation[window]:
            window += 1
        return window

    def _continuation_rows(self, import_fields, data):
        model = self.env[self.res_model]
        o2m_indexes, other_indexes = [], []
        for index, path in enumerate(import_fields):
            field = model._fields.get(path.split("/")[0])
            (
                o2m_indexes
                if field is not None and field.type == "one2many"
                else other_indexes
            ).append(index)

        if not o2m_indexes:
            return [False] * len(data)

        return [
            bool(
                index
                and any(row[i] for i in o2m_indexes if i < len(row))
                and not any(row[i] for i in other_indexes if i < len(row))
            )
            for index, row in enumerate(data)
        ]

    @api.model
    def _remove_currency_symbol(self, value, currency_symbols=None):
        if currency_symbols is None:
            currency_symbols = _StoredCurrencySymbols(self.env)
        number = strip_currency_symbol(value, currency_symbols)
        return False if number is None else number

    @api.model
    def _currency_symbols(self) -> set:
        symbols = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([])
            .mapped("symbol")
        )
        return {s for s in symbols if s}

    @api.model
    def _parse_float_from_data(self, data, index, name, options) -> None:
        currency_symbols = self._currency_symbols()
        for line in data:
            line[index] = self._stringify_date_like_objects(
                line[index], options, trim=True
            )
            if not line[index]:
                continue
            value = line[index]
            line[index] = normalize_number(
                value,
                symbols=currency_symbols,
                thousand=options.get("float_thousand_separator", " "),
                decimal=options.get("float_decimal_separator", "."),
            )
            if line[index] is None:
                raise ImportValidationError(
                    self.env._(
                        "Column %(column)s contains incorrect values (value: %(value)s)",
                        column=name,
                        value=value,
                    ),
                    field=name,
                )

    def _parse_import_data(self, data, import_fields, options):
        path_models = self._check_import_paths(import_fields)
        for index, path in enumerate(import_fields):
            field = self._resolve_import_path(path, path_models)
            if field is None:
                continue
            if field.type in ("date", "datetime"):
                self._parse_date_from_data(data, index, path, field.type, options)
            elif field.type in ("float", "monetary"):
                self._parse_float_from_data(data, index, path, options)
            elif field.type == "binary" and field.attachment:
                self._parse_binary_from_data(data, index, path, options)
        return data

    def _resolve_import_path(self, path, path_models=None):
        if path_models is not None and path in path_models:
            model = path_models[path]
        else:
            model = self._resolve_path_model(path)
        if not model:
            return None
        return self.env[model]._fields.get(path.split("/")[-1].split(".")[0])

    def _resolve_path_model(self, path):
        model = self.res_model
        for segment in path.split("/")[:-1]:
            if model not in self.env:
                return None
            name, _, property_name = segment.partition(".")
            parent = self.env[model]._fields.get(name)
            if parent is None:
                return None
            if parent.type == "properties":
                return "" if property_name else None
            if not parent.comodel_name:
                return None
            model = parent.comodel_name
        return model if model in self.env else None

    def _check_import_paths(self, import_fields):
        path_models = {}
        for path in import_fields:
            segments = path.split("/")
            if len(segments) == 1:
                continue
            model = self._resolve_path_model(path)
            path_models[path] = model
            if model is None:
                raise ImportValidationError(
                    self.env._(
                        "Column %(column)s cannot be imported: %(path)s is not a "
                        "relation on model %(model)s, so it has no sub-fields.",
                        column=path,
                        path="/".join(segments[:-1]),
                        model=self.res_model,
                    ),
                    field=path,
                )
        return path_models

    def _parse_binary_from_data(self, data, index, name, options) -> None:
        with self.env["ir.egress"].session(
            purpose="import_url", max_bytes=None
        ) as session:
            session.stream = True

            for num, line in enumerate(data):
                if isinstance(line[index], (datetime.date, datetime.datetime)):
                    line[index] = self._stringify_date_like_objects(
                        line[index], options
                    )
                if re.match(config.get("import_url_regex"), line[index]):
                    if not self.env.user._can_import_remote_urls():
                        raise ImportValidationError(
                            self.env._(
                                "You can not import file via URL, check with your administrator or support for the reason."
                            ),
                            field=name,
                            field_type="binary",
                        )
                    line[index] = self._import_file_by_url(
                        line[index], session, name, num
                    )
                elif "." in line[index]:
                    pass
                else:
                    try:
                        base64.b64decode(line[index], validate=True)
                    except ValueError as e:
                        raise ImportValidationError(
                            self.env._(
                                "Found invalid image data, images should be imported as either URLs or base64-encoded data."
                            ),
                            field=name,
                            field_type="binary",
                        ) from e

    def _parse_date_from_data(self, data, index, name, field_type, options) -> None:
        dt = datetime.datetime
        fmt = (
            fields.Date.to_string if field_type == "date" else fields.Datetime.to_string
        )
        d_fmt = options.get("date_format") or DEFAULT_SERVER_DATE_FORMAT
        dt_fmt = options.get("datetime_format") or DEFAULT_SERVER_DATETIME_FORMAT
        for num, line in enumerate(data):
            if not line[index] or isinstance(line[index], datetime.date):
                continue

            v = line[index].strip()
            try:
                if dt_fmt and field_type == "datetime":
                    try:
                        line[index] = fmt(dt.strptime(v, dt_fmt))
                        continue
                    except ValueError:
                        pass
                line[index] = fmt(dt.strptime(v, d_fmt))
            except ValueError as e:
                raise ImportValidationError(
                    self.env._(
                        "Column %(column)s contains incorrect values. Error in line %(line)d: %(error)s",
                        column=name,
                        line=num + 1,
                        error=e,
                    ),
                    field=name,
                    field_type=field_type,
                ) from e
            except Exception as e:
                raise ImportValidationError(
                    self.env._(
                        "Error Parsing Date [%(field)s:L%(line)d]: %(error)s",
                        field=name,
                        line=num + 1,
                        error=e,
                    ),
                    field=name,
                    field_type=field_type,
                ) from e

    def _import_file_by_url(self, url, session, field, line_number):
        assert re.match(config.get("import_url_regex"), url)
        maxsize = config.get("import_file_maxbytes")
        _logger.debug(
            "Trying to import file from URL: %s into field %s, at line %s",
            url,
            field,
            line_number,
        )
        try:
            response = session.get(url, timeout=config.get("import_file_timeout"))
            response.raise_for_status()

            if (
                response.headers.get("Content-Length")
                and int(response.headers["Content-Length"]) > maxsize
            ):
                raise ImportValidationError(
                    self.env._(
                        "File size exceeds configured maximum (%s bytes)", maxsize
                    ),
                    field=field,
                )

            content = bytearray()
            for chunk in response.iter_content(DEFAULT_CHUNK_SIZE):
                content += chunk
                if len(content) > maxsize:
                    raise ImportValidationError(
                        self.env._(
                            "File size exceeds configured maximum (%s bytes)", maxsize
                        ),
                        field=field,
                    )

            if not guess_mimetype(content).startswith("image/"):
                return base64.b64encode(content)

            image = Image.open(io.BytesIO(content))
            w, h = image.size
            if w * h > 42e6:
                raise ImportValidationError(
                    self.env._(
                        "Image size excessive, imported images must be smaller than 42 million pixel"
                    ),
                    field=field,
                )

            return base64.b64encode(content)
        except ImportValidationError:
            raise
        except Exception as e:
            _logger.warning(e, exc_info=True)
            raise ImportValidationError(
                self.env._(
                    "Could not retrieve URL: %(url)s [%(field_name)s: L%(line_number)d]: %(error)s"
                )
                % {
                    "url": url,
                    "field_name": field,
                    "line_number": line_number + 1,
                    "error": e,
                },
                field=field,
            ) from e

    @api.model
    def _stringify_date_like_objects(self, data, options, trim=False):
        if isinstance(data, datetime.datetime):
            res = data.strftime(
                options.get("datetime_format") or DEFAULT_SERVER_DATETIME_FORMAT
            )
        elif isinstance(data, datetime.date):
            res = data.strftime(
                options.get("date_format") or DEFAULT_SERVER_DATE_FORMAT
            )
        else:
            res = data
        return res.strip() if trim else res

    def _merge_import_columns(
        self, import_fields, input_file_data, options
    ) -> tuple[list[str], list[list]]:
        import_fields, merged_data = self.with_context(
            import_options=options
        )._handle_multi_mapping(import_fields, input_file_data)

        if options.get("fallback_values"):
            merged_data = self._handle_fallback_values(
                import_fields, merged_data, options["fallback_values"]
            )
        return import_fields, merged_data

    def _load_import_data(self, import_fields, merged_data, options, import_limit):
        name_create_enabled_fields = options.pop("name_create_enabled_fields", {})
        options.pop("limit", None)
        model = self.env[self.res_model].with_context(
            import_file=True,
            name_create_enabled_fields=name_create_enabled_fields,
            import_set_empty_fields=options.get("import_set_empty_fields", []),
            import_skip_records=options.get("import_skip_records", []),
            _import_limit=import_limit,
        )
        return model.load(import_fields, merged_data)

    def _finalize_import_result(
        self, import_result, columns, fields, import_fields, merged_data, options
    ) -> None:
        if import_result["ids"] and options.get("has_headers"):
            self._save_column_mappings(columns, fields)

        import_result["name"] = self._record_names(import_fields, merged_data, options)

        if import_result["nextrow"]:
            import_result["nextrow"] += options.get("skip", 0)

    def execute_import(self, fields, columns, options, dryrun=False):
        self.check_singleton()
        self._check_model_name(self.res_model)
        import_savepoint = self.env.cr.savepoint()
        released = False
        try:
            try:
                import_fields, input_file_data = self._prepare_batch_rows(
                    fields, options
                )
            except ImportValidationError as error:
                error.message = self._prepare_error_message(error)
                return {"messages": [error.__dict__]}
            import_limit = options.get("limit")

            _logger.info("importing %d rows...", len(input_file_data))

            binary_filenames = self._extract_binary_filenames(
                import_fields, input_file_data
            )
            import_fields, merged_data = self._merge_import_columns(
                import_fields, input_file_data, options
            )
            import_result = self._load_import_data(
                import_fields, merged_data, options, import_limit
            )
            _logger.info("done")

            with contextlib.suppress(psycopg.InternalError):
                import_savepoint.close(rollback=dryrun)
            released = True
            if dryrun:
                self.pool.clear_cache("default", "groups", "stable")
                self.pool.reset_changes()

            self._finalize_import_result(
                import_result, columns, fields, import_fields, merged_data, options
            )
            if binary_filenames:
                import_result["binary_filenames"] = binary_filenames

            return import_result
        finally:
            if not released:
                with contextlib.suppress(psycopg.InternalError):
                    import_savepoint.close(rollback=True)

    def _prepare_batch_rows(self, fields, options) -> tuple:
        self._normalize_row_window_options(options)
        data, import_fields = self._convert_import_data(fields, options)
        data = self._parse_import_data(data, import_fields, options)
        window = self._batch_window(import_fields, data, options.get("limit"))
        return import_fields, data[:window]

    def _record_names(self, import_fields, merged_data, options):
        if "name" not in import_fields:
            return []
        index_of_name = import_fields.index("name")
        names = [""] * (options.get("skip", 0) if merged_data else 0)
        continuation = self._continuation_rows(import_fields, merged_data)
        names.extend(
            self._stringify_date_like_objects(row[index_of_name], options)
            for index, row in enumerate(merged_data)
            if not continuation[index]
        )
        return names

    def _save_column_mappings(self, columns, fields) -> None:
        wanted = {
            _normalize_column_name(column_name): field_name
            for column_name, field_name in zip(columns, fields, strict=False)
            if column_name and field_name
        }
        if not wanted:
            return

        BaseImportMapping = self.env["base_import.mapping"]
        existing = BaseImportMapping.search(
            [
                ("res_model", "=", self.res_model),
                ("column_name", "in", list(wanted)),
            ]
        )
        for mapping in existing:
            field_name = wanted[mapping.column_name]
            if mapping.field_name != field_name:
                mapping.field_name = field_name

        missing = [
            {
                "res_model": self.res_model,
                "column_name": column_name,
                "field_name": field_name,
            }
            for column_name, field_name in wanted.items()
            if column_name not in set(existing.mapped("column_name"))
        ]
        if not missing:
            return
        try:
            with self.env.cr.savepoint():
                BaseImportMapping.create(missing)
        except psycopg.errors.UniqueViolation:
            _logger.debug(
                "concurrent import already stored a mapping for %s; skipping",
                self.res_model,
            )

    def _extract_binary_filenames(self, import_fields, data):
        binary_indexes = {}
        for index, path in enumerate(import_fields):
            field = self._resolve_import_path(path)
            if field is not None and field.type == "binary" and field.attachment:
                binary_indexes[path] = index
        if not binary_indexes:
            return {}

        per_row = []
        for line in data:
            row_names = {}
            for name, index in binary_indexes.items():
                value = line[index] if index < len(line) else None
                if (
                    isinstance(value, str)
                    and "." in value
                    and not re.match(config.get("import_url_regex"), value)
                ):
                    row_names[name] = value
                    line[index] = ""
            per_row.append(row_names)

        continuation = self._continuation_rows(import_fields, data)
        binary_filenames = {name: [] for name in binary_indexes}
        for row_index, row_names in enumerate(per_row):
            for name in binary_indexes:
                filename = row_names.get(name)
                if continuation[row_index]:
                    if (
                        filename
                        and binary_filenames[name]
                        and not binary_filenames[name][-1]
                    ):
                        binary_filenames[name][-1] = filename
                else:
                    binary_filenames[name].append(filename)
        return binary_filenames

    def _get_merge_plan(self, mapped_field_indexes):
        merge_plan = []
        for field_path, indexes in mapped_field_indexes.items():
            field = self._resolve_import_path(field_path)
            field_type = field.type if field else ""
            merge_plan.append(
                (
                    indexes,
                    field_type,
                    CONCAT_SEPARATOR_IMPORT.get(field_type),
                    field_type == "char" and field.trim,
                )
            )
        return merge_plan

    def _merge_mapped_row(self, record, merge_plan, import_options):
        new_record = []
        for indexes, field_type, separator, trim in merge_plan:
            if separator is not None:
                new_record.append(
                    separator.join(
                        self._stringify_date_like_objects(
                            record[idx], import_options, trim
                        )
                        for idx in indexes
                        if record[idx]
                    )
                )
            elif field_type == "properties":
                new_record.append(
                    self._stringify_date_like_objects(
                        record[indexes[0]], import_options
                    )
                )
            else:
                new_record.append(record[indexes[0]])
        return new_record

    def _handle_multi_mapping(self, import_fields, input_file_data) -> tuple:
        mapped_field_indexes = {}
        for idx, field_path in enumerate(
            field_path for field_path in import_fields if field_path
        ):
            mapped_field_indexes.setdefault(field_path, []).append(idx)
        import_fields = list(mapped_field_indexes.keys())
        import_options = self.env.context.get("import_options", {})

        merge_plan = self._get_merge_plan(mapped_field_indexes)

        merged_data = [
            self._merge_mapped_row(record, merge_plan, import_options)
            for record in input_file_data
        ]

        return import_fields, merged_data

    def _update_fallback_accepted_values(self, fallback_values) -> None:
        converter = self.env["ir.fields.converter"]
        for field_string, fallback in fallback_values.items():
            target_field = field_string.split("/")[-1]
            target_model = self.env[fallback["field_model"]]
            field = target_model._fields.get(target_field)

            if fallback["field_type"] == "boolean":
                trues, falses = converter._get_boolean_tokens()
                fallback["accepted_values"] = trues | falses
                continue
            if fallback["field_type"] != "selection":
                continue

            if field is not None and field.type == "selection":
                fallback["accepted_values"] = frozenset(
                    converter._get_selection_index(field)
                )
                continue
            selection = fallback.get("selection") or []
            fallback["accepted_values"] = frozenset(
                str(token).lower() for pair in selection for token in pair
            )

    def _apply_fallback_value(self, value, fallback):
        value = self._stringify_date_like_objects(
            value, self.env.context.get("import_options", {})
        )
        accepted = fallback.get("accepted_values")
        if accepted is not None and value.lower() not in accepted:
            fallback_value = fallback["fallback_value"]
            return fallback_value if fallback_value != "skip" else None
        return value

    def _handle_fallback_values(self, import_field, input_file_data, fallback_values):
        self._update_fallback_accepted_values(fallback_values)

        for record_index, records in enumerate(input_file_data):
            for column_index, value in enumerate(records):
                field = import_field[column_index]
                if field in fallback_values:
                    input_file_data[record_index][column_index] = (
                        self._apply_fallback_value(value, fallback_values[field])
                    )

        return input_file_data


_SEPARATORS = [" ", "/", "-", ".", ""]
_PATTERN_BASELINE = [
    ("%m", "%d", "%Y"),
    ("%d", "%m", "%Y"),
    ("%Y", "%m", "%d"),
    ("%Y", "%d", "%m"),
]
DATE_FORMATS = []
for ps in _PATTERN_BASELINE:
    patterns = {ps}
    for s, t in [("%Y", "%y")]:
        patterns.update([tuple(t if it == s else it for it in f) for f in patterns])
    DATE_FORMATS.extend(patterns)
DATE_PATTERNS = [sep.join(fmt) for sep in _SEPARATORS for fmt in DATE_FORMATS]
TIME_PATTERNS = [
    "%H:%M:%S",
    "%H:%M",
    "%H",
    "%I:%M:%S %p",
    "%I:%M %p",
    "%I %p",
]

_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")


def _normalize_column_name(name):
    return (name or "").strip().lower()


def _is_native_date_column(values) -> bool:
    populated = [value for value in values if value]
    return bool(populated) and all(
        isinstance(value, datetime.date) for value in populated
    )


def _is_integer_literal(value) -> bool:
    return bool(_INTEGER_RE.match(value))


def get_matching_pattern(patterns, values):
    for pattern in patterns:
        p = to_re(pattern)
        for val in values:
            if isinstance(val, datetime.date):
                continue
            if val and not p.match(val):
                break

        else:
            return pattern

    return None


@functools.lru_cache(maxsize=1024)
def to_re(pattern):
    pattern = re.sub(r"\s+", r"\\s+", pattern)
    pattern = re.sub(r"%([a-z])", _replacer, pattern, flags=re.IGNORECASE)
    pattern = "^" + pattern + "$"
    return re.compile(pattern, re.IGNORECASE)


def _replacer(m):
    return _P_TO_RE[m.group(1)]


_P_TO_RE = {
    "d": r"(3[0-1]|[1-2]\d|0[1-9]|[1-9]| [1-9])",
    "H": r"(2[0-3]|[0-1]\d|\d)",
    "I": r"(1[0-2]|0[1-9]|[1-9])",
    "m": r"(1[0-2]|0[1-9]|[1-9])",
    "M": r"([0-5]\d|\d)",
    "S": r"(6[0-1]|[0-5]\d|\d)",
    "y": r"(\d\d)",
    "Y": r"(\d\d\d\d)",
    "p": r"(am|pm)",
    "%": "%",
}


def _prepare_read_file_error(exc: Exception, message: str) -> UserError:
    _logger.debug(message, exc_info=exc)
    e = UserError(message)
    e.__cause__ = exc
    return e


register_reader(
    _SpreadsheetReader("xlsx", mimetypes_for("xlsx"), read_xlsx_rows, "openpyxl")
)
register_reader(_SpreadsheetReader("xls", mimetypes_for("xls"), read_xls_rows, "xlrd"))
register_reader(_SpreadsheetReader("ods", mimetypes_for("ods"), read_ods_rows, "odf"))
