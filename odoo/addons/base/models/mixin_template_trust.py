import logging
from collections.abc import Collection, Iterator
from typing import Any, Literal, Self

from lxml import etree

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog
from odoo.modules import Manifest
from odoo.tools import SQL
from odoo.tools.convert import is_loading_data_file, xml_import
from odoo.tools.misc import file_path

from .ir_access import NON_STANDARD_MODULES

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class MixinTemplateTrust(models.AbstractModel):
    _name = "mixin.template.trust"
    _inherit = ["mixin.template.authoring"]
    _description = "Template Trust Mixin"

    shipped_digests = fields.Json(
        copy=False,
        classification="base.template_trust",
        help="Per template field, the digest of what the text its module file "
        "ships evaluates: a text with the same digest in the same field is "
        "trusted as the module's own, wherever it is stored.",
    )

    _shipped_digests_index = models.Index("USING gin (shipped_digests jsonb_path_ops)")

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if self._is_loading_shipped_templates():
            units = self._get_template_unit_fields()
            for vals in vals_list:
                if written := vals.keys() & units:
                    vals["shipped_digests"] = self.new(vals)._get_unit_digests(written)
        return super().create(vals_list)

    def write(self, vals: ValuesType) -> Literal[True]:
        result = super().write(vals)
        if self._is_loading_shipped_templates() and (
            written := vals.keys() & self._get_template_unit_fields()
        ):
            self._record_shipped_digests(written)
        return result

    def _is_loading_shipped_templates(self) -> bool:
        return self.env.su and is_loading_data_file()

    def _get_unit_digests(
        self, fnames: Collection[str], digests: dict[str, str] | None = None
    ) -> dict[str, str]:
        digests = dict(digests or {})
        for fname in fnames:
            if unit := self._get_template_unit(fname, self[fname]):
                digests[fname] = unit.digest
            else:
                digests.pop(fname, None)
        return digests

    def _record_shipped_digests(self, fnames: Collection[str]) -> None:
        for record in self:
            digests = record._get_unit_digests(fnames, record.shipped_digests)
            if digests != (record.shipped_digests or {}):
                _debug.lifecycle(
                    "shipped_digests_recorded",
                    model=self._name,
                    record=record.id,
                    fields=sorted(digests),
                )
                record.shipped_digests = digests

    def _get_shipped_units(
        self, units: Collection[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        if not units:
            return set()
        self.flush_model(["shipped_digests"])
        fnames, digests = zip(*units, strict=True)
        rows = self.env.execute_query(
            SQL(
                """SELECT unit.fname, unit.digest
                     FROM unnest(%s::text[], %s::text[]) AS unit(fname, digest)
                    WHERE EXISTS (
                              SELECT FROM %s shipped
                               WHERE shipped.shipped_digests
                                     @> jsonb_build_object(unit.fname, unit.digest)
                          )""",
                list(fnames),
                list(digests),
                SQL.identifier(self._table),
            )
        )
        return {(fname, digest) for fname, digest in rows}

    def _get_shipped_sources(self) -> dict[Self, dict[str, Any]]:
        fnames = self._get_template_unit_fields()
        external_ids = self._get_external_ids()
        documents: dict[str, list[tuple[str, etree._ElementTree]]] = {}
        sources: dict[Self, dict[str, Any]] = {}
        for record in self:
            for xmlid in external_ids[record.id]:
                module, _dot, name = xmlid.partition(".")
                if module in NON_STANDARD_MODULES:
                    continue
                if module not in documents:
                    documents[module] = list(_iter_module_documents(module))
                for path, document in documents[module]:
                    for node in document.xpath(
                        "//record[@model = $model][@id = $name or @id = $xmlid]",
                        model=self._name,
                        name=name,
                        xmlid=xmlid,
                    ):
                        importer = xml_import(
                            self.env, module, {}, mode="update", xml_filename=path
                        )
                        values = importer._eval_record_fields(
                            node, importer.env, self, xmlid, []
                        )
                        sources.setdefault(record, {}).update(
                            (fname, value)
                            for fname, value in (values or {}).items()
                            if fname in fnames
                        )
        return sources

    @api.model
    def _backfill_shipped_digests(self) -> tuple[int, int]:
        pending = (
            self.with_context(active_test=False)
            .search([("shipped_digests", "=", False)])
            ._filter_module_records()
        )
        sources = pending._get_shipped_sources()
        for record, values in sources.items():
            digests = {
                fname: unit.digest
                for fname, value in values.items()
                if (
                    unit := record._get_template_unit(
                        fname, record._fields[fname].convert_to_cache(value, record)
                    )
                )
            }
            if digests:
                record.shipped_digests = digests
        return len(sources), len(pending) - len(sources)

    def _filter_module_records(self) -> Self:
        external_ids = self._get_external_ids()
        return self.filtered(
            lambda record: any(
                xmlid.partition(".")[0] not in NON_STANDARD_MODULES
                for xmlid in external_ids[record.id]
            )
        )


def _iter_module_documents(module: str) -> Iterator[tuple[str, etree._ElementTree]]:
    manifest = Manifest.for_addon(module, display_warning=False) or {}
    for data_file in (*manifest.get("data", ()), *manifest.get("demo", ())):
        if not data_file.endswith(".xml"):
            continue
        try:
            path = file_path(f"{module}/{data_file}")
            yield path, etree.parse(path)
        except FileNotFoundError, ValueError, etree.XMLSyntaxError:
            continue


def migrate_shipped_digests(env: api.Environment, model: str) -> None:
    templates = env[model].with_context(active_test=False, lang="en_US")
    read, unreadable = templates._backfill_shipped_digests()
    _logger.info(
        "Shipped digests of %s: %d records read from their files, %d not found there",
        model,
        read,
        unreadable,
    )
    if findings := templates._audit_template_authoring():
        _logger.warning(
            "%d stored %s records hold what an author below Settings may no longer "
            "save: they render unchanged, and such an author's next save of one is "
            "refused while it still holds them:\n%s",
            len(findings),
            model,
            "\n".join(
                f"{record}: {'; '.join(errors)}" for record, errors in findings.items()
            ),
        )
