from __future__ import annotations

import logging
from typing import Any

import psycopg

from odoo import api, fields, models
from odoo.libs.documents import METERED, Document

from ..tools import GENERATIVE, cascade
from ..tools.schema import known_schemas

_logger = logging.getLogger(__name__)

JOB_CHANNEL = "extract"

NOT_COMPARABLE = object()

WAIT_SECONDS = 30
WAIT_ATTEMPTS = 40

STATES = [
    ("none", "Not extracted"),
    ("queued", "Queued"),
    ("running", "Running"),
    ("waiting", "Waiting on a service"),
    ("done", "Extracted"),
    ("partial", "Partially extracted"),
    ("failed", "Failed"),
]


class MixinExtract(models.AbstractModel):
    _name = "mixin.extract"
    _description = "Document Extraction"

    _extract_document_type: str = ""
    _extract_target: dict[str, str] = {}

    extract_state = fields.Selection(
        selection=STATES,
        default="none",
        index=True,
        copy=False,
        readonly=True,
    )
    extract_result = fields.Json(
        copy=False,
        readonly=True,
        help="Every value that was read, with which strategy proposed it and "
        "how confident it was.",
    )
    extract_missing = fields.Json(
        copy=False,
        readonly=True,
        help="Required fields no strategy could read, and rules that do not "
        "hold. What a person has to supply.",
    )
    extract_error = fields.Text(
        copy=False,
        readonly=True,
    )
    extract_pending = fields.Json(
        copy=False,
        readonly=True,
        help="The service this document is waiting on, and its handle. Kept so "
        "the next attempt asks again rather than submitting the document a "
        "second time.",
    )
    extract_corrections = fields.Json(
        copy=False,
        readonly=True,
        help="Fields a person changed after extraction, with what was read and "
        "what it should have been.",
    )

    def write(self, vals):
        watched = set(self._extract_target.values()) & set(vals)
        corrections = {}
        if watched and not self.env.context.get("extracting"):
            for record in self:
                found = record._corrections_in(vals)
                if found:
                    corrections[record.id] = found

        result = super().write(vals)

        for record in self:
            found = corrections.get(record.id)
            if found:
                stored = dict(record.extract_corrections or {})
                stored.update(found)
                super(MixinExtract, record.with_context(extracting=True)).write(
                    {"extract_corrections": stored}
                )
        return result

    def _get_extract_document_type(self) -> str:
        return self._extract_document_type

    def _get_extract_source(self) -> Document | None:
        self.check_singleton()
        attachment = None
        if "message_main_attachment_id" in self._fields:
            attachment = self.message_main_attachment_id
        if not attachment:
            attachment = self.env["ir.attachment"].search(
                [("res_model", "=", self._name), ("res_id", "=", self.id)],
                order="id desc",
                limit=1,
            )
        if not attachment:
            return None
        document = attachment._as_document()
        if document is not None and "company_id" in self._fields and self.company_id:
            document.options["company"] = self.company_id
        return document

    def _update_from_extraction(self, result) -> None:
        self.check_singleton()
        values = {}
        for schema_field, model_field in self._extract_target.items():
            if model_field not in self._fields:
                _logger.warning(
                    "%s maps %r to %r, which is not a field of this model",
                    self._name,
                    schema_field,
                    model_field,
                )
                continue
            value = result.flat().get(schema_field)
            if value is not None and not self[model_field]:
                values[model_field] = self._extract_write_value(model_field, value)
        if values:
            self.write(values)

    def _extract_write_value(self, model_field: str, value: Any) -> Any:
        return value

    def _extract_compare_value(self, model_field: str, value: Any) -> Any:
        return value

    def action_extract(self) -> None:
        for record in self:
            record._extract_document(up_to=GENERATIVE)

    def action_extract_later(self) -> None:
        for record in self:
            record._extract_later()

    def _extract_later(self, delay: int = 0, after=None):
        self.check_singleton()
        key = f"extract.{self._name}.{self.id}"
        if after:
            key += ".after_readings"
        job = self.delayed(
            channel=JOB_CHANNEL,
            eta=delay or None,
            identity_key=key,
            after=after or None,
            name=f"Extract {self._get_extract_document_type()}: {self.display_name}",
        )._job_extract()
        self.extract_state = "queued"
        return job

    def _await_readings(self, source: Document) -> bool:
        attachment = self.env["ir.attachment"].browse(
            source.options.get("attachment_id") or ()
        )
        if not source.wanted or not attachment:
            return False
        jobs = self.env["ir.job"]
        for representation in sorted(source.wanted):
            jobs |= attachment._await_reading(representation)
        if not jobs:
            return False
        self._extract_later(after=jobs)
        self.write(
            {
                "extract_state": "waiting",
                "extract_pending": {
                    "readings": sorted(source.wanted),
                    "attachment_id": attachment.id,
                },
                "extract_error": False,
            }
        )
        return True

    @api.job(channel=JOB_CHANNEL, max_retries=3, max_defers=WAIT_ATTEMPTS)
    def _job_extract(self) -> None:
        self.check_singleton()
        result = self._extract_document(up_to=GENERATIVE, allow_pending=True)
        if result is not None and result.waiting:
            self.env["ir.job"]._defer(
                WAIT_SECONDS,
                reason=f"{result.pending['strategy']} is still reading the document.",
            )

    def _extract_document(self, up_to: int = GENERATIVE, allow_pending: bool = False):
        self.check_singleton()
        doc_type = self._get_extract_document_type()
        if not doc_type:
            raise ValueError(
                f"{self._name} inherits mixin.extract without "
                "declaring _extract_document_type"
            )
        if doc_type not in known_schemas():
            raise ValueError(
                f"{self._name} declares document type {doc_type!r}, which no "
                f"module registers; known: {', '.join(known_schemas())}"
            )

        source = self._get_extract_source()
        if source is None:
            self.write(
                {
                    "extract_state": "failed",
                    "extract_error": "No document to read.",
                }
            )
            return None
        if allow_pending:
            source.options["read_up_to"] = METERED
        source.options["defer_async"] = True

        pending = self.extract_pending or None
        self.extract_state = "running"
        try:
            result = cascade.run(
                source,
                doc_type,
                env=self.env,
                up_to=up_to,
                allow_pending=allow_pending,
                pending=pending if pending and "strategy" in pending else None,
            )
        except psycopg.Error:
            raise
        except Exception as e:
            _logger.exception("Extraction failed on %s %s", self._name, self.id)
            self.write({"extract_state": "failed", "extract_error": str(e)})
            return None

        if result.waiting:
            self.write({"extract_state": "waiting", "extract_pending": result.pending})
            return result
        if not result.satisfied and self._await_readings(source):
            return None

        attachment = self.env["ir.attachment"].browse(
            source.options.get("attachment_id") or ()
        )
        if attachment:
            attachment._keep_costly_readings(source)
        self.write(
            {
                "extract_pending": False,
                "extract_state": "done" if result.satisfied else "partial",
                "extract_result": _as_json(result),
                "extract_missing": {
                    "fields": list(result.missing),
                    "rules": list(result.violations),
                },
                "extract_error": "; ".join(source.errors.values()) or False,
            }
        )
        self._update_from_extraction(result)
        return result

    def _corrections_in(self, vals: dict[str, Any]) -> dict[str, Any]:
        self.check_singleton()
        if not self.extract_result or not self._extract_target:
            return {}
        found = {}
        for schema_field, model_field in self._extract_target.items():
            if model_field not in vals:
                continue
            read = (self.extract_result or {}).get(schema_field)
            written = self._extract_compare_value(model_field, vals[model_field])
            if (
                not read
                or written is NOT_COMPARABLE
                or read.get("value") in (None, written)
            ):
                continue
            found[schema_field] = {
                "read": read.get("value"),
                "read_by": read.get("source"),
                "corrected_to": written,
            }
        return found


def _as_json(result) -> dict[str, Any]:
    return {
        name: {
            "value": field.value,
            "source": field.source,
            "confidence": field.confidence,
            "disputed": field.disputed,
            "candidates": [
                {"value": c.value, "source": c.source, "confidence": c.confidence}
                for c in field.candidates
            ],
        }
        for name, field in result.fields.items()
    }
