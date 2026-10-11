from datetime import UTC

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL


class ResourceRelation(models.Model):
    _name = "resource.relation"
    _description = "Resource Relation"
    _order = "parent_id, relation_type, date_start, id"
    _check_company_auto = True
    _rec_names_search = ["parent_id.name", "member_id.name"]

    name = fields.Char(compute="_compute_name")
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Resource",
        index=True,
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    member_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    relation_type = fields.Selection(
        selection=[("contains", "Contains"), ("depends_on", "Depends On")],
        default="contains",
        required=True,
        help="Containment records physical membership. Dependency records an operational requirement. Neither reserves capacity automatically.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        precompute=True,
        store=True,
        index="btree_not_null",
    )
    date_start = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        help="Inclusive UTC start. Empty means the start is unknown or unbounded.",
    )
    date_end = fields.Datetime(
        index=True,
        help="Exclusive UTC end. Empty means the relation remains open.",
    )
    note = fields.Text()

    _different_members = models.Constraint(
        "CHECK(parent_id != member_id)",
        "A resource cannot contain or depend on itself.",
    )
    _positive_period = models.Constraint(
        "CHECK(date_end IS NULL OR date_start IS NULL OR date_start < date_end)",
        "A resource relation must end after it starts.",
    )
    _member_period_idx = models.Index(
        "(member_id, relation_type, date_start, date_end)"
    )

    _parent_period_idx = models.Index(
        "(parent_id, relation_type, date_start, date_end)"
    )

    @api.depends("parent_id.name", "member_id.name", "relation_type")
    @api.depends_context("lang")
    def _compute_name(self):
        labels = dict(self._fields["relation_type"]._description_selection(self.env))
        for relation in self:
            relation.name = self.env._(
                "%(parent)s: %(relation)s %(member)s",
                parent=relation.parent_id.name or "?",
                relation=labels.get(relation.relation_type, "?"),
                member=relation.member_id.name or "?",
            )

    @api.depends("parent_id.company_id", "member_id.company_id")
    def _compute_company_id(self):
        for relation in self:
            relation.company_id = (
                relation.parent_id.company_id or relation.member_id.company_id
            )

    @api.model
    def _get_domain_live_relations(self, at=None, relation_type="contains"):
        at = fields.Datetime.to_datetime(at or fields.Datetime.now())
        if at.tzinfo is not None:
            at = at.astimezone(UTC).replace(tzinfo=None)
        return [
            ("active", "=", True),
            ("relation_type", "=", relation_type),
            "|",
            ("date_start", "=", False),
            ("date_start", "<=", at),
            "|",
            ("date_end", "=", False),
            ("date_end", ">", at),
        ]

    @api.model
    def _set_containment_parent(self, member, parent, at=None):
        member.check_singleton()
        if parent:
            parent.check_singleton()
        if parent == member:
            raise ValidationError(self.env._("A resource cannot contain itself."))
        at = fields.Datetime.to_datetime(at or fields.Datetime.now())
        if at.tzinfo is not None:
            at = at.astimezone(UTC).replace(tzinfo=None)
        (member | parent).check_access("write")
        self.check_access("write")
        self._lock_graph((member | parent).ids)
        current = self.search(
            self._get_domain_live_relations(at) + [("member_id", "=", member.id)]
        )
        if current.parent_id == parent:
            return
        current.parent_id.check_access("write")
        instant = current.filtered(lambda relation: relation.date_start == at)
        instant.unlink()
        (current - instant).write({"date_end": at})
        if parent:
            planned = self.search(
                [
                    ("member_id", "=", member.id),
                    ("active", "=", True),
                    ("relation_type", "=", "contains"),
                    ("date_start", ">", at),
                ],
                order="date_start, id",
                limit=1,
            )
            self.create(
                {
                    "parent_id": parent.id,
                    "member_id": member.id,
                    "relation_type": "contains",
                    "date_start": at,
                    "date_end": planned.date_start if planned else False,
                }
            )

    @api.model
    def _lock_graph(self, resource_ids):
        if not resource_ids:
            return
        self.flush_model(["parent_id", "member_id"])
        self.env.cr.execute(
            SQL(
                """WITH RECURSIVE connected(id) AS (
                SELECT unnest(%s::int[])
                UNION
                SELECT CASE WHEN edge.parent_id = connected.id
                            THEN edge.member_id ELSE edge.parent_id END
                  FROM connected
                  JOIN resource_relation edge
                    ON edge.parent_id = connected.id OR edge.member_id = connected.id
            ) SELECT id FROM connected ORDER BY id""",
                sorted(set(resource_ids)),
            )
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        self.env["resource.resource"].browse(ids)._lock_for_integrity()

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        defaults = self.default_get(["parent_id", "member_id"])
        ids = [
            vals.get(key, defaults.get(key))
            for vals in vals_list
            for key in ("parent_id", "member_id")
        ]
        resources = self.env["resource.resource"].browse([id_ for id_ in ids if id_])
        resources.check_access("write")
        self._lock_graph(resources.ids)
        return super().create(vals_list)

    def write(self, vals):
        self.check_access("write")
        if vals.keys() & {
            "parent_id",
            "member_id",
            "relation_type",
            "date_start",
            "date_end",
            "active",
        }:
            resources = self.parent_id | self.member_id
            resources |= self.env["resource.resource"].browse(
                [vals[key] for key in ("parent_id", "member_id") if vals.get(key)]
            )
            resources.check_access("write")
            self._lock_graph(resources.ids)
        return super().write(vals)

    def unlink(self):
        self.check_access("unlink")
        resources = self.parent_id | self.member_id
        resources.check_access("write")
        self._lock_graph(resources.ids)
        return super().unlink()

    @api.constrains(
        "parent_id", "member_id", "relation_type", "date_start", "date_end", "active"
    )
    def _check_graph(self):
        self.flush_model()
        self.env.cr.execute(
            SQL(
                """SELECT source.relation_type FROM resource_relation source
                  JOIN resource_relation rival ON rival.id != source.id
                   AND rival.active AND rival.relation_type = source.relation_type
                   AND rival.member_id = source.member_id
                   AND (source.relation_type = 'contains' OR rival.parent_id = source.parent_id)
                   AND tsrange(rival.date_start, rival.date_end, '[)')
                       && tsrange(source.date_start, source.date_end, '[)')
                 WHERE source.id = ANY(%s) AND source.active LIMIT 1""",
                self.ids,
            )
        )
        if self.env.cr.fetchone():
            raise ValidationError(
                self.env._(
                    "A member can have only one physical parent at a time, and duplicate overlapping dependencies are not allowed."
                )
            )
        self.env.cr.execute(
            SQL(
                """WITH RECURSIVE paths(origin, member_id, relation_type, period) AS (
                SELECT parent_id, member_id, relation_type,
                       tsrange(date_start, date_end, '[)')
                  FROM resource_relation WHERE id = ANY(%s) AND active
                UNION
                SELECT paths.origin, edge.member_id, paths.relation_type,
                       paths.period * tsrange(edge.date_start, edge.date_end, '[)')
                  FROM paths JOIN resource_relation edge
                    ON edge.parent_id = paths.member_id
                   AND edge.relation_type = paths.relation_type AND edge.active
                   AND paths.period && tsrange(edge.date_start, edge.date_end, '[)')
                 WHERE paths.origin != paths.member_id
            ) SELECT 1 FROM paths WHERE origin = member_id LIMIT 1""",
                self.ids,
            )
        )
        if self.env.cr.fetchone():
            raise ValidationError(
                self.env._(
                    "Resource relations cannot form a cycle during an overlapping period."
                )
            )
