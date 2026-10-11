from typing import Any

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict

OPEN_CHANGESET_STATES = ("draft", "proposed")


class IrAccessMatrix(models.Model):
    _name = "ir.access.matrix"
    _description = "Access Matrix"
    _auto = False
    _order = "model_id, group_id"
    _depends = frozendict(
        {
            "ir.access": [
                "active",
                "domain",
                "group_id",
                "kind",
                "model_id",
                "operation",
                "reach",
                "verbs",
            ],
            "res.groups": ["is_privilege", "privilege_id"],
            "res.groups.privilege": ["category_id"],
        }
    )
    _table_query = """
        WITH access AS (
            SELECT
                id,
                model_id,
                group_id,
                kind,
                COALESCE(operation, '') AS operation,
                verbs,
                CASE
                    WHEN reach IS NOT NULL THEN reach
                    WHEN COALESCE(domain, '') NOT IN ('', '[]') THEN 'filtered'
                    ELSE 'all'
                END AS reach
            FROM ir_access
            WHERE active
        ),
        guards AS (
            SELECT model_id, COUNT(*) AS guard_count
            FROM access
            WHERE kind = 'guard'
            GROUP BY model_id
        ),
        verbs AS (
            SELECT
                access.model_id,
                access.group_id,
                string_agg(DISTINCT trim(verb) || ':' || access.reach, ','
                    ORDER BY trim(verb) || ':' || access.reach) AS verb_keys
            FROM access, unnest(string_to_array(access.verbs, ',')) AS verb
            WHERE access.kind = 'permission' AND trim(verb) != ''
            GROUP BY access.model_id, access.group_id
        ),
        pairs AS (
            SELECT
                MIN(id) AS id,
                model_id,
                group_id,
                COUNT(*) AS permission_count,
                string_agg(DISTINCT reach, ',' ORDER BY reach)
                    FILTER (WHERE strpos(operation, 'r') > 0) AS read_keys,
                string_agg(DISTINCT reach, ',' ORDER BY reach)
                    FILTER (WHERE strpos(operation, 'u') > 0) AS write_keys,
                string_agg(DISTINCT reach, ',' ORDER BY reach)
                    FILTER (WHERE strpos(operation, 'c') > 0) AS create_keys,
                string_agg(DISTINCT reach, ',' ORDER BY reach)
                    FILTER (WHERE strpos(operation, 'd') > 0) AS unlink_keys
            FROM access
            WHERE kind = 'permission'
            GROUP BY model_id, group_id
        )
        SELECT
            pairs.id,
            pairs.model_id,
            pairs.group_id,
            res_groups.privilege_id,
            res_groups_privilege.category_id,
            COALESCE(res_groups.is_privilege, FALSE) AS is_privilege,
            pairs.permission_count,
            (pairs.read_keys IS NOT NULL)::int
                + (pairs.write_keys IS NOT NULL)::int
                + (pairs.create_keys IS NOT NULL)::int
                + (pairs.unlink_keys IS NOT NULL)::int AS operation_count,
            COALESCE(guards.guard_count, 0) AS guard_count,
            pairs.read_keys,
            pairs.write_keys,
            pairs.create_keys,
            pairs.unlink_keys,
            verbs.verb_keys
        FROM pairs
        JOIN res_groups ON res_groups.id = pairs.group_id
        LEFT JOIN res_groups_privilege
            ON res_groups_privilege.id = res_groups.privilege_id
        LEFT JOIN guards ON guards.model_id = pairs.model_id
        LEFT JOIN verbs
            ON verbs.model_id = pairs.model_id AND verbs.group_id = pairs.group_id
    """

    model_id = fields.Many2one(
        comodel_name="ir.model",
        readonly=True,
    )
    group_id = fields.Many2one(
        comodel_name="res.groups",
        readonly=True,
    )
    privilege_id = fields.Many2one(
        comodel_name="res.groups.privilege",
        readonly=True,
    )
    category_id = fields.Many2one(
        comodel_name="ir.module.category",
        string="App",
        readonly=True,
    )
    is_privilege = fields.Boolean(
        string="Named Privilege",
        readonly=True,
        help="The group is a privilege: held by nobody, raised by code for one call.",
    )
    permission_count = fields.Integer(
        string="Permissions",
        readonly=True,
    )
    operation_count = fields.Integer(
        string="Operations",
        readonly=True,
        help="How many of read, update, create and delete the group reaches.",
    )
    guard_count = fields.Integer(
        string="Guards",
        readonly=True,
        help="The model's guards, which bind whatever the group reaches.",
    )
    read_keys = fields.Char(readonly=True)
    write_keys = fields.Char(readonly=True)
    create_keys = fields.Char(readonly=True)
    unlink_keys = fields.Char(readonly=True)
    verb_keys = fields.Char(readonly=True)
    read_reach = fields.Char(
        string="Read",
        compute="_compute_reach",
    )
    write_reach = fields.Char(
        string="Update",
        compute="_compute_reach",
    )
    create_reach = fields.Char(
        string="Create",
        compute="_compute_reach",
    )
    unlink_reach = fields.Char(
        string="Delete",
        compute="_compute_reach",
    )
    verb_reach = fields.Char(
        string="Verbs",
        compute="_compute_reach",
    )
    guard_names = fields.Char(
        string="Guarded By",
        compute="_compute_guard_names",
    )
    changeset_ids = fields.Many2many(
        comodel_name="ir.access.changeset",
        string="Open Change Sets",
        compute="_compute_changeset_ids",
        search="_search_changeset_ids",
    )

    @api.depends("read_keys", "write_keys", "create_keys", "unlink_keys", "verb_keys")
    def _compute_reach(self) -> None:
        labels = {
            **dict(
                self.env["ir.access"]._fields["reach"]._description_selection(self.env)
            ),
            "filtered": self.env._("Filtered"),
        }

        def words(keys: str | bool) -> str | bool:
            return keys and ", ".join(labels.get(key, key) for key in keys.split(","))

        for row in self:
            row.read_reach = words(row.read_keys)
            row.write_reach = words(row.write_keys)
            row.create_reach = words(row.create_keys)
            row.unlink_reach = words(row.unlink_keys)
            row.verb_reach = row.verb_keys and "; ".join(
                f"{verb}: {labels.get(key, key)}"
                for verb, key in (pair.split(":") for pair in row.verb_keys.split(","))
            )

    @api.depends("model_id")
    def _compute_guard_names(self) -> None:
        guards = self.env["ir.access"].search_read(
            [("kind", "=", "guard"), ("model_id", "in", self.model_id.ids)],
            ["model_id", "name"],
            order="model_id, name",
        )
        names: dict[int, list[str]] = {}
        for guard in guards:
            names.setdefault(guard["model_id"][0], []).append(guard["name"])
        for row in self:
            row.guard_names = "; ".join(names.get(row.model_id.id, [])) or False

    @api.depends("model_id", "group_id")
    def _compute_changeset_ids(self) -> None:
        changesets = self.env["ir.access.changeset"].search(
            [("state", "in", OPEN_CHANGESET_STATES)]
        )
        touched = {changeset: changeset._matrix_pairs() for changeset in changesets}
        for row in self:
            row.changeset_ids = [
                changeset.id
                for changeset, (pairs, groups) in touched.items()
                if (row.model_id.id, row.group_id.id) in pairs
                or row.group_id.id in groups
            ]

    def _search_changeset_ids(self, operator: str, value: Any) -> Domain:
        Changeset = self.env["ir.access.changeset"]
        if operator == "in":
            changesets = Changeset.browse([id_ for id_ in value if id_])
        elif operator == "not in" and not any(value):
            changesets = Changeset.search([("state", "in", OPEN_CHANGESET_STATES)])
        else:
            return NotImplemented
        domains = []
        for changeset in changesets:
            pairs, groups = changeset._matrix_pairs()
            domains += [
                Domain("model_id", "=", model_id) & Domain("group_id", "=", group_id)
                for model_id, group_id in pairs
            ]
            if groups:
                domains.append(Domain("group_id", "in", sorted(groups)))
        return Domain.OR(domains) if domains else Domain.FALSE


class IrAccessChangeset(models.Model):
    _inherit = "ir.access.changeset"

    def _matrix_pairs(self) -> tuple[set[tuple[int, int]], set[int]]:
        self.check_singleton()
        Access = self.env["ir.access"]._access_evaluator("ir.access")
        pairs: set[tuple[int, int]] = set()
        groups: set[int] = set()
        predicate_ids = []
        for line in self.line_ids:
            if line.res_model == "ir.access":
                row = Access.browse(line.res_id).exists()
                if row:
                    pairs.add((row.model_id.id, row.group_id.id))
                after = line.values_after or {}
                model_id = after.get("model_id") or row.model_id.id
                group_id = after.get("group_id") or row.group_id.id
                if model_id and group_id:
                    pairs.add((model_id, group_id))
            elif line.res_model == "res.groups":
                groups.add(line.res_id)
            elif line.res_model == "ir.access.predicate":
                predicate_ids.append(line.res_id)
        if predicate_ids:
            pairs |= {
                (row.model_id.id, row.group_id.id)
                for row in Access.search([("predicate_id", "in", predicate_ids)])
            }
        return pairs, groups

    def action_open_matrix(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Access Matrix: %(name)s", name=self.name),
            "res_model": "ir.access.matrix",
            "view_mode": "list,pivot",
            "domain": [("changeset_ids", "in", self.ids)],
            "context": {"group_by": ["model_id"]},
        }
