import datetime
import logging

from odoo import models
from odoo.fields import Domain
from odoo.libs.json import dumps as json_dumps

from . import catalog, write_ops

_logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_GROUPS = 200
MAX_MODELS = 40
# A tool answer goes back to the model as text: past this it is cut, and the
# model is told so, rather than overflowing the conversation.
RESULT_BUDGET = 60000

# Models that hold the instance's secrets rather than business data: system
# parameters, API keys and the credential vault.
BLOCKED_MODEL_PREFIXES = (
    "ir.config_parameter",
    "res.users.apikeys",
    "credential.",
)
# Field types a question never needs and whose values are large or opaque.
SKIPPED_FIELD_TYPES = frozenset({"binary", "image"})

TOOLS = [
    {
        "name": "find_models",
        "description": (
            "Find the Odoo models whose technical name or label contains a "
            "word, e.g. 'sale', 'factura', 'stock.quant'. Call it whenever you "
            "are unsure which model holds the data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "describe_model",
        "description": (
            "The fields of one model: name, type, label, relation target and "
            "selection values. Call it before using a field you have not seen "
            "described: this Odoo fork renames many vanilla fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "search": {
                    "type": "string",
                    "description": "Only fields whose name or label contains this.",
                },
            },
            "required": ["model"],
        },
    },
    {
        "name": "search_records",
        "description": (
            "Read records matching an Odoo domain. Always name the fields you "
            f"need. At most {MAX_LIMIT} records per call; page with offset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {
                    "type": "array",
                    "description": 'Odoo domain, e.g. [["state", "=", "sale"]].',
                },
                "fields": {"type": "array", "items": {"type": "string"}},
                "order": {"type": "string"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
            "required": ["model", "fields"],
        },
    },
    {
        "name": "count_records",
        "description": "How many records match a domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {"type": "array"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "aggregate_records",
        "description": (
            "Group and aggregate instead of listing: totals, counts per "
            "category, time series. groupby takes field names, a date with a "
            'granularity ("date_order:month"); aggregates take '
            '"field:sum|avg|min|max|count_distinct" or "__count".'
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {"type": "array"},
                "groupby": {"type": "array", "items": {"type": "string"}},
                "aggregates": {"type": "array", "items": {"type": "string"}},
                "order": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["model", "aggregates"],
        },
    },
]


MAX_PDFS = 5
# pdf_reports' id for a partner's account statement, which no report action
# prints
STATEMENT_ID = -1

PDF_TOOLS = [
    {
        "name": "pdf_reports",
        "description": (
            "The PDF documents Odoo prints for a model (quotation, invoice, "
            "delivery slip, receipt...): their ids and names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"model": {"type": "string"}},
            "required": ["model"],
        },
    },
    {
        "name": "send_pdf",
        "description": (
            "Send the person a PDF exactly as Odoo prints it: one of the "
            "model's pdf_reports, for records found with the read tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "integer"},
                "ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["report_id", "ids"],
        },
    },
]


class ReaderError(Exception):
    """A tool call the model can correct: the message goes back to it."""


class OdooTools:
    """Run the agent's read tools through an `OdooReader`.

    Each call reads on its own read-only transaction, so no tool can write
    whatever it is asked, and none sits idle while the model thinks. What the
    instance keeps secret stays out, also as a filter, an order or a grouping.
    """

    def __init__(
        self, reader, queries=None, *, tz="UTC", today=None, writable=False
    ) -> None:
        self._reader = reader
        self._queries = queries or {}
        self._tz = tz
        self._today = today
        self._writable = writable
        # changes the agent proposes, kept until the person authorizes them
        self.proposals = []
        # Odoo's own PDFs the agent asks to send: (report id, model, ids)
        self.pdf_requests = []

    def tools(self) -> list:
        """The tool specs the model gets: the catalogued reports first, when
        there are any, then the exploration tools."""
        if not self._queries:
            return [*(dict(tool) for tool in TOOLS), *PDF_TOOLS, *self._write_tools()]
        reports = "\n".join(
            f"- {key}: {query.description}" for key, query in self._queries.items()
        )
        run_report = {
            "name": "run_report",
            "description": (
                "Run one of the company's exact reports and get its answer as "
                "text. Its figures are exact: prefer it whenever a report "
                "covers the question or part of it, and explore with the other "
                "tools only what no report covers. Reports:\n" + reports
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "report": {"type": "string", "enum": list(self._queries)},
                    "date_from": {"type": "string", "description": "ISO date"},
                    "date_to": {"type": "string", "description": "ISO date"},
                    "group_by": {
                        "type": "string",
                        "enum": [
                            "company",
                            "warehouse",
                            "salesperson",
                            "partner",
                            "product",
                            "month",
                        ],
                    },
                    "company": {"type": "string"},
                    "warehouse": {"type": "string"},
                    "partner": {"type": "string"},
                    "product": {"type": "string"},
                    "salesperson": {"type": "string"},
                    "employee": {"type": "string"},
                    "overdue_only": {"type": "boolean"},
                    "summary_only": {"type": "boolean"},
                    "top": {"type": "integer"},
                },
                "required": ["report"],
            },
        }
        return [
            run_report,
            *(dict(tool) for tool in TOOLS),
            *PDF_TOOLS,
            *self._write_tools(),
        ]

    def call(self, name, arguments) -> str:
        """Run tool `name` and return its answer as JSON text.

        :param str name: the tool name, one of TOOLS
        :param dict arguments: the tool input the model produced
        :return: the result, or an error the model can act on
        :rtype: str
        """
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            return json_dumps({"error": f"Unknown tool {name!r}."})
        try:
            with self._reader.env() as env:
                result = method(env, **(arguments or {}))
        except ReaderError as error:
            result = {"error": str(error)}
        except Exception as error:
            # an invalid domain, an unknown field, a compute that would write:
            # the model reads the reason and tries another way
            _logger.info("insight_telegram tool %s failed: %s", name, error)
            result = {"error": f"{type(error).__name__}: {error}"}
        text = json_dumps(result, default=_json_default)
        if len(text) > RESULT_BUDGET:
            text = text[:RESULT_BUDGET] + (
                "\n[TRUNCATED: ask for fewer fields or records, or aggregate]"
            )
        return text

    def companies(self) -> str:
        """The companies the reader sees, with their currency, for the prompt."""
        with self._reader.env() as env:
            companies = env["res.company"].search([])
            return ", ".join(
                f"{company.name} (id {company.id}, {company.currency_id.name})"
                for company in companies
            )

    def _write_tools(self) -> list:
        if not self._writable:
            return []
        values = {
            "type": "object",
            "description": "Field name to value; one2many lines as Odoo commands.",
        }
        ids = {
            "type": "array",
            "items": {"type": ["integer", "string"]},
            "description": 'Record ids, or "ref:N" for the record proposal N creates.',
        }
        attach = {
            "type": "boolean",
            "description": "Attach the files the person sent to this record.",
        }
        return [
            {
                "name": "propose_create",
                "description": (
                    "Propose creating a record. Nothing is written until the "
                    "person authorizes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "values": values,
                        "attach_files": attach,
                    },
                    "required": ["model", "values"],
                },
            },
            {
                "name": "propose_write",
                "description": (
                    "Propose changing fields of existing records. Nothing is "
                    "written until the person authorizes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "ids": ids,
                        "values": values,
                        "attach_files": attach,
                    },
                    "required": ["model", "ids", "values"],
                },
            },
            {
                "name": "propose_action",
                "description": (
                    "Propose pressing a screen button (an action_* or button_* "
                    "method: confirm, validate, mark done...) on records. "
                    "Nothing runs until the person authorizes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "ids": ids,
                        "method": {"type": "string"},
                    },
                    "required": ["model", "ids", "method"],
                },
            },
        ]

    def _propose(self, env, operation) -> dict:
        if not self._writable:
            raise ReaderError("This bot does not change data.")
        if len(self.proposals) >= write_ops.MAX_OPERATIONS:
            raise ReaderError("Too many changes at once; propose fewer.")
        try:
            operation = write_ops.check(env, operation)
        except write_ops.OperationError as error:
            raise ReaderError(str(error)) from error
        self.proposals.append(operation)
        return {
            "proposal": len(self.proposals),
            "status": "kept until the person authorizes; nothing written yet",
        }

    def _tool_propose_create(self, env, model="", values=None, attach_files=False):
        return self._propose(
            env,
            {
                "op": "create",
                "model": model,
                "values": values,
                "attach_files": attach_files,
            },
        )

    def _tool_propose_write(
        self, env, model="", ids=None, values=None, attach_files=False
    ):
        return self._propose(
            env,
            {
                "op": "write",
                "model": model,
                "ids": ids,
                "values": values,
                "attach_files": attach_files,
            },
        )

    def _tool_propose_action(self, env, model="", ids=None, method=""):
        return self._propose(
            env, {"op": "action", "model": model, "ids": ids, "method": method}
        )

    def _tool_pdf_reports(self, env, model="") -> dict:
        model = (model or "").strip()
        reports = env["ir.actions.report"].search(
            [("model", "=", model), ("report_type", "=", "qweb-pdf")]
        )
        listed = [{"id": report.id, "name": report.name} for report in reports]
        if model == "res.partner":
            # the account statement is an accounting report, not a report action
            listed.insert(
                0, {"id": STATEMENT_ID, "name": "Account statement (estado de cuenta)"}
            )
        return {"reports": listed}

    def _tool_send_pdf(self, env, report_id=0, ids=None) -> dict:
        if int(report_id or 0) == STATEMENT_ID:
            partners = env["res.partner"].browse([int(i) for i in ids or []]).exists()
            if not partners:
                raise ReaderError(f"No res.partner record {ids}.")
            if len(self.pdf_requests) >= MAX_PDFS:
                raise ReaderError("Too many PDFs at once.")
            self.pdf_requests.append((STATEMENT_ID, "res.partner", partners.ids))
            return {
                "queued": "Account statement",
                "records": partners.mapped("display_name"),
            }
        report = env["ir.actions.report"].browse(int(report_id or 0)).exists()
        if not report or report.report_type != "qweb-pdf":
            raise ReaderError("No such PDF report; call pdf_reports for the model.")
        records = env[report.model].browse([int(i) for i in ids or []]).exists()
        if not records:
            raise ReaderError(f"No {report.model} record {ids}.")
        if len(self.pdf_requests) >= MAX_PDFS:
            raise ReaderError("Too many PDFs at once.")
        self.pdf_requests.append((report.id, report.model, records.ids))
        return {"queued": report.name, "records": records.mapped("display_name")}

    def _tool_run_report(self, env, report="", **params) -> dict:
        query = self._queries.get(report)
        if query is None:
            raise ReaderError(f"No report {report!r}; use one of the listed ones.")
        return {
            "report": catalog.answer(env, query, params, tz=self._tz, today=self._today)
        }

    # -- tools ----------------------------------------------------------------

    def _tool_find_models(self, env, query="") -> dict:
        query = (query or "").strip()
        if not query:
            raise ReaderError("`query` must be a non-empty word.")
        found = env["ir.model"].search_fetch(
            [
                ("transient", "=", False),
                "|",
                ("model", "ilike", query),
                ("name", "ilike", query),
            ],
            ["model", "name"],
            limit=MAX_MODELS * 2,
        )
        rows = [
            {"model": m.model, "name": m.name}
            for m in found
            if not _is_blocked(m.model) and _is_queryable(env, m.model)
        ]
        return {"models": rows[:MAX_MODELS]}

    def _tool_describe_model(self, env, model="", search=None) -> dict:
        records = _model(env, model)
        search = (search or "").lower()
        described = {}
        for name, field in records._fields.items():
            if not _is_readable(field):
                continue
            if search and search not in name and search not in field.string.lower():
                continue
            spec = {"type": field.type, "label": field.string}
            if field.relational:
                spec["relation"] = field.comodel_name
            if field.type == "selection":
                spec["selection"] = _selection(records, field)
            if not field.store:
                spec["stored"] = False
            if field.readonly and field.compute and not field.inverse:
                # a proposal setting it is refused: the figure would be lost
                spec["computed"] = True
            described[name] = spec
        return {"model": records._name, "fields": described}

    def _tool_search_records(
        self, env, model="", domain=None, fields=None, order=None, limit=None, offset=0
    ) -> dict:
        records = _model(env, model)
        names = _fields(records, fields or ["display_name"])
        limit = _limit(limit, DEFAULT_LIMIT, MAX_LIMIT)
        domain = _domain(records, domain)
        rows = records.search_read(
            domain,
            names,
            offset=int(offset or 0),
            limit=limit,
            order=_order(records, order),
        )
        total = records.search_count(domain) if len(rows) == limit else None
        result = {"records": rows, "returned": len(rows)}
        if total is not None:
            result["total_matching"] = total
        return result

    def _tool_count_records(self, env, model="", domain=None) -> dict:
        records = _model(env, model)
        return {"count": records.search_count(_domain(records, domain))}

    def _tool_aggregate_records(
        self,
        env,
        model="",
        domain=None,
        groupby=None,
        aggregates=None,
        order=None,
        limit=None,
    ) -> dict:
        records = _model(env, model)
        groupby = list(groupby or [])
        aggregates = list(aggregates or ["__count"])
        for spec in groupby + aggregates:
            path = spec.split(":")[0]
            if path != "__count":
                _check_path(records, path)
        limit = _limit(limit, MAX_GROUPS, MAX_GROUPS)
        rows = records._read_group(
            _domain(records, domain),
            groupby,
            aggregates,
            limit=limit,
            order=_order(records, order),
        )
        keys = groupby + aggregates
        return {
            "groups": [
                {key: _plain(value) for key, value in zip(keys, row, strict=True)}
                for row in rows
            ],
            "returned": len(rows),
        }


def _is_blocked(model_name) -> bool:
    return model_name.startswith(BLOCKED_MODEL_PREFIXES)


def _is_queryable(env, model_name) -> bool:
    model = env.get(model_name)
    return model is not None and not model._abstract and model._auto


def _is_readable(field) -> bool:
    # what the instance marks secret, and what only its administrators see,
    # are the instance's configuration, never a business answer
    if field.type in SKIPPED_FIELD_TYPES:
        return False
    if (field.classification or "").startswith("secret"):
        return False
    return "base.group_system" not in (field.groups or "")


def _model(env, model_name):
    model_name = (model_name or "").strip()
    if not model_name:
        raise ReaderError("`model` must name an Odoo model; call find_models.")
    if _is_blocked(model_name):
        raise ReaderError(f"{model_name!r} holds secrets and is not readable here.")
    if not _is_queryable(env, model_name):
        raise ReaderError(f"No queryable model {model_name!r}; call find_models.")
    return env[model_name]


def _fields(records, names) -> list:
    unknown, hidden = [], []
    for name in names:
        field = records._fields.get(name)
        if field is None:
            unknown.append(name)
        elif not _is_readable(field):
            hidden.append(name)
    if unknown:
        raise ReaderError(
            f"{records._name} has no field {', '.join(unknown)}; call describe_model."
        )
    if hidden:
        raise ReaderError(f"Field(s) {', '.join(hidden)} cannot be read here.")
    return list(names)


def _check_path(records, path):
    """Refuse a dotted field path that crosses a field the reader hides: a
    filter, an order or a grouping on a secret reveals it as surely as reading
    it would."""
    model, field = records, None
    for name in path.split("."):
        field = model._fields.get(name)
        if field is None:
            raise ReaderError(
                f"{model._name} has no field {name!r}; call describe_model."
            )
        if not _is_readable(field) or (
            field.relational and _is_blocked(field.comodel_name)
        ):
            raise ReaderError(f"Field {path!r} cannot be used here.")
        if field.relational:
            model = model.env[field.comodel_name]
    return field


def _domain(records, domain):
    if not domain:
        return []
    if not isinstance(domain, list):
        raise ReaderError("`domain` must be a list.")
    # Domain() validates the shape, so a malformed one fails here with a
    # message the model can read rather than deep in the query builder
    Domain(domain)
    _check_domain_paths(records, domain)
    return domain


def _check_domain_paths(records, domain) -> None:
    for leaf in domain:
        if isinstance(leaf, list | tuple) and len(leaf) == 3:
            path, _operator, value = leaf
            if not isinstance(path, str):
                continue
            field = _check_path(records, path)
            if (
                field is not None
                and field.relational
                and isinstance(value, list)
                and any(isinstance(item, list | tuple) for item in value)
            ):
                # a sub-domain under any / not any, on the related model
                _check_domain_paths(records.env[field.comodel_name], value)


def _order(records, order):
    if not order:
        return None
    for term in str(order).split(","):
        words = term.split()
        if words:
            _check_path(records, words[0])
    return order


def _limit(value, default, maximum) -> int:
    try:
        value = int(value) if value else default
    except TypeError, ValueError:
        value = default
    return max(1, min(value, maximum))


def _selection(records, field) -> list:
    try:
        return [key for key, _label in field._description_selection(records.env)]
    except Exception:
        return []


def _plain(value):
    if isinstance(value, models.BaseModel):
        if len(value) == 1:
            return [value.id, value.display_name]
        return [[record.id, record.display_name] for record in value]
    return value


def _json_default(value):
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    if isinstance(value, models.BaseModel):
        return _plain(value)
    return str(value)
