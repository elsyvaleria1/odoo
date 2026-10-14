from __future__ import annotations

import typing
from dataclasses import dataclass

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from .ir_access import predicate_arguments

_debug = DebugLog(__name__)

if typing.TYPE_CHECKING:
    from odoo.tools import Query


@dataclass(frozen=True)
class AccessGraph:
    parent: str
    grants: str
    roles: tuple[str, ...]
    owner: str | None = None
    boundary: str | None = None
    container: tuple[str, typing.Any] | None = None


def path_ids(column: SQL) -> SQL:
    return SQL("string_to_array(rtrim(%s, '/'), '/')::int4[]", column)


def _graph_depends(model: models.BaseModel) -> list[str]:
    graph = type(model)._access_graph
    if graph is None:
        return []
    depends = [graph.parent, f"{graph.parent}.access_scope_path"]
    if graph.boundary:
        depends.append(graph.boundary)
    return depends


def _label_depends(model: models.BaseModel) -> list[str]:
    graph = type(model)._access_graph
    if graph is None:
        return ["access_label_id"]
    depends = ["access_label_id", f"{graph.parent}.access_inherited_label_id"]
    if graph.boundary:
        depends.append(graph.boundary)
    return depends


def _role_depends(model: models.BaseModel) -> list[str]:
    graph = type(model)._access_graph
    if graph is None:
        return []
    grant_model = model.env[model._fields[graph.grants].comodel_name]
    names = type(grant_model)._access_grant_names
    depends = [
        "access_scope_path",
        f"{graph.grants}.partner_id",
        f"{graph.grants}.group_id",
        f"{graph.grants}.company_id",
        f"{graph.grants}.{names.role}",
        f"{graph.grants}.date_to",
    ]
    if graph.owner:
        depends.append(graph.owner)
    return depends


class MixinAccessGraph(models.AbstractModel):
    _name = "mixin.access.graph"
    _description = "Access Through a Tree of Grants"

    _access_graph: AccessGraph | None = None
    _access_label_field = "access_inherited_label_id"

    access_scope_path = fields.Char(
        compute="_compute_access_scope_path",
        recursive=True,
        store=True,
        copy=False,
        help="The nodes whose grants reach this one: its ancestors up to the "
        "nearest boundary, and itself.",
    )
    access_label_id = fields.Many2one(
        comodel_name="ir.access.class",
        string="Sensitivity Label",
        domain=[("can_label", "=", True)],
        help="Only the principals this field class grants reach the record and "
        "the records below it that carry no label of their own.",
    )
    access_inherited_label_id = fields.Many2one(
        comodel_name="ir.access.class",
        string="Effective Sensitivity Label",
        compute="_compute_access_inherited_label_id",
        recursive=True,
        store=True,
        index="btree_not_null",
        copy=False,
        help="The record's own label, else its nearest labelled ancestor's "
        "within its scope.",
    )
    access_role = fields.Selection(
        selection="_selection_access_role",
        compute="_compute_access_role",
        search="_search_access_role",
        compute_sudo=True,
        help="The role the current user holds on the record.",
    )

    @api.model_create_multi
    def create(self, vals_list: list[dict[str, typing.Any]]) -> typing.Any:
        nodes = super().create(vals_list)
        labelled = [
            node
            for node, vals in zip(nodes, vals_list, strict=True)
            if vals.get("access_label_id")
        ]
        self.browse([node.id for node in labelled])._check_access_label_change()
        return nodes

    def write(self, vals: dict[str, typing.Any]) -> bool:
        if "access_label_id" not in vals:
            return super().write(vals)
        self._check_access_label_change()
        result = super().write(vals)
        self.invalidate_model(["access_role"])
        return result

    @api.constrains("access_label_id")
    def _check_access_label_id(self) -> None:
        refused = self.env["ir.access"]._label_refused_classes()
        if names := {refused.get(label.id) for label in self.access_label_id} - {None}:
            raise ValidationError(
                self.env._(
                    "%(classes)s cannot label a record: it lets someone write "
                    "without reading, and the record would hide from them.",
                    classes=", ".join(sorted(names)),
                )
            )

    def _check_access_label_change(self) -> None:
        if self.env.su or self._access_graph is None or not self:
            return
        top = self._access_graph.roles[-1]
        if any(node.access_role != top for node in self):
            raise AccessError(
                self.env._(
                    "Only who holds the %(role)s role on a record changes its "
                    "sensitivity label.",
                    role=top,
                )
            )

    @api.depends(_label_depends)
    def _compute_access_inherited_label_id(self) -> None:
        graph = self._access_graph
        for node in self:
            inherits = (
                graph is not None
                and not node.access_label_id
                and not (graph.boundary and node[graph.boundary])
            )
            node.access_inherited_label_id = (
                node[graph.parent].access_inherited_label_id
                if inherits
                else node.access_label_id
            )

    def _access_label_reach(self, role: str) -> Domain:
        graph = self._access_graph
        operation = "read" if graph is None or role == graph.roles[0] else "write"
        return self._access_label_guard(operation)

    @api.model
    def _selection_access_role(self) -> list[tuple[str, str]]:
        graph = self._access_graph
        return [(role, role.capitalize()) for role in graph.roles] if graph else []

    @api.depends(_graph_depends)
    def _compute_access_scope_path(self) -> None:
        graph = self._access_graph
        if graph is None:
            self.access_scope_path = False
            return
        for node in self:
            parent = node[graph.parent]
            own = f"{node.id}/" if isinstance(node.id, int) else ""
            if not parent or (graph.boundary and node[graph.boundary]):
                node.access_scope_path = own
            else:
                node.access_scope_path = (parent.access_scope_path or "") + own

    @api.depends(_role_depends)
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_access_role(self) -> None:
        if self._access_graph is None:
            self.access_role = False
            return
        roles = self._access_graph.roles
        saved = self.filtered(lambda node: isinstance(node.id, int))
        for node in self - saved:
            node.access_role = roles[-1]
        if not saved:
            return
        if self.env.user._is_public():
            saved.access_role = False
            return
        ranks = self._access_graph_ranks(saved.ids)
        for node in saved:
            rank = ranks.get(node.id, 0)
            node.access_role = roles[rank - 1] if rank else False

    def _search_access_role(self, operator: str, value: typing.Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        if self._access_graph is None:
            return Domain.FALSE
        roles = self._access_graph.roles
        bands = [False, *roles]
        asked = [band in set(value) for band in bands]
        if operator == "not in":
            asked = [not wanted for wanted in asked]
        pieces = []
        start = None
        for index, wanted in enumerate([*asked, False]):
            if wanted and start is None:
                start = index
            elif not wanted and start is not None:
                lowest = (
                    Domain.TRUE
                    if start == 0
                    else self._access_graph_reach(bands[start])
                )
                above = (
                    ~self._access_graph_reach(bands[index])
                    if index < len(bands)
                    else Domain.TRUE
                )
                pieces.append(lowest & above)
                start = None
        return Domain.OR(pieces)

    def _access_graph_reach(self, role: str, **options: typing.Any) -> Domain:
        label = self._access_label_reach(role)
        return self._access_graph_domain(role, **options) & label

    def _access_graph_domain(
        self,
        role: str,
        *,
        groups: typing.Iterable[int] | None = None,
        exclude_groups: typing.Iterable[int] = (),
        partner: bool = True,
        owner: bool = True,
    ) -> Domain:
        if self.env.user._is_public():
            return Domain.FALSE
        sql = self._access_graph_condition(
            role,
            groups=groups,
            exclude_groups=exclude_groups,
            partner=partner,
            owner=owner,
        )

        def to_sql(model: MixinAccessGraph, alias: str, query: Query) -> SQL:
            model._access_graph_flush()
            return sql(alias, query)

        return Domain.custom(to_sql=to_sql)

    def _access_graph_group_ranks(self, group_id: int) -> dict[int, int]:
        graph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        ids = [node_id for node_id in self.ids if isinstance(node_id, int)]
        if not ids:
            return {}
        self._access_graph_flush()
        self.env.cr.execute(
            SQL(
                """SELECT node.id, max(array_position(%(roles)s, grant_row.%(role)s))
                     FROM %(table)s AS node
                     JOIN %(grant_table)s AS grant_row
                       ON grant_row.group_id = %(group)s
                      AND grant_row.%(resource)s = ANY(%(chain)s)
                      AND (grant_row.date_to IS NULL OR grant_row.date_to > now() AT TIME ZONE 'UTC')
                     JOIN %(table)s AS holder
                       ON holder.id = grant_row.%(resource)s
                      AND (holder.id = node.id OR %(is_container)s)
                    WHERE node.id = ANY(%(ids)s)
                 GROUP BY node.id""",
                roles=list(graph.roles),
                role=SQL.identifier(names.role),
                table=SQL.identifier(self._table),
                grant_table=SQL.identifier(grant_model._table),
                group=group_id,
                resource=SQL.identifier(names.resource),
                chain=path_ids(SQL.identifier("node", "access_scope_path")),
                is_container=self._get_access_container_condition("holder"),
                ids=ids,
            )
        )
        return dict(self.env.cr.fetchall())

    def _access_graph_ranks(self, ids: list[int]) -> dict[int, int]:
        roles = self._access_graph.roles
        self._access_graph_flush()
        nodes = self.with_context(active_test=False)
        cases = SQL(" ").join(
            SQL(
                "WHEN %s AND %s.id IN (%s) THEN %s",
                self._access_graph_condition(role)(self._table),
                SQL.identifier(self._table),
                nodes._search(
                    Domain("id", "in", list(ids)) & self._access_label_reach(role)
                ).select(),
                index + 1,
            )
            for index, role in reversed(list(enumerate(roles)))
        )
        self.env.cr.execute(
            SQL(
                "SELECT id, CASE %s ELSE 0 END FROM %s WHERE id = ANY(%s)",
                cases,
                SQL.identifier(self._table),
                list(ids),
            )
        )
        return {node_id: rank for node_id, rank in self.env.cr.fetchall() if rank}

    def _access_graph_flush(self) -> None:
        graph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        grant_model.flush_model(
            [
                names.resource,
                names.role,
                "partner_id",
                "group_id",
                "company_id",
                "date_to",
            ]
        )
        self.flush_model(
            sorted(
                {
                    "access_scope_path",
                    *self._access_reach_tracked_columns(),
                }
            )
        )

    def _get_access_container_condition(self, alias: str) -> SQL:
        graph = self._access_graph
        if not graph.container:
            return SQL("TRUE")
        field, value = graph.container
        return SQL("%s = %s", SQL.identifier(alias, field), value)

    def _access_graph_condition(
        self,
        role: str,
        *,
        groups: typing.Iterable[int] | None = None,
        exclude_groups: typing.Iterable[int] = (),
        partner: bool = True,
        owner: bool = True,
    ) -> typing.Callable[..., SQL]:
        subquery = self._access_reach_subquery(
            role,
            groups=groups,
            exclude_groups=exclude_groups,
            partner=partner,
            owner=owner,
        )

        def condition(alias: str, query: Query | None = None) -> SQL:
            _debug.logic("access_graph.reach", model=self._name, alias=alias)
            reach = SQL("(%s)", subquery) if query is None else query.once_set(subquery)
            return SQL("%s IN %s", SQL.identifier(alias, "id"), reach)

        return condition

    def _access_graph_sources(self) -> list[dict[str, typing.Any]]:
        self.check_singleton()
        graph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        self._access_graph_flush()
        owner = (
            SQL(
                """UNION ALL
                   SELECT holder.id, NULL, users.partner_id, NULL, NULL, %s
                     FROM target
                     JOIN %s AS holder
                       ON holder.id = ANY(target.chain)
                      AND (holder.id = target.id OR %s)
                     JOIN res_users AS users ON users.id = holder.%s""",
                graph.roles[-1],
                SQL.identifier(self._table),
                self._get_access_container_condition("holder"),
                SQL.identifier(graph.owner),
            )
            if graph.owner
            else SQL()
        )
        self.env.cr.execute(
            SQL(
                """WITH target AS (
                       SELECT id, %(chain)s AS chain FROM %(table)s WHERE id = %(id)s
                   )
                   SELECT grant_row.%(resource)s, grant_row.id, grant_row.partner_id,
                          grant_row.group_id, grant_row.company_id, grant_row.%(role)s
                     FROM target
                     JOIN %(grant_table)s AS grant_row
                       ON grant_row.%(resource)s = ANY(target.chain)
                     JOIN %(table)s AS holder
                       ON holder.id = grant_row.%(resource)s
                      AND (holder.id = target.id OR %(is_container)s)
                    WHERE (grant_row.date_to IS NULL
                           OR grant_row.date_to > now() AT TIME ZONE 'UTC')
                   %(owner)s""",
                chain=path_ids(SQL.identifier("access_scope_path")),
                table=SQL.identifier(self._table),
                id=self.id,
                resource=SQL.identifier(names.resource),
                role=SQL.identifier(names.role),
                grant_table=SQL.identifier(grant_model._table),
                is_container=self._get_access_container_condition("holder"),
                owner=owner,
            )
        )
        return [
            {
                "node": self.browse(node_id),
                "grant": grant_model.browse(grant_id or ()),
                "partner": self.env["res.partner"].browse(partner_id or ()),
                "group": self.env["res.groups"].browse(group_id or ()),
                "company": self.env["res.company"].browse(company_id or ()),
                "role": role,
                "inherited": node_id != self.id,
            }
            for node_id, grant_id, partner_id, group_id, company_id, role in (
                self.env.cr.fetchall()
            )
        ]


class Base(models.AbstractModel):
    _inherit = "base"

    @predicate_arguments(
        "role", optional=("at", "groups", "except_groups", "partner", "owner")
    )
    def _access_predicate_graph_reach(self, bind: typing.Any, args: dict) -> Domain:
        path = (args.get("at") or "").rstrip(".")
        model = self
        for name in filter(None, path.split(".")):
            model = model.env[model._fields[name].comodel_name]
        if getattr(type(model), "_access_graph", None) is None:
            raise ValueError(f"{model._name} has no access graph")
        env = model.env
        groups = args.get("groups")
        domain = model._access_graph_reach(
            args["role"],
            groups=None if groups is None else [env.ref(g).id for g in groups],
            exclude_groups=[env.ref(g).id for g in args.get("except_groups", ())],
            partner=args.get("partner", True),
            owner=args.get("owner", True),
        )
        return Domain(path, "any", domain) if path else domain


@dataclass(frozen=True)
class AccessGrantNames:
    resource: str
    role: str = "role"


GRANT_CAUSES = [
    ("manual", "Shared by a user"),
    ("module", "Set by a module"),
    ("approval_request", "Approved request"),
    ("migration", "Carried over by an upgrade"),
    ("merge", "Kept from a merged contact"),
]


class MixinAccessGrant(models.AbstractModel):
    _name = "mixin.access.grant"
    _description = "Grant of a Role on a Node"
    _merge_clash_policy = "drop"

    _access_grant_names: AccessGrantNames
    _access_grant_by_cause = False

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index=True,
        ondelete="cascade",
    )
    group_id = fields.Many2one(
        comodel_name="res.groups",
        index="btree_not_null",
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index="btree_not_null",
        ondelete="cascade",
        help="A group's grant limited to one company reaches only who holds the "
        "group in it.",
    )
    date_to = fields.Datetime(
        string="Expiration",
        index="btree_not_null",
        help="After this moment the grant grants nothing.",
    )
    cause = fields.Selection(
        selection=GRANT_CAUSES,
        default="manual",
        required=True,
    )
    cause_ref = fields.Char(
        string="Cause Reference",
        index="btree_not_null",
        help="The record that caused the grant, as model,id.",
    )
    granted_by_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        ondelete="set null",
    )

    _one_principal = models.Constraint(
        "CHECK ((partner_id IS NULL) != (group_id IS NULL))",
        "A grant names exactly one principal: a partner or a group.",
    )
    _company_of_a_group = models.Constraint(
        "CHECK (company_id IS NULL OR group_id IS NOT NULL)",
        "Only a group's grant is limited to a company.",
    )

    @api.model
    def _sync_caused_grants(
        self, cause_ref: str, wanted: list[tuple[int, str, int, str, int | bool]]
    ) -> None:
        names = self._access_grant_names
        grants = self.sudo()
        ladder = self._fields[names.role].get_values(self.env)
        roles: dict[tuple, str] = {}
        for node, kind, principal_id, role, company in wanted:
            key = (node, kind, principal_id, company or False)
            if key not in roles or ladder.index(role) > ladder.index(roles[key]):
                roles[key] = role
        stale = grants.browse()
        for grant in grants.search([("cause_ref", "=", cause_ref)]):
            node = grant[names.resource].id
            key = (
                (node, "partner_id", grant.partner_id.id, False)
                if grant.partner_id
                else (node, "group_id", grant.group_id.id, grant.company_id.id or False)
            )
            role = roles.pop(key, None)
            if role is None:
                stale |= grant
            elif grant[names.role] != role or grant.date_to:
                grant.write({names.role: role, "date_to": False})
        stale.unlink()
        if roles:
            grants.create(
                [
                    {
                        names.resource: node,
                        kind: principal_id,
                        "company_id": company,
                        names.role: role,
                        "cause": "module",
                        "cause_ref": cause_ref,
                    }
                    for (node, kind, principal_id, company), role in roles.items()
                ]
            )

    @api.model
    def _merge_partner_claims(
        self, src_partners: models.BaseModel, dst_partner: models.BaseModel
    ) -> None:
        names = self._access_grant_names
        ladder = self._fields[names.role].get_values(self.env)
        table = SQL.identifier(self._table)
        self.flush_model()
        for src in src_partners:
            self.env.cr.execute(
                SQL(
                    """SELECT src.id, dst.id, src.%(role)s, dst.%(role)s,
                              src.date_to, dst.date_to
                         FROM %(table)s AS src
                         JOIN %(table)s AS dst
                           ON dst.%(resource)s = src.%(resource)s
                          AND dst.partner_id = %(dst)s
                          AND %(same_claim)s
                        WHERE src.partner_id = %(src)s""",
                    same_claim=SQL("dst.cause_ref IS NOT DISTINCT FROM src.cause_ref")
                    if self._access_grant_by_cause
                    else SQL("TRUE"),
                    role=SQL.identifier(names.role),
                    resource=SQL.identifier(names.resource),
                    table=table,
                    src=src.id,
                    dst=dst_partner.id,
                )
            )
            dropped, carried = [], []
            for (
                src_id,
                dst_id,
                src_role,
                dst_role,
                src_to,
                dst_to,
            ) in self.env.cr.fetchall():
                src_rank, dst_rank = ladder.index(src_role), ladder.index(dst_role)
                src_lasts = not src_to or bool(dst_to and src_to >= dst_to)
                dst_lasts = not dst_to or bool(src_to and dst_to >= src_to)
                if self._access_grant_by_cause and not (
                    (dst_rank >= src_rank and dst_lasts)
                    or (src_rank >= dst_rank and src_lasts)
                ):
                    carried.append(src_id)
                    continue
                if (src_lasts, src_rank) > (dst_lasts, dst_rank):
                    self.env.cr.execute(
                        SQL(
                            "UPDATE %s SET %s = %s, date_to = %s WHERE id = %s",
                            table,
                            SQL.identifier(names.role),
                            src_role,
                            src_to,
                            dst_id,
                        )
                    )
                dropped.append(src_id)
            if dropped:
                self.env.cr.execute(
                    SQL("DELETE FROM %s WHERE id = ANY(%s)", table, dropped)
                )
            if carried:
                self.env.cr.execute(
                    SQL(
                        "UPDATE %s SET cause = 'merge', cause_ref = %s WHERE id = ANY(%s)",
                        table,
                        f"res.partner,{src.id}",
                        carried,
                    )
                )
            self.env.cr.execute(
                SQL(
                    "UPDATE %s SET partner_id = %s WHERE partner_id = %s",
                    table,
                    dst_partner.id,
                    src.id,
                )
            )
            _debug.lifecycle(
                "claims_merged",
                model=self._name,
                src=src.id,
                dst=dst_partner.id,
                dropped=len(dropped),
                carried=len(carried),
            )
        self.invalidate_model()
