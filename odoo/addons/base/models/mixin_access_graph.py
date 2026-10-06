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
    # parent: the many2one onto the same model (the model has _parent_store)
    # grants: the one2many onto the adopter's mixin.access.grant model
    # roles: the ladder, lowest first; a role implies every lower one
    # owner: a many2one onto res.users holding the top role on its node and
    #   below it
    # boundary: a boolean; inherited grants stop at a node that sets it
    # container: (field, value) a node must match to hold children; grants on
    #   other nodes reach that node only
    parent: str
    grants: str
    roles: tuple[str, ...]
    owner: str | None = None
    boundary: str | None = None
    container: tuple[str, typing.Any] | None = None


SCOPE_CHAIN = "string_to_array(rtrim({}, '/'), '/')::int4[]"


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

    _access_scope_chain_idx = models.Index(
        "USING gin ((" + SCOPE_CHAIN.format("access_scope_path") + "))"
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
        # a label lets its class's writers edit and its readers see: a class
        # someone may write without reading hides what it lets them edit
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
        # a label changes who reaches a record: whoever holds the top role on
        # it sets it, as they set its grants
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
        # the records whose label lets the current user hold the role: the
        # lowest role reads the label's class, the others write it
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
        # a role band is the records reached at that role and not at the next
        # one up; False is the band reached at none. Adjacent bands asked
        # together are one run, the records reached at its lowest role and not
        # above its highest: "view or above" is one reach, not one per role
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
        # the records the current user holds the role or a higher one on, as
        # far as their labels let them: the lowest role reads a label's class,
        # the others write it. No label lets writing without reading, so a
        # record reached higher up is never reached past its label's readers
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
        # the records the current user reaches at the role or above; groups
        # given explicitly are counted whether or not the user holds them, for
        # an adopter that composes an audience term of its own
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
            # the condition reads the tree and the grants in SQL: what the
            # transaction wrote must be there first
            model._access_graph_flush()
            return sql(alias, query)

        return Domain.custom(to_sql=to_sql)

    def _access_graph_group_ranks(self, group_id: int) -> dict[int, int]:
        # {id: 1-based rank of the highest live grant the group holds on the
        # record or above it, within its scope}
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
                    WHERE node.id = ANY(%(ids)s)
                 GROUP BY node.id""",
                roles=list(graph.roles),
                role=SQL.identifier(names.role),
                table=SQL.identifier(self._table),
                grant_table=SQL.identifier(grant_model._table),
                group=group_id,
                resource=SQL.identifier(names.resource),
                chain=SQL(
                    SCOPE_CHAIN.format("%s"),
                    SQL.identifier("node", "access_scope_path"),
                ),
                ids=ids,
            )
        )
        return dict(self.env.cr.fetchall())

    def _access_graph_ranks(self, ids: list[int]) -> dict[int, int]:
        # {id: 1-based rank of the highest role the current user holds, as far
        # as the record's label lets them}
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
            [
                "access_scope_path",
                graph.parent,
                *(name for name in (graph.owner, graph.boundary) if name),
                *((graph.container[0],) if graph.container else ()),
            ]
        )

    def _access_graph_condition(
        self,
        role: str,
        *,
        groups: typing.Iterable[int] | None = None,
        exclude_groups: typing.Iterable[int] = (),
        partner: bool = True,
        owner: bool = True,
    ) -> typing.Callable[..., SQL]:
        # an SQL condition on a row of the model, as three branches: a grant
        # on the node itself, the node's scope chain overlapping granted
        # containers (GIN), or its owner.
        # A grant on the node itself is a semi-join on the grant table, by
        # principal: PostgreSQL hashes the principal's grants once and probes
        # it per row, in parallel workers too. Not an array of granted node
        # ids: a partner's grants run to thousands, and = ANY() over an array
        # computed at run time compares every row with each of them.
        # Containers are few; given the query the condition goes into, each
        # set of granted containers is computed once there, as a rule that
        # walks to the graph through several aliases asks for it at each
        graph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        held = graph.roles[graph.roles.index(role) :]
        user = self.env.user
        excluded = set(exclude_groups)
        if groups is None:
            scopes = {
                gid: companies
                for gid, companies in user._get_group_scopes().items()
                if gid not in excluded
            }
        else:
            scopes = dict.fromkeys(set(groups) - excluded)
        anchor = self._access_company_anchor()
        # a group counts in the companies in use it is held in (those its
        # membership is limited to, else all), as an access row does: it
        # reaches a node of those companies or of none, and its grant limited
        # to a company counts while that company is one of them
        in_use = set(self.env.companies.ids)
        # a partner's grant and an owner reach a node of a company in use, of
        # none, or of one the user is not in (shared from outside): not one of
        # the user's companies they deselected
        member_of = user.with_context(active_test=False).company_ids.ids
        by_companies: dict[tuple[int, ...], list[int]] = {}
        for gid, companies in sorted(scopes.items()):
            counted = in_use if companies is None else in_use & set(companies)
            if counted:
                by_companies.setdefault(tuple(sorted(counted)), []).append(gid)
        with_owner = bool(graph.owner) and owner
        _debug.pipeline(
            "access_graph.condition",
            model=self._name,
            role=role,
            bands=len(by_companies),
            anchored=bool(anchor),
            owner=with_owner,
            partner=partner,
        )
        table = SQL.identifier(self._table)
        grant_table = SQL.identifier(grant_model._table)
        resource = SQL.identifier(names.resource)
        role_column = SQL.identifier(names.role)

        def is_container(alias: str) -> SQL:
            if not graph.container:
                return SQL("TRUE")
            cfield, cvalue = graph.container
            return SQL("%s = %s", SQL.identifier(alias, cfield), cvalue)

        container = is_container("node")

        def held_grants(principal: SQL) -> SQL:
            return SQL(
                """SELECT grant_row.%(resource)s
                     FROM %(grant_table)s AS grant_row
                    WHERE %(principal)s
                      AND grant_row.%(role)s = ANY(%(held)s)
                      AND (grant_row.date_to IS NULL OR grant_row.date_to > now() AT TIME ZONE 'UTC')""",
                resource=resource,
                grant_table=grant_table,
                principal=principal,
                role=role_column,
                held=list(held),
            )

        def granted_containers(principal: SQL) -> SQL:
            return SQL(
                "SELECT node.id FROM (%s) AS held JOIN %s AS node ON node.id = held.%s"
                " WHERE %s",
                held_grants(principal),
                table,
                resource,
                container,
            )

        def owned_containers() -> SQL:
            return SQL(
                "SELECT node.id FROM %s AS node WHERE node.%s = %s AND %s",
                table,
                SQL.identifier(graph.owner),
                user.id,
                container,
            )

        def reached(
            alias: str, principal: SQL, with_owner: bool, query: Query | None
        ) -> SQL:
            chain = SQL(
                SCOPE_CHAIN.format("%s"), SQL.identifier(alias, "access_scope_path")
            )
            containers = granted_containers(principal)
            if with_owner:
                containers = SQL("%s UNION ALL %s", containers, owned_containers())
            containers = SQL("ARRAY(%s)", containers)
            if query is not None:
                containers = query.once(containers)
            # a grant on a container reaches it through its own scope chain
            return SQL(
                "((NOT (%s) AND %s IN (%s)) OR %s && %s::int4[])",
                is_container(alias),
                SQL.identifier(alias, "id"),
                held_grants(principal),
                chain,
                containers,
            )

        partner_id = user.partner_id.id if partner else None

        def held_by(gids: list[int], companies: tuple[int, ...]) -> SQL:
            return SQL(
                """(grant_row.group_id = ANY(%s)
                    AND (grant_row.company_id IS NULL
                         OR grant_row.company_id = ANY(%s)))""",
                gids,
                list(companies),
            )

        def condition(alias: str, query: Query | None = None) -> SQL:
            # a node carries no company to check without an anchor: every
            # group is read in the one reach, beside the partner's grants
            _debug.logic(
                "access_graph.reach",
                model=self._name,
                alias=alias,
                shared=query is not None,
            )
            principal = SQL("grant_row.partner_id = %s", partner_id)
            if not anchor:
                principal = SQL(" OR ").join(
                    [
                        principal,
                        *(held_by(gids, key) for key, gids in by_companies.items()),
                    ]
                )
            personal = [reached(alias, SQL("(%s)", principal), with_owner, query)]
            if with_owner:
                personal.append(
                    SQL("%s = %s", SQL.identifier(alias, graph.owner), user.id)
                )
            branches = personal
            if anchor:
                node_company = SQL.identifier(alias, anchor)
                branches = [
                    SQL(
                        "((%s) AND (%s IS NULL OR %s = ANY(%s) OR NOT %s = ANY(%s)))",
                        SQL(" OR ").join(personal),
                        node_company,
                        node_company,
                        sorted(in_use),
                        node_company,
                        member_of,
                    )
                ]
            for companies, gids in by_companies.items() if anchor else ():
                branches.append(
                    SQL(
                        "(%s AND (%s = ANY(%s) OR %s IS NULL))",
                        reached(alias, held_by(gids, companies), False, query),
                        SQL.identifier(alias, anchor),
                        list(companies),
                        SQL.identifier(alias, anchor),
                    )
                )
            return SQL("(%s)", SQL(" OR ").join(branches))

        return condition

    def _access_graph_sources(self) -> list[dict[str, typing.Any]]:
        # every live grant and owner that reaches the record, with the node it
        # comes from: what a share dialog lists as inherited, and what explain
        # reads. The policy reads its own data here, as ir.access reads its
        # rows: in SQL, so whether the caller may read a folder above does not
        # change what reaches the record; records come back as ids in the
        # caller's environment
        self.check_singleton()
        graph = self._access_graph
        grant_model = self.env[self._fields[graph.grants].comodel_name]
        names = type(grant_model)._access_grant_names
        self._access_graph_flush()
        owner = (
            SQL(
                """UNION ALL
                   SELECT node.id, NULL, users.partner_id, NULL, NULL, %s
                     FROM target
                     JOIN %s AS node ON node.id = ANY(target.chain)
                     JOIN res_users AS users ON users.id = node.%s""",
                graph.roles[-1],
                SQL.identifier(self._table),
                SQL.identifier(graph.owner),
            )
            if graph.owner
            else SQL()
        )
        self.env.cr.execute(
            SQL(
                """WITH target AS (
                       SELECT %(chain)s AS chain FROM %(table)s WHERE id = %(id)s
                   )
                   SELECT grant_row.%(resource)s, grant_row.id, grant_row.partner_id,
                          grant_row.group_id, grant_row.company_id, grant_row.%(role)s
                     FROM target
                     JOIN %(grant_table)s AS grant_row
                       ON grant_row.%(resource)s = ANY(target.chain)
                    WHERE (grant_row.date_to IS NULL
                           OR grant_row.date_to > now() AT TIME ZONE 'UTC')
                   %(owner)s""",
                chain=SQL(SCOPE_CHAIN.format("access_scope_path")),
                table=SQL.identifier(self._table),
                id=self.id,
                resource=SQL.identifier(names.resource),
                role=SQL.identifier(names.role),
                grant_table=SQL.identifier(grant_model._table),
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
        # base.graph_reach: the records whose access graph (the model's own, or
        # the one at the end of args["at"]) the principal holds args["role"]
        # or a higher role on. args["groups"] counts those groups' grants
        # whoever holds them, as an audience; args["except_groups"] leaves
        # theirs out; partner and owner (true by default) count the
        # principal's own grants and ownership
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


class MixinAccessGrant(models.AbstractModel):
    _name = "mixin.access.grant"
    _description = "Grant of a Role on a Node"

    _access_grant_names: AccessGrantNames

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
        selection=[
            ("manual", "Shared by a user"),
            ("module", "Set by a module"),
            ("approval_request", "Approved request"),
            ("migration", "Carried over by an upgrade"),
        ],
        default="manual",
        required=True,
    )
    cause_ref = fields.Char(
        string="Cause Reference",
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
        # the grants one cause holds become exactly `wanted`, each (node id,
        # "partner_id" or "group_id", principal id, role, company id or False);
        # what the cause no longer asks for is revoked, and a grant another
        # cause made on the same node is left alone unless it grants less. The
        # rows are read in SQL and written as the system: a module's grant is
        # the module's decision, taken when its own configuration is written,
        # and whoever writes that configuration need not manage the node
        names = self._access_grant_names
        grants = self.sudo()
        ladder = self._fields[names.role].get_values(self.env)
        self.flush_model(
            [names.resource, names.role, "partner_id", "group_id", "company_id"]
        )
        self.env.cr.execute(
            SQL(
                """SELECT id, %(resource)s, partner_id, group_id, company_id,
                          %(role)s, cause_ref
                     FROM %(table)s
                    WHERE cause_ref = %(cause_ref)s OR %(resource)s = ANY(%(nodes)s)""",
                resource=SQL.identifier(names.resource),
                role=SQL.identifier(names.role),
                table=SQL.identifier(self._table),
                cause_ref=cause_ref,
                nodes=sorted({node for node, *_ in wanted}),
            )
        )
        rows = {}
        for (
            grant_id,
            node,
            partner_id,
            group_id,
            company_id,
            role,
            ref,
        ) in self.env.cr.fetchall():
            key = (
                (node, "partner_id", partner_id, False)
                if partner_id
                else (node, "group_id", group_id, company_id or False)
            )
            rows[key] = (grant_id, role, ref)
        wanted_roles = {
            (node, kind, pid, company or False): role
            for node, kind, pid, role, company in wanted
        }
        stale = [
            grant_id
            for key, (grant_id, _role, ref) in rows.items()
            if ref == cause_ref and key not in wanted_roles
        ]
        if stale:
            grants.browse(stale).unlink()
        creates = []
        for key, role in wanted_roles.items():
            node, kind, principal_id, company = key
            if key not in rows:
                creates.append(
                    {
                        names.resource: node,
                        kind: principal_id,
                        "company_id": company,
                        names.role: role,
                        "cause": "module",
                        "cause_ref": cause_ref,
                    }
                )
                continue
            grant_id, current, ref = rows[key]
            if ref == cause_ref and current != role:
                grants.browse(grant_id).write({names.role: role})
            elif ref != cause_ref and ladder.index(current) < ladder.index(role):
                grants.browse(grant_id).write(
                    {names.role: role, "cause": "module", "cause_ref": cause_ref}
                )
        if creates:
            grants.create(creates)
