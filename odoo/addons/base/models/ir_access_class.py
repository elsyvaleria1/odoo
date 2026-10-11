import typing

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.fields import NO_ACCESS, Domain
from odoo.libs.field_class_names import PER_RECORD, anonymous_spec, field_view_groups
from odoo.tools import SQL, frozendict

from .ir_access import (
    REACH_ANCHOR,
    AccessInfo,
    covers,
    parse_access_domain,
    parse_verbs,
)


def _writes_without_reading(rows: typing.Iterable[AccessInfo]) -> bool:
    for row in rows:
        reads, writes = covers(row, "read"), covers(row, "write")
        reach = row.reach or "all"
        if row.kind == "permission":
            if writes and not reads and reach != "none":
                return True
        elif reads and not writes and reach != "all":
            return True
    return False


class IrAccessClass(models.Model):
    _name = "ir.access.class"
    _description = "Field Class"
    _order = "name"

    name = fields.Char(
        required=True,
        help="How fields and rows name it, module-qualified: hr.compensation.",
    )
    description = fields.Char(
        translate=True,
        help="What the fields of the class have in common: an employee's pay.",
    )
    active = fields.Boolean(default=True)
    can_label = fields.Boolean(
        compute="_compute_can_label",
        search="_search_can_label",
        help="A record may carry the class as its sensitivity label: not when "
        "the class lets someone write without reading, as a label lets its "
        "writers edit what only its readers see.",
    )

    _name_unique = models.Constraint("UNIQUE (name)", "A field class's name is unique.")

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> typing.Any:
        classes = super().create(vals_list)
        self.env["ir.access"]._clear_access_caches()
        return classes

    def write(self, vals: dict[str, typing.Any]) -> bool:
        if "name" in vals and any(cls.name != vals["name"] for cls in self):
            raise ValidationError(
                self.env._(
                    "A field class is named in code; rename it there and in its data."
                )
            )
        result = super().write(vals)
        self.env["ir.access"]._clear_access_caches()
        return result

    def unlink(self) -> bool:
        result = super().unlink()
        self.env["ir.access"]._clear_access_caches()
        return result

    def _compute_can_label(self) -> None:
        refused = self.env["ir.access"]._label_refused_classes()
        for access_class in self:
            access_class.can_label = access_class.id not in refused

    def _search_can_label(self, operator: str, value: typing.Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        refused = Domain(
            "id", "in", list(self.env["ir.access"]._label_refused_classes())
        )
        return ~refused if (True in value) == (operator == "in") else refused


class IrAccess(models.Model):
    _inherit = "ir.access"

    model_id = fields.Many2one(
        required=False,
        help="The model whose records the row reaches; empty on a row for a field "
        "class.",
    )
    class_id = fields.Many2one(
        comodel_name="ir.access.class",
        index=True,
        ondelete="cascade",
        help="The field class the row grants or guards, instead of a model's "
        "records: reading (r) or writing (u) the fields of that class.",
    )

    exempt_group_ids = fields.Many2many(
        comodel_name="res.groups",
        relation="ir_access_exempt_group_rel",
        column1="access_id",
        column2="group_id",
        string="Exempt Groups",
        help="On a guard of a field class: the members of these groups are not "
        "bound by it (a manager whom a restriction of their colleagues spares).",
    )

    _model_or_class = models.Constraint(
        "CHECK ((model_id IS NULL) != (class_id IS NULL))",
        "An access is for a model's records or for a field class, not both.",
    )

    @api.constrains(
        "class_id",
        "operation",
        "verbs",
        "domain",
        "reach",
        "kind",
        "exempt_group_ids",
        "active",
    )
    def _check_class_row(self) -> None:
        for access in self:
            if access.exempt_group_ids and not (
                access.class_id and access.kind == "guard"
            ):
                raise ValidationError(
                    self.env._(
                        "%(access)s: only a guard of a field class spares groups.",
                        access=access.name,
                    )
                )
            if not access.class_id:
                continue
            if set(access.operation or "") - {"r", "u"} or parse_verbs(access.verbs):
                raise ValidationError(
                    self.env._(
                        "%(access)s is for a field class: it grants reading (r) "
                        "or writing (u) its fields, nothing else.",
                        access=access.name,
                    )
                )
            if access.domain or access.reach == "predicate":
                raise ValidationError(
                    self.env._(
                        "%(access)s is for a field class: it reaches the records "
                        "of each of the class's models through a reach, never a "
                        "domain or a predicate of one model.",
                        access=access.name,
                    )
                )
        self._check_class_still_labels()

    def _check_class_still_labels(self) -> None:
        classes = self.class_id
        if not classes:
            return
        infos = self._access_class_infos(self.search([("class_id", "in", classes.ids)]))
        refused = classes.filtered(
            lambda access_class: _writes_without_reading(
                infos.get(access_class.name, ())
            )
        )
        if labelling := self._labelling_classes(refused):
            raise ValidationError(
                self.env._(
                    "%(classes)s label records: a row of theirs cannot let anyone "
                    "write them without reading them, or those records hide "
                    "from the people they let edit.",
                    classes=", ".join(labelling.mapped("name")),
                )
            )

    @api.model
    def _labelling_classes(self, classes: typing.Any) -> typing.Any:
        graph = self.env.registry["mixin.access.graph"]
        tables = [
            model_cls._table
            for model_cls in self.env.registry.models.values()
            if not model_cls._abstract and issubclass(model_cls, graph)
        ]
        if not classes or not tables:
            return classes.browse()
        self.env.flush_all()
        self.env.cr.execute(
            SQL(" UNION ").join(
                SQL(
                    "SELECT access_label_id FROM %s WHERE access_label_id = ANY(%s)",
                    SQL.identifier(table),
                    classes.ids,
                )
                for table in tables
            )
        )
        return classes.browse([label_id for (label_id,) in self.env.cr.fetchall()])

    @api.model
    def _class_model_names(self, name: str) -> list[str]:
        registry = self.env.registry
        return sorted(
            model_name
            for model_name, model_cls in registry.models.items()
            if any(
                classes is not None
                and name in (*classes.read, *classes.write, *classes.read_alternative)
                for classes in (f.access_classes for f in model_cls._fields.values())
            )
        )

    @api.model
    def _label_classes(self) -> tuple[tuple[int, str], ...]:
        return tuple(
            sorted(
                (rows[0].class_id, name)
                for name, rows in self._get_class_access().items()
                if not _writes_without_reading(rows)
            )
        )

    @api.model
    def _label_refused_classes(self) -> dict[int, str]:
        return {
            rows[0].class_id: name
            for name, rows in self._get_class_access().items()
            if _writes_without_reading(rows)
        }

    @api.model
    def _get_class_access(self) -> frozendict:
        return self._get_access_rows()[1]

    def _access_class_infos(self, accesses: typing.Any) -> frozendict:
        rows = accesses.filtered(lambda access: access.class_id.active)
        result: dict[str, list[AccessInfo]] = {}
        for access in rows:
            result.setdefault(access.class_id.name, []).append(
                AccessInfo(
                    access.id,
                    access.group_id.id,
                    access.kind,
                    access.guard_scope,
                    access.operation or "",
                    parse_access_domain(""),
                    access.name,
                    reach=access.reach or "",
                    anchor=access.anchor or "",
                    exempt=frozenset(access.exempt_group_ids._ids),
                    class_id=access.class_id.id,
                )
            )
        return frozendict({name: tuple(infos) for name, infos in result.items()})

    def _field_view_groups(self, definitions, field, operation: str = "read"):
        return field_view_groups(
            definitions,
            field,
            lambda key: self._class_view_expression(definitions, key, operation),
            operation,
        )

    def _class_view_expression(self, definitions, name: str, operation: str):
        rows = self._get_class_access().get(name, ())
        granted = definitions.empty
        for row in rows:
            if (
                row.kind == "permission"
                and row.reach != "none"
                and covers(row, operation)
            ):
                granted |= definitions.from_ids([row.group_id])
        for row in rows:
            if row.kind == "guard" and row.reach == "none" and covers(row, operation):
                bound = (
                    definitions.universe
                    if row.guard_scope == "everyone"
                    else definitions.from_ids([row.group_id])
                )
                if row.exempt:
                    bound &= ~definitions.from_ids(sorted(row.exempt))
                granted &= ~bound
        return granted

    @api.model
    def _field_class_allowed(self, name: str, operation: str) -> bool | str:
        spec = anonymous_spec(name)
        if spec is not None:
            return self._field_group_spec_allowed(spec)
        scopes = self.env.user._get_group_scopes()
        everywhere = somewhere = guarded = False
        for row in self._get_class_access().get(name, ()):
            if not covers(row, operation):
                continue
            reach = row.reach or "all"
            if row.kind == "permission":
                if row.group_id not in scopes or reach == "none":
                    continue
                if reach == "all" and scopes[row.group_id] is None:
                    everywhere = True
                else:
                    somewhere = True
                continue
            binds = row.guard_scope == "everyone"
            if reach == "all" or not (binds or row.group_id in scopes):
                continue
            exempt = [scopes[group_id] for group_id in row.exempt if group_id in scopes]
            if None in exempt:
                continue
            if (
                reach == "none"
                and not exempt
                and (binds or scopes[row.group_id] is None)
            ):
                return False
            guarded = True
        if not (everywhere or somewhere):
            return False
        return PER_RECORD if guarded or not everywhere else True

    @api.model
    def _field_group_spec_allowed(self, spec: str) -> bool | str:
        user = self.env.user
        if not user._get_group_signature()[1]:
            return user.has_groups(spec)
        terms = self._group_spec_terms(spec)
        if terms is None:
            return False
        named_positive, positives, negatives = terms
        scopes = user._get_group_scopes()
        per_record = False
        for group_id in negatives:
            if scopes[group_id] is None:
                return False
            per_record = True
        if named_positive:
            if not positives:
                return False
            if all(scopes[group_id] is not None for group_id in positives):
                per_record = True
        return PER_RECORD if per_record else True

    @api.model
    def _group_spec_terms(self, spec: str) -> tuple[bool, list[int], list[int]] | None:
        if spec == NO_ACCESS:
            return None
        user = self.env.user
        named_positive = named = False
        positives: list[int] = []
        negatives: list[int] = []
        for token in spec.split(","):
            token = token.strip()
            if not token:
                continue
            named = True
            negative = token.startswith("!")
            named_positive = named_positive or not negative
            ext_id = token.removeprefix("!")
            group_id = user._group_id(ext_id)
            if group_id is not None and user._has_group_effective(ext_id):
                (negatives if negative else positives).append(group_id)
        return (named_positive, positives, negatives) if named else None

    @api.model
    def _field_class_domain(self, name: str, operation: str, model_name: str) -> Domain:
        scopes = self.env.user._get_group_scopes()
        permissions: list[Domain] = []
        guards: list[Domain] = []
        spec = anonymous_spec(name)
        if spec is not None:
            terms = self._group_spec_terms(spec)
            if terms is None:
                return Domain.FALSE
            named_positive, positives, negatives = terms
            if named_positive:
                permissions = [
                    self._scoped_verdict(model_name, True, scopes[group_id])
                    for group_id in positives
                ]
            else:
                permissions = [Domain.TRUE]
            guards = [
                self._scoped_verdict(model_name, False, scopes[group_id])
                for group_id in negatives
            ]
            return Domain.OR(permissions) & Domain.AND(guards)
        domain_of = self._row_domains()
        for row in self._get_class_access().get(name, ()):
            if not covers(row, operation):
                continue
            binds = row.kind == "guard" and row.guard_scope == "everyone"
            if not binds and row.group_id not in scopes:
                continue
            domain = (
                domain_of(model_name, row)
                if self._row_reaches_model(row, model_name)
                else Domain.FALSE
            )
            if not binds:
                domain = self._scoped(model_name, row, domain, scopes[row.group_id])
            for group_id in row.exempt & scopes.keys():
                domain |= self._scoped_verdict(model_name, True, scopes[group_id])
            (permissions if row.kind == "permission" else guards).append(domain)
        return Domain.OR(permissions) & Domain.AND(guards)

    def _row_reaches_model(self, row: AccessInfo, model_name: str) -> bool:
        if row.reach not in REACH_ANCHOR:
            return True
        key = row.anchor or REACH_ANCHOR[row.reach]
        return key in self.env.registry.model_anchors.get(model_name, {})

    def _scoped_verdict(
        self, model_name: str, permission: bool, companies: frozenset[int] | None
    ) -> Domain:
        domain = Domain.TRUE if permission else Domain.FALSE
        if companies is None:
            return domain
        within = self._company_scope_domain(model_name, companies)
        if within is None:
            return domain
        return domain & within if permission else domain | ~within
