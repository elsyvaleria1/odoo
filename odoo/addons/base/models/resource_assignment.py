from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import SQL

from .resource_utils import CUSTODY_SYNC, EXCLUSIVE_CUSTODY_ROLES, HOLDING_CUSTODY_ROLES


class ResourceAssignment(models.Model):
    _name = "resource.assignment"
    _description = "Resource Assignment"
    _inherit = ["mixin.resource.scheduling"]
    _order = "date_start desc, id desc"
    _check_company_auto = True
    _rec_names_search = ["resource_id.name", "assignee_id.name"]

    name = fields.Char(compute="_compute_name")
    active = fields.Boolean(default=True)
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        required=True,
        ondelete="restrict",
        check_company=True,
        help="What is held: a vehicle, a machine, a room, a device.",
    )
    assignee_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        domain="[('type', '=', 'human')]",
        ondelete="restrict",
        check_company=True,
        help="Who holds it.",
    )
    assignee_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Holder",
        compute="_compute_assignee_partner_id",
        store=True,
        readonly=False,
        domain="[('is_company', '=', False)]",
        help="The person who holds it. Anyone can: picking a person gives them a human resource in the company of what they hold.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="resource_id.company_id",
    )
    custody_role = fields.Selection(
        selection=[
            ("custodian", "Custodian"),
            ("operator", "Operator"),
            ("manager", "Manager"),
            ("technician", "Technician"),
        ],
        default="custodian",
        required=True,
    )
    date_start = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        required=True,
    )
    date_end = fields.Datetime(index=True)
    state = fields.Selection(
        selection=[("planned", "Planned"), ("active", "Active"), ("ended", "Ended")],
        compute="_compute_state",
        search="_search_state",
    )
    note = fields.Text()

    _resource_period_idx = models.Index("(resource_id, date_start, date_end)")
    _check_dates = models.Constraint(
        "CHECK(date_end IS NULL OR date_end >= date_start)",
        "An assignment cannot end before it starts.",
    )

    @api.constrains("resource_id", "assignee_id")
    def _check_parties(self):
        for record in self:
            if not record._has_holder():
                raise ValidationError(
                    self.env._(
                        "%(resource)s is assigned to nobody: name who holds it.",
                        resource=record.resource_id.name,
                    )
                )
            if not record.assignee_id:
                continue
            if record.resource_id == record.assignee_id:
                raise ValidationError(
                    self.env._("A resource cannot be assigned to itself.")
                )
            if record.assignee_id.type != "human":
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a human resource and cannot hold an assignment.",
                        name=record.assignee_id.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        self._update_assignee_vals(vals_list)
        assignments = super().create(vals_list)
        if not self.env.context.get(CUSTODY_SYNC):
            assignments._supersede_rivals()
        return assignments

    def write(self, vals):
        result = self._write_assignee(vals)
        if not self.env.context.get(
            CUSTODY_SYNC
        ) and self._get_fields_custody().intersection(vals):
            self._supersede_rivals()
        return result

    @api.model
    def _get_fields_custody(self) -> frozenset[str]:
        return frozenset(
            {"custody_role", "resource_id", "date_start", "date_end", "active"}
        )

    def _write_assignee(self, vals):
        if "assignee_partner_id" not in vals:
            return super().write(vals)
        vals = dict(vals)
        party = self.env["res.partner"].browse(vals.pop("assignee_partner_id"))
        if not party:
            return super().write({**vals, "assignee_id": False})
        resource = self.env["resource.resource"].browse(vals.get("resource_id"))
        by_company = self.grouped(
            lambda record: (resource or record.resource_id).company_id
        )
        for company, records in by_company.items():
            holder = party.sudo()._get_or_create_resources(company)
            super(ResourceAssignment, records).write({**vals, "assignee_id": holder.id})
        return True

    @api.depends("assignee_id.partner_id")
    def _compute_assignee_partner_id(self):
        for record in self:
            record.assignee_partner_id = record.assignee_id.partner_id

    @api.depends("resource_id.name", "assignee_id.name", "custody_role")
    @api.depends_context("lang")
    def _compute_name(self):
        roles = dict(self._fields["custody_role"]._description_selection(self.env))
        for record in self:
            record.name = self.env._(
                "%(assignee)s, %(role)s of %(resource)s",
                assignee=record._get_holder_name() or "?",
                role=roles.get(record.custody_role, record.custody_role),
                resource=record.resource_id.name or "?",
            )

    @api.depends("date_start", "date_end", "active")
    def _compute_state(self):
        now = fields.Datetime.now()
        for record in self:
            if record.date_end and (
                record.date_end <= now or record.date_end <= record.date_start
            ):
                record.state = "ended"
            elif record.date_start and record.date_start > now:
                record.state = "planned"
            else:
                record.state = "active"

    def _end(self, at=None):
        # A planned assignment is cancelled by giving it no length: it ends
        # where it starts.
        at = at or fields.Datetime.now()
        records = self.with_context(**{CUSTODY_SYNC: True})
        started = records.filtered(lambda a: a.date_start <= at)
        started.write({"date_end": at})
        for planned in records - started:
            planned.date_end = planned.date_start

    @api.model
    def _get_domain_cancelled(self) -> Domain:
        return Domain.custom(
            to_sql=lambda model, alias, query: SQL(
                "COALESCE(%s <= %s, FALSE)",
                model._field_to_sql(alias, "date_end", query),
                model._field_to_sql(alias, "date_start", query),
            )
        )

    @api.model
    def _get_exclusive_custody_roles(self) -> tuple[str, ...]:
        return EXCLUSIVE_CUSTODY_ROLES

    @api.model
    def _get_holding_custody_roles(self) -> tuple[str, ...]:
        # Who has the resource, in order: whoever operates it, else whoever
        # keeps it. Managing or repairing it is not having it.
        return HOLDING_CUSTODY_ROLES

    @api.model
    def _get_domain_custody(self, at=None, when="live"):
        at = at or fields.Datetime.now()
        not_ended = Domain("date_end", "=", False) | Domain("date_end", ">", at)
        if when == "live":
            return Domain("date_start", "<=", at) & not_ended
        if when == "planned":
            return Domain("date_start", ">", at) & ~self._get_domain_cancelled()
        if when == "open":
            return not_ended & ~self._get_domain_cancelled()
        raise ValueError(when)

    @api.model
    def _get_sql_custody_winners(self, roles, when="live", at=None) -> SQL:
        """The assignment that answers each resource's custody among `roles`,
        as (resource_id, assignee_id, date_start): live, the first of `roles`
        held, then the latest started; planned, the earliest to start. The
        computes and the searches of the custody fields both read this, so
        what a resource shows is what finds it."""
        at = at or fields.Datetime.now()
        if when == "live":
            period = SQL(
                "date_start <= %s AND (date_end IS NULL OR date_end > %s)", at, at
            )
            order = SQL(
                "array_position(%s::varchar[], custody_role::varchar),"
                " date_start DESC, id DESC",
                list(roles),
            )
        elif when == "planned":
            period = SQL(
                "date_start > %s AND NOT COALESCE(date_end <= date_start, FALSE)", at
            )
            order = SQL("date_start, id")
        else:
            raise ValueError(when)
        return SQL(
            """
            SELECT DISTINCT ON (resource_id) resource_id, assignee_id, date_start
              FROM resource_assignment
             WHERE active AND custody_role = ANY(%s) AND %s
             ORDER BY resource_id, %s
            """,
            list(roles),
            period,
            order,
        )

    @api.model
    def _get_custody_winners(self, resources, roles, when="live", at=None) -> dict:
        if not resources:
            return {}
        self.flush_model(
            [
                "resource_id",
                "assignee_id",
                "custody_role",
                "date_start",
                "date_end",
                "active",
            ]
        )
        rows = self.env.execute_query(
            SQL(
                "SELECT resource_id, assignee_id, date_start FROM (%s) winners"
                " WHERE resource_id = ANY(%s)",
                self._get_sql_custody_winners(roles, when, at),
                resources._origin.ids,
            )
        )
        return {
            resource_id: (assignee_id, start)
            for resource_id, assignee_id, start in rows
        }

    def _get_holder_name(self):
        self.check_singleton()
        return self.assignee_id.name

    def _get_fields_reservation_date(self):
        return ("date_start", "date_end")

    def _get_fields_sync_trigger(self):
        return super()._get_fields_sync_trigger() | {
            "resource_id",
            "assignee_id",
            "custody_role",
        }

    @api.model
    def _get_sql_effective_custody(self, ids=None):
        """Resolve overlapping roles using the same latest-started winner as custody."""
        return SQL(
            """
            SELECT ra.id, ra.resource_id, ra.assignee_id, ra.custody_role,
                   TRUE AS active, lower(piece) AS date_start, upper(piece) AS date_end
              FROM resource_assignment ra
              CROSS JOIN LATERAL unnest(
                  tsrange(ra.date_start, ra.date_end, '[)')::tsmultirange
                  - COALESCE((
                      SELECT range_agg(tsrange(rival.date_start, rival.date_end, '[)'))
                        FROM resource_assignment rival
                       WHERE rival.resource_id = ra.resource_id
                         AND rival.custody_role = ra.custody_role AND rival.active
                         AND (rival.date_start, rival.id) > (ra.date_start, ra.id)
                         AND tsrange(rival.date_start, rival.date_end, '[)')
                             && tsrange(ra.date_start, ra.date_end, '[)')
                    ), '{}'::tsmultirange)
              ) piece
             WHERE ra.active %(scope)s
        """,
            scope=SQL("AND ra.id = ANY(%s)", list(ids)) if ids is not None else SQL(),
        )

    @api.model
    def _get_holder(self, resource, custody_role=None, at=None):
        roles = (custody_role,) if custody_role else self._get_holding_custody_roles()
        winner = self._get_custody_winners(resource, roles, at=at).get(resource.id)
        return self.env["resource.resource"].browse(winner[0] if winner else ())

    @api.model
    def _get_custody_assignments(
        self, resources, roles=None, at=None, when="live", archived=False
    ):
        if not resources:
            return self.browse()
        domain = Domain("resource_id", "in", resources.ids) & self._get_domain_custody(
            at, when
        )
        if roles:
            domain &= Domain("custody_role", "in", list(roles))
        assignments = self.sudo()
        if archived:
            assignments = assignments.with_context(active_test=False)
        return assignments.search(domain)

    def _prepare_reservation_vals_list(self):
        self.check_singleton()
        if not self.date_start or not self.date_end or not self.resource_id:
            return []
        return [
            {
                "name": self.name,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "resource_id": self.resource_id.id,
                "allocated_percentage": 100.0 / (self.resource_id.capacity or 1),
                "enforcement_mode": "soft",
            }
        ]

    def _supersede_rivals(self, at=None):
        at = at or fields.Datetime.now()
        exclusive = self._get_exclusive_custody_roles()
        started = self.filtered(
            lambda assignment: (
                assignment.active
                and assignment.custody_role in exclusive
                and assignment.date_start <= at
                and (not assignment.date_end or assignment.date_end > at)
            )
        )
        if not started:
            return
        # one batch may hold rivals too: the latest started of each holds
        winners = {}
        for assignment in started.sorted(lambda a: (a.date_start, a.id)):
            winners[assignment.resource_id.id, assignment.custody_role] = assignment
        outrun = started - self.browse().union(*winners.values())
        rivals = (
            self._get_custody_assignments(started.resource_id, roles=exclusive, at=at)
            - self
        ).filtered(lambda rival: (rival.resource_id.id, rival.custody_role) in winners)
        (rivals | outrun)._end(at)

    def _search_state(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            return NotImplemented
        values = {value} if isinstance(value, str) else set(value or ())
        now = fields.Datetime.now()
        ended = (
            Domain("date_end", "!=", False) & Domain("date_end", "<=", now)
        ) | self._get_domain_cancelled()
        by_state = {
            "planned": Domain("date_start", ">", now) & ~ended,
            "ended": ended,
        }
        by_state["active"] = ~(by_state["planned"] | by_state["ended"])
        domain = (
            Domain.OR(by_state[v] for v in values if v in by_state)
            if values
            else Domain.FALSE
        )
        if operator in ("!=", "not in"):
            domain = ~domain
        return domain

    def _update_assignee_vals(self, vals_list):
        default_resource_id = self.env.context.get("default_resource_id")
        pending = defaultdict(list)
        for vals in vals_list:
            party_id = vals.pop("assignee_partner_id", None)
            if not party_id or vals.get("assignee_id"):
                continue
            resource = self.env["resource.resource"].browse(
                vals.get("resource_id") or default_resource_id
            )
            pending[resource.company_id].append((vals, party_id))
        for company, entries in pending.items():
            parties = self.env["res.partner"].browse(
                [party_id for _vals, party_id in entries]
            )
            holders = parties.sudo()._get_or_create_resources(company)
            for (vals, _party_id), holder in zip(entries, holders, strict=True):
                vals["assignee_id"] = holder.id

    def _has_holder(self) -> bool:
        self.check_singleton()
        return bool(self.assignee_id)
