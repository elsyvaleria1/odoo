from collections.abc import Callable, Collection
from typing import Any, Literal, NamedTuple, Self

from odoo import api, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class TemplateUnit(NamedTuple):
    digest: str
    errors: list[str]


class MixinTemplateAuthoring(models.AbstractModel):
    _name = "mixin.template.authoring"
    _description = "Template Authoring Mixin"

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        records = super().create(vals_list)
        records._check_template_authoring()
        return records

    def write(self, vals: ValuesType) -> Literal[True]:
        units = self._get_template_unit_fields()
        if not units:
            return super().write(vals)
        written = vals.keys() & units
        may_move = not vals.keys() <= units
        before = (
            {record.id: record._get_template_unit_context() for record in self}
            if may_move
            else {}
        )
        result = super().write(vals)
        moved = (
            self.filtered(
                lambda record: record._get_template_unit_context() != before[record.id]
            )
            if may_move
            else self.browse()
        )
        if written and (rest := self - moved):
            rest._check_template_authoring(written)
        if moved:
            moved._check_template_authoring()
        return result

    def _update_field_translations(
        self,
        field_name: str,
        translations: dict[str, str | Literal[False] | dict[str, str]],
        digest: Callable[[str], str] | None = None,
        source_lang: str = "",
    ) -> bool:
        result = super()._update_field_translations(
            field_name, translations, digest=digest, source_lang=source_lang
        )
        if field_name in self._get_template_unit_fields():
            for lang in translations:
                self.with_context(lang=lang)._check_template_authoring({field_name})
        return result

    def _get_template_unit_fields(self) -> set[str]:
        return set()

    def _get_template_unit(self, fname: str, source: Any) -> TemplateUnit | None:
        return None

    def _get_template_unit_context(self) -> Any:
        return None

    def _get_template_name(self) -> str:
        return self.display_name

    def _get_template_unit_label(self, fname: str) -> str:
        return self._fields[fname].string

    def _is_restricted_template_author(self) -> bool:
        return not self.env.su and not self.env.user._is_system()

    def _get_shipped_units(
        self, units: Collection[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        return set()

    def _get_template_authoring_errors(
        self, fnames: Collection[str] | None = None
    ) -> dict[Self, list[str]]:
        scanned = self._get_template_unit_fields()
        if fnames is not None:
            scanned &= set(fnames)
        refused: dict[Self, list[tuple[str, TemplateUnit]]] = {}
        for record in self:
            for fname in sorted(scanned):
                unit = record._get_template_unit(fname, record[fname])
                if unit and unit.errors:
                    refused.setdefault(record, []).append((fname, unit))
        shipped = self._get_shipped_units(
            {
                (fname, unit.digest)
                for units in refused.values()
                for fname, unit in units
            }
        )
        return {
            record: errors
            for record, units in refused.items()
            if (
                errors := [
                    f"{record._get_template_unit_label(fname)}: {error}"
                    for fname, unit in units
                    if (fname, unit.digest) not in shipped
                    for error in unit.errors
                ]
            )
        }

    def _check_template_authoring(self, fnames: Collection[str] | None = None) -> None:
        if not self._is_restricted_template_author():
            return
        errors = [
            error
            for refused in self._get_template_authoring_errors(fnames).values()
            for error in refused
        ]
        if errors:
            _debug.logic(
                "template_authoring_refused",
                model=self._name,
                records=self.ids,
                uid=self.env.uid,
                errors=len(errors),
            )
            raise AccessError(self._prepare_template_authoring_error(errors))

    def _prepare_template_authoring_error(self, errors: list[str]) -> str:
        return self.env._(
            "Only administrators may add expressions that reach the environment "
            "or call methods to a template:\n%(errors)s",
            errors="\n".join(errors[:20]),
        )

    @api.model
    def _audit_template_authoring(self) -> dict[str, list[str]]:
        records = self.with_context(active_test=False).search([])
        return {
            f"{record._get_template_name()} ({record.id})": errors
            for record, errors in records._get_template_authoring_errors().items()
        }
