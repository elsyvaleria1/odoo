import copy
from collections.abc import Callable, Iterator
from typing import Literal, Self

from lxml import etree

from odoo import api, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import unique
from odoo.tools.misc import file_path

from odoo.addons.base.models.ir_qweb import (
    TEMPLATE_REF,
    evaluated_attributes,
    template_context_changes,
)
from odoo.addons.base.models.ir_ui_view import (
    hierarchy_views,
    is_view_declared_optional,
)

_debug = DebugLog(__name__)

Hierarchy = dict[models.BaseModel, list[models.BaseModel]]


def _iter_overlay_content(specs_tree: etree._Element) -> Iterator[etree._Element]:
    specs = [specs_tree]
    while specs:
        spec = specs.pop()
        if spec.tag == "data":
            specs.extend(child for child in spec if isinstance(child.tag, str))
        elif spec.get("position") != "attributes":
            for child in spec:
                if isinstance(child.tag, str) and child.get("position") != "move":
                    yield from child.iter(etree.Element)


def _marked_arch(
    arch: etree._Element, view_id: int, *, trusted: bool, whole: bool
) -> etree._Element:
    for spec in list(arch.iter("attribute")):
        if spec.get("name") == TEMPLATE_REF:
            spec.getparent().remove(spec)
    for element in arch.iter(etree.Element):
        element.attrib.pop(TEMPLATE_REF, None)
    if trusted:
        elements = arch.iter(etree.Element) if whole else _iter_overlay_content(arch)
        rank = 0
        for element in list(elements):
            if evaluated_attributes(element):
                element.set(TEMPLATE_REF, f"{view_id}.{rank}")
                rank += 1
            else:
                element.set(TEMPLATE_REF, f"{view_id}.plain")
    return arch


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def write(self, vals: ValuesType) -> Literal[True]:
        if "active" in vals and not vals["active"]:
            self._check_template_removal(deactivated=True)
        result = super().write(vals)
        if not {"key", "website_id"}.isdisjoint(vals):
            self.exists()._check_template_contexts()
        return result

    def unlink(self) -> bool:
        self._check_template_removal(deactivated=False)
        return super().unlink()

    def _check_xml(self) -> bool:
        result = super()._check_xml()
        self._check_template_contexts()
        return result

    def _check_template_contexts(self) -> None:
        if not self._is_restricted_template_author():
            return
        errors = [
            error
            for refused in self._get_template_context_errors().values()
            for error in refused
        ]
        if errors:
            _debug.logic(
                "template_context_refused",
                views=self.ids,
                uid=self.env.uid,
                errors=len(errors),
            )
            raise AccessError(
                self.env._(
                    "Only administrators may change how a template a module ships "
                    "evaluates:\n%(errors)s",
                    errors="\n".join(errors[:20]),
                )
            )

    def _check_template_removal(self, *, deactivated: bool) -> None:
        if not self._is_restricted_template_author():
            return
        errors = [
            error
            for refused in self._get_template_removal_errors(deactivated).values()
            for error in refused
        ]
        if errors:
            _debug.logic(
                "template_removal_refused",
                views=self.ids,
                uid=self.env.uid,
                errors=len(errors),
            )
            raise AccessError(
                self.env._(
                    "Only administrators may remove a template a module ships where "
                    "that changes how another one evaluates:\n%(errors)s",
                    errors="\n".join(errors[:20]),
                )
            )

    def _comparing(self) -> Self:
        return self.with_privilege(
            "base.privilege_compare_template_contexts",
            reason="compare template contexts",
        )

    def _get_template_primaries(self) -> Self:
        roots = self.browse(unique(view._get_primary_root().id for view in self))
        return roots | roots._get_primary_descendants()

    def _get_template_context_errors(self) -> dict[Self, list[str]]:
        views = self._comparing().filtered(lambda view: view.type == "qweb")
        if not views:
            return {}
        errors = views._get_template_shadow_errors()
        for primary, refused in (
            views._get_template_primaries()._get_combined_context_errors(views).items()
        ):
            errors.setdefault(primary, []).extend(refused)
        return errors

    def _get_template_shadow_errors(self) -> dict[Self, list[str]]:
        authored = self.filtered(
            lambda view: view.mode == "primary" and view.key
        )._get_authored_templates()
        if not authored:
            return {}
        holders = self.with_context(active_test=False).search(
            [
                ("type", "=", "qweb"),
                ("key", "in", authored.mapped("key")),
                ("id", "not in", authored.ids),
            ]
        )
        trusted_keys = set((holders - holders._get_authored_templates()).mapped("key"))
        return {
            view: [
                f"{view.key}: "
                + self.env._(
                    "it takes the key of a template a module ships, which other "
                    "templates call"
                )
            ]
            for view in authored
            if view.key in trusted_keys
        }

    def _get_authored_templates(self) -> Self:
        units = {
            view: unit
            for view in self
            if (unit := view._get_template_unit("arch_db", view.arch_db))
        }
        shipped = self._get_shipped_units(
            {("arch_db", unit.digest) for unit in units.values()}
        )
        return self.browse(
            [
                view.id
                for view, unit in units.items()
                if ("arch_db", unit.digest) not in shipped and not unit.errors
            ]
        )

    def _get_shipped_texts(self) -> dict[int, str]:
        texts = {}
        for view in self:
            text = view._get_arch_from_file()
            if not text or text == view.arch:
                continue
            shipped = view._get_template_unit("arch_db", text)
            current = view._get_template_unit("arch_db", view.arch)
            if shipped and current and shipped.digest == current.digest:
                texts[view.id] = text
        return texts

    def _is_template_option(self) -> bool:
        self.check_singleton()
        xml_id = self.xml_id or self.key
        if not (self.arch_fs and xml_id):
            return False
        try:
            return is_view_declared_optional(
                file_path(self.arch_fs, check_exists=False), xml_id
            )
        except OSError, etree.ParseError:
            return False

    def _get_trusted_hierarchy(
        self, tree: Self, hidden: Self
    ) -> tuple[Self, Hierarchy, Self]:
        known = set(tree.ids)
        while True:
            ((root, hierarchy),) = self.with_context(
                ir_ui_view_hidden_ids=hidden.ids
            )._get_hierarchies()
            joined = self.browse(
                [
                    view.id
                    for view in (root, *hierarchy_views(hierarchy))
                    if view.id not in known
                ]
            )
            known.update(joined.ids)
            found = joined._get_authored_templates()
            if not found:
                return root, hierarchy, hidden
            hidden |= found

    def _get_combined_context_errors(self, edited: Self) -> dict[Self, list[str]]:
        hierarchies = self._get_hierarchies()
        trees = [
            self.browse(
                unique([root.id, *(view.id for view in hierarchy_views(hierarchy))])
            )
            for root, hierarchy in hierarchies
        ]
        every = self.browse(unique(view.id for tree in trees for view in tree))
        authored = every._get_authored_templates()
        shipped_texts = (every & edited - authored)._get_shipped_texts()
        errors = {}
        for primary, (root, hierarchy), tree in zip(
            self, hierarchies, trees, strict=True
        ):
            if not (tree & authored or shipped_texts.keys() & set(tree.ids)):
                continue
            if refused := primary._get_context_errors(
                root, hierarchy, tree, authored, shipped_texts
            ):
                errors[primary] = refused
        _debug.logic(
            "template_contexts_checked",
            primaries=len(self),
            authored=len(authored),
            edited=len(shipped_texts),
            refused=len(errors),
        )
        return errors

    def _get_context_errors(
        self,
        root: Self,
        hierarchy: Hierarchy,
        tree: Self,
        authored: Self,
        shipped_texts: dict[int, str],
    ) -> list[str]:
        served_of = self._get_marked_archs(authored, root)
        try:
            served = root._combine_marked(hierarchy, served_of)
        except (ValidationError, ValueError) as error:
            return [
                self.env._(
                    "%(template)s does not combine: %(error)s",
                    template=self.key or self.name,
                    error=error,
                )
            ]
        if root in authored:
            return self._describe_context_changes(served, None, set())
        trusted_root, trusted_hierarchy, hidden = self._get_trusted_hierarchy(
            tree, authored
        )
        trusted_of = self._get_marked_archs(hidden, trusted_root, shipped_texts)
        try:
            trusted = trusted_root._combine_marked(trusted_hierarchy, trusted_of)
        except (ValidationError, ValueError) as error:
            _debug.logic("template_contexts.trusted_uncombined", root=root.id)
            return [
                self.env._(
                    "%(template)s: a module's extension applies to what an "
                    "author added: %(error)s",
                    template=self.key or self.name,
                    error=error,
                )
            ]
        return self._describe_context_changes(
            served,
            trusted,
            {
                trusted_root.id,
                *(view.id for view in hierarchy_views(trusted_hierarchy)),
            },
        )

    def _get_template_removal_errors(self, deactivated: bool) -> dict[Self, list[str]]:
        views = self._comparing().filtered(
            lambda view: view.type == "qweb" and view.mode != "primary"
        )
        removed = views._get_removed_templates(deactivated)
        removed -= removed._get_authored_templates()
        removed = removed.filtered(lambda view: not view._is_template_option())
        if not removed:
            return {}
        errors = {}
        for primary in removed._get_template_primaries():
            ((root, hierarchy),) = primary._get_hierarchies()
            tree = self.browse(
                unique([root.id, *(view.id for view in hierarchy_views(hierarchy))])
            )
            if not tree & removed:
                continue
            authored = tree._get_authored_templates()
            before_root, before, hidden = primary._get_trusted_hierarchy(tree, authored)
            after_root, after, _hidden = primary._get_trusted_hierarchy(
                tree, hidden | removed
            )
            staying = {
                after_root.id,
                *(view.id for view in hierarchy_views(after)),
            }
            marked = primary._get_marked_archs(hidden, before_root)
            try:
                trusted = before_root._combine_marked(before, marked)
                remaining = after_root._combine_marked(after, marked)
            except ValidationError, ValueError:
                continue
            if refused := primary._describe_context_changes(
                remaining, trusted, staying, staying=staying
            ):
                errors[primary] = refused
        return errors

    def _get_removed_templates(self, deactivated: bool) -> Self:
        return self

    def _get_marked_archs(
        self, authored: Self, root: Self, texts: dict[int, str] | None = None
    ) -> Callable[[Self], etree._Element]:
        marked: dict[int, etree._Element] = {}

        def arch_of(view: Self) -> etree._Element:
            if view.id not in marked:
                text = (texts or {}).get(view.id) or view.arch or "<data/>"
                marked[view.id] = _marked_arch(
                    etree.fromstring(text),
                    view.id,
                    trusted=view not in authored,
                    whole=view == root,
                )
            return copy.deepcopy(marked[view.id])

        return arch_of

    def _combine_marked(
        self, hierarchy: Hierarchy, arch_of: Callable[[Self], etree._Element]
    ) -> etree._Element:
        return self.with_context(
            inherit_branding=False,
            validate_view_ids=None,
            ir_ui_view_tree_cut_off_view=None,
        )._combine_tree(hierarchy, arch_of)[0]

    def _describe_context_changes(
        self,
        served: etree._Element,
        trusted: etree._Element | None,
        trusted_ids: set[int],
        staying: set[int] | None = None,
    ) -> list[str]:
        changes = template_context_changes(
            served, trusted, self.env["ir.qweb"]._get_authoring_directives()
        )
        how_said = {
            "removed": self.env._("it is removed or replaced"),
            "added": self.env._("it gains directives, or is copied"),
            "directives": self.env._("what it evaluates changes"),
            "placed": self.env._("it is moved or wrapped in directives"),
            "bindings": self.env._("a name it reads is bound differently"),
            "authored": self.env._("it evaluates only where an author put it"),
        }
        errors = []
        for ref, (how, label) in sorted(changes.items()):
            view = self.browse(int(ref.partition(".")[0]))
            if staying is not None and view.id not in staying:
                continue
            if how == "added" and view.id not in trusted_ids:
                how = "authored"
            errors.append(f"{view.key or view.name} {label}: {how_said[how]}")
        return errors

    @api.model
    def _audit_template_authoring(self) -> dict[str, list[str]]:
        findings = super()._audit_template_authoring()
        views = self.with_context(active_test=False).search([("type", "=", "qweb")])
        edited = views.filtered(lambda view: view.arch_fs and view.arch_updated)
        audited = views._get_authored_templates() | edited
        for primary, errors in audited._get_template_context_errors().items():
            findings.setdefault(
                f"{primary.key or primary.name} ({primary.id})", []
            ).extend(errors)
        return findings
