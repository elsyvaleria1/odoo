from collections.abc import Callable, Mapping
from typing import Literal, Self

from lxml import etree

from odoo import api, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.ir_qweb import (
    BINDING_PREFIX,
    iter_template_bindings,
    iter_template_expressions,
    restricted_template_errors,
)

_debug = DebugLog(__name__)

ARCH_FIELDS = frozenset({"arch", "arch_base", "arch_db"})
COPY_CHECKED_BY_CALLER = object()


def _arch_expressions(arch: str | None) -> set[str]:
    if not arch:
        return set()
    try:
        root = etree.fromstring(arch)
    except etree.XMLSyntaxError:
        return set()
    return {
        *iter_template_expressions(root),
        *(f"{BINDING_PREFIX}{name}" for name in iter_template_bindings(root)),
    }


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def _is_restricted_template_author(self) -> bool:
        return not self.env.su and not self.env.user._is_system()

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        views = super().create(vals_list)
        if (
            self.env.context.get("template_authoring_copy")
            is not COPY_CHECKED_BY_CALLER
        ):
            views._check_template_authoring({})
        return views

    def copy(self, default: ValuesType | None = None) -> Self:
        if not self._is_restricted_template_author():
            return super().copy(default)
        originals = self.with_context(template_authoring_copy=COPY_CHECKED_BY_CALLER)
        copies = super(IrUiView, originals).copy(default).with_env(self.env)
        copies._check_template_authoring(
            {},
            originals={
                copy.id: original for original, copy in zip(self, copies, strict=True)
            },
        )
        return copies

    def write(self, vals: ValuesType) -> Literal[True]:
        if not (ARCH_FIELDS & vals.keys() and self._is_restricted_template_author()):
            return super().write(vals)
        previous = {view.id: view.arch_db for view in self if view.type == "qweb"}
        result = super().write(vals)
        self._check_template_authoring(previous)
        return result

    def _update_field_translations(
        self,
        field_name: str,
        translations: dict[str, str | Literal[False] | dict[str, str]],
        digest: Callable[[str], str] | None = None,
        source_lang: str = "",
    ) -> bool:
        if field_name != "arch_db" or not self._is_restricted_template_author():
            return super()._update_field_translations(
                field_name, translations, digest=digest, source_lang=source_lang
            )
        previous = {view.id: view.arch_db for view in self if view.type == "qweb"}
        result = super()._update_field_translations(
            field_name, translations, digest=digest, source_lang=source_lang
        )
        for lang in translations:
            self.with_context(lang=lang)._check_template_authoring(previous)
        return result

    def _check_template_authoring(
        self,
        previous: dict[int, str | None],
        originals: Mapping[int, Self] | None = None,
    ) -> None:
        if not self._is_restricted_template_author():
            return
        errors = []
        for view in self.filtered(lambda view: view.type == "qweb" and view.arch_db):
            try:
                root = etree.fromstring(view.arch_db)
            except etree.XMLSyntaxError:
                continue
            trust = view._template_trust(
                previous.get(view.id), original=(originals or {}).get(view.id)
            )
            refused = restricted_template_errors(root, trust)
            errors += [f"{view.key or view.name}: {error}" for error in refused]
        if errors:
            _debug.logic(
                "template_authoring_refused",
                views=self.ids,
                uid=self.env.uid,
                errors=len(errors),
            )
            raise AccessError(
                self.env._(
                    "Only administrators may add expressions that reach the environment "
                    "or call methods to a template:\n%(errors)s",
                    errors="\n".join(errors[:20]),
                )
            )

    def _template_trust(
        self,
        previous_arch: str | None,
        *,
        module_only: bool = False,
        original: Self | None = None,
    ) -> Callable[[str], bool]:
        trusted: set[str] | None = None

        def is_trusted(expression: str) -> bool:
            nonlocal trusted
            if trusted is None:
                trusted = self._template_trusted_expressions(
                    previous_arch, module_only=module_only
                )
                if original:
                    trusted |= original._template_trusted_expressions(original.arch_db)
            return expression in trusted

        return is_trusted

    def _template_trusted_expressions(
        self, previous_arch: str | None, *, module_only: bool = False
    ) -> set[str]:
        self.check_singleton()
        related = self.with_context(active_test=False)
        if self.key:
            related |= related.search([("key", "=", self.key), ("id", "!=", self.id)])
        related |= related.inherit_id
        sources = [self._get_arch_from_file()]
        sources += [view._get_arch_from_file() for view in related - self]
        if not module_only:
            sources += [previous_arch, *(view.arch_db for view in related - self)]
        return set().union(*map(_arch_expressions, sources))

    @api.model
    def _audit_template_authoring(self) -> dict[str, list[str]]:
        findings = {}
        views = self.with_context(active_test=False).search([("type", "=", "qweb")])
        for view in views:
            if not view.arch_db or (view.arch_fs and not view.arch_updated):
                continue
            try:
                root = etree.fromstring(view.arch_db)
            except etree.XMLSyntaxError:
                continue
            trust = view._template_trust(None, module_only=True)
            if errors := restricted_template_errors(root, trust):
                findings[f"{view.key or view.name} ({view.id})"] = errors
        return findings
