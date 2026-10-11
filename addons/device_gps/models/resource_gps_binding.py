from bisect import bisect_right

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.tools import SQL

from ..tools.periods import GpsCustodyPeriod


class ResourceGpsBinding(models.Model):
    _name = "resource.gps.binding"
    _description = "Resource GPS Attachment Period"
    _order = "date_start desc, id desc"
    _rec_name = "device_id"
    _check_company_auto = True

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        readonly=True,
        ondelete="restrict",
        check_company=True,
    )
    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        readonly=True,
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        readonly=True,
        required=True,
    )
    date_start = fields.Datetime(
        index=True,
        readonly=True,
        help="Unknown for associations that predate attachment history.",
    )
    date_end = fields.Datetime(
        index=True,
        readonly=True,
    )
    origin = fields.Selection(
        selection=[
            ("transition", "Recorded Attachment"),
            ("legacy", "Legacy Assumption"),
        ],
        readonly=True,
        required=True,
    )

    _device_open = models.UniqueIndex(
        "(device_id) WHERE date_end IS NULL",
        "A device has only one open attachment period.",
    )
    _resource_open = models.UniqueIndex(
        "(resource_id) WHERE date_end IS NULL",
        "A resource has only one open GPS attachment period.",
    )
    _dates = models.Constraint(
        "CHECK(date_end IS NULL OR date_start IS NULL OR date_end >= date_start)",
        "An attachment cannot end before it starts.",
    )
    _start = models.Constraint(
        "CHECK(date_start IS NOT NULL OR origin = 'legacy')",
        "A recorded attachment requires its start time.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if vals_list:
            raise AccessError(
                self.env._(
                    "Attachment history is maintained through the resource's GPS device."
                )
            )
        return self.browse()

    def write(self, vals):
        if self:
            raise AccessError(
                self.env._("Attachment history cannot be edited directly.")
            )
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_except_history(self):
        raise AccessError(self.env._("Attachment history cannot be deleted."))

    @api.model
    def _transition(self, resources, at):
        history = self.sudo()
        devices = resources.gps_device_id
        opened = history.search(
            [
                "|",
                ("resource_id", "in", resources.ids),
                ("device_id", "in", devices.ids),
                ("date_end", "=", False),
            ]
        )
        if opened.filtered(
            lambda binding: binding.resource_id and binding.resource_id not in resources
        ):
            raise ValidationError(
                self.env._(
                    "The attachment timeline disagrees with the current GPS target."
                )
            )
        if opened.filtered(
            lambda binding: binding.date_start and binding.date_start > at
        ):
            raise ValidationError(
                self.env._(
                    "An attachment transition cannot precede its recorded start."
                )
            )
        if opened:
            super(ResourceGpsBinding, opened).write({"date_end": at})
            opened.flush_recordset(["date_end"])
        vals_list = [
            {
                "resource_id": resource.id,
                "device_id": resource.gps_device_id.id,
                "company_id": resource.company_id.id,
                "date_start": at,
                "origin": "transition",
            }
            for resource in resources
            if resource.gps_device_id
        ]
        vals_list.extend(
            {
                "device_id": binding.device_id.id,
                "company_id": binding.company_id.id,
                "date_start": at,
                "origin": "transition",
            }
            for binding in opened
            if binding.device_id not in devices
        )
        if vals_list:
            super(ResourceGpsBinding, history).create(vals_list)

    @api.model
    def _bootstrap_legacy(self):
        self.env["resource.resource"].flush_model(["gps_device_id", "company_id"])
        self.env.cr.execute("""
            SELECT r.id FROM resource_resource r JOIN device_device d ON d.id = r.gps_device_id
             WHERE r.company_id IS DISTINCT FROM d.company_id LIMIT 1
        """)
        if self.env.cr.fetchone():
            raise ValueError(
                "GPS attachment history: existing resource and device companies disagree"
            )
        self.env.cr.execute(
            """
            INSERT INTO resource_gps_binding
                (resource_id, device_id, company_id, origin, create_uid, write_uid, create_date, write_date)
            SELECT r.id, r.gps_device_id, r.company_id, 'legacy', %s, %s, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
              FROM resource_resource r
             WHERE r.gps_device_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM resource_gps_binding b WHERE b.resource_id = r.id)
        """,
            [self.env.uid, self.env.uid],
        )
        self.invalidate_model()

    @api.model
    def _tracked_resource_ids(self):
        history = self.with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="business adapters find resources with GPS history",
        )
        return history.search([("resource_id", "!=", False)]).resource_id.ids

    @api.model
    def _periods(self, resource):
        resource.check_access("read")
        history = self.with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="a resource filters its own GPS observations",
        )
        return [
            (binding.device_id.id, binding.date_start, binding.date_end)
            for binding in history.search([("resource_id", "=", resource.id)])
        ]

    @api.model
    def _observation_domain(self, resource):
        domains = []
        for device_id, date_start, date_end in self._periods(resource):
            domain = Domain("device_id", "=", device_id)
            if date_start:
                domain &= Domain("timestamp", ">=", date_start)
            if date_end:
                domain &= Domain("timestamp", "<", date_end)
            domains.append(domain)
        return Domain.OR(domains)

    @api.model
    def _custody_periods(
        self, resources, *, roles, assignees=None, date_start=None, date_end=None
    ) -> list[GpsCustodyPeriod]:
        resources.check_access("read")
        domain = [
            ("resource_id", "in", resources.ids),
            ("custody_role", "in", list(roles)),
        ]
        if assignees is not None:
            assignees.check_access("read")

        if date_start:
            domain.extend(
                ["|", ("date_end", "=", False), ("date_end", ">", date_start)]
            )
        if date_end:
            domain.append(("date_start", "<", date_end))
        Assignment = self.env["resource.assignment"]
        assignments = Assignment.search(domain)
        Assignment.flush_model(
            [
                "resource_id",
                "assignee_id",
                "date_start",
                "date_end",
                "active",
                "custody_role",
            ]
        )
        domain = [("resource_id", "in", resources.ids)]
        if date_start:
            domain.extend(
                ["|", ("date_end", "=", False), ("date_end", ">", date_start)]
            )
        if date_end:
            domain.extend(
                ["|", ("date_start", "=", False), ("date_start", "<", date_end)]
            )
        history = self.with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="a business adapter composes GPS attachment and custody",
        )
        bindings = history.search(domain)
        bindings.flush_recordset()
        self.env.cr.execute(
            self._custody_query(
                assignment_ids=assignments.ids, binding_ids=bindings.ids
            )
        )
        periods = []
        for row in self.env.cr.dictfetchall():
            if assignees is not None and row["assignee_id"] not in assignees.ids:
                continue
            start = max(value for value in (row["date_start"], date_start) if value)
            ends = [value for value in (row["date_end"], date_end) if value]
            end = min(ends) if ends else None
            if end is None or start < end:
                periods.append(
                    GpsCustodyPeriod(
                        row["resource_id"],
                        row["device_id"],
                        row["assignee_id"],
                        row["custody_role"],
                        start,
                        end,
                    )
                )
        return periods

    @api.model
    def _custody_query(self, *, assignment_ids=None, binding_ids=None):
        return SQL(
            """
            SELECT * FROM (
                SELECT b.id AS binding_id, ra.id AS assignment_id,
                       b.resource_id, b.device_id, b.company_id,
                       ra.assignee_id, ra.custody_role,
                       GREATEST(b.date_start, ra.date_start) AS date_start,
                       LEAST(b.date_end, ra.date_end) AS date_end
                  FROM resource_gps_binding b
                  JOIN (%(roles)s) ra ON ra.resource_id = b.resource_id
                 WHERE TRUE %(bindings)s
            ) periods
             WHERE date_end IS NULL OR date_start < date_end
            """,
            roles=self.env["resource.assignment"]._get_sql_effective_custody(
                assignment_ids
            ),
            bindings=SQL("AND b.id = ANY(%s)", list(binding_ids))
            if binding_ids is not None
            else SQL(),
        )

    @api.model
    def _period_values_query(self, periods):
        return SQL(
            """SELECT * FROM UNNEST(%s::int[], %s::int[], %s::timestamp[], %s::timestamp[])
               AS periods(device_id, assignee_id, date_start, date_end)""",
            [period.device_id for period in periods],
            [period.assignee_id for period in periods],
            [period.date_start for period in periods],
            [period.date_end for period in periods],
        )

    @api.model
    def _coverage(self, periods, date_from, date_to):
        Log = self.env["device.data.log.gps"].with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="a business adapter checks GPS coverage of its custody periods",
        )
        now = fields.Datetime.now()
        coverage = {}
        for period in periods:
            clock = self.env["resource.resource"].browse(period.assignee_id)
            start = clock._get_local_day_bounds(date_from)[0]
            end = clock._get_local_day_bounds(date_to)[1]
            domain = [
                ("device_id", "=", period.device_id),
                ("timestamp", ">=", period.date_start),
                ("timestamp", "<=", now),
                "|",
                ("latitude", "!=", 0),
                ("longitude", "!=", 0),
            ]
            if period.date_end:
                domain.append(("timestamp", "<", period.date_end))
            last = Log.search(  # noqa: E8507 -- a bounded index read per custody window, as the docstring says
                domain, order="timestamp desc, id desc", limit=1
            ).timestamp
            item = coverage.setdefault(
                period.assignee_id, {"with_data": False, "last_seen": None}
            )
            if last:
                item["last_seen"] = max(
                    value for value in (item["last_seen"], last) if value
                )
                item["with_data"] |= start <= last < end
                if not item["with_data"]:
                    item["with_data"] = bool(
                        Log.search(  # noqa: E8507 -- a bounded index read per custody window
                            [
                                *domain,
                                ("timestamp", ">=", start),
                                ("timestamp", "<", end),
                            ],
                            limit=1,
                        )
                    )
        return coverage

    @api.model
    def _current_periods(self, resources):
        resources.check_access("read")
        history = self.with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="a resource validates its current GPS snapshot",
        )
        return {
            binding.resource_id.id: (binding.device_id.id, binding.date_start)
            for binding in history.search(
                [("resource_id", "in", resources.ids), ("date_end", "=", False)]
            )
        }

    @api.model
    def _attribute_points(self, points):
        if not points:
            return points
        history = self.with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="GPS trails resolve their observation targets",
        )
        periods = history.search(
            [
                ("device_id", "in", sorted({point["device_id"] for point in points})),
                "|",
                ("date_start", "=", False),
                ("date_start", "<=", max(point["timestamp"] for point in points)),
                "|",
                ("date_end", "=", False),
                ("date_end", ">", min(point["timestamp"] for point in points)),
            ]
        )
        timelines = {}
        utc_min = fields.Datetime.to_datetime("0001-01-01")
        for device, bindings in periods.grouped("device_id").items():
            bindings = bindings.sorted(
                lambda period: (
                    period.date_start or utc_min,
                    period.id,
                )
            )
            timelines[device.id] = (
                [period.date_start or utc_min for period in bindings],
                bindings,
            )
        for point in points:
            starts, bindings = timelines.get(point["device_id"], ([], history.browse()))
            index = bisect_right(starts, point["timestamp"]) - 1
            binding = bindings[index : index + 1] if index >= 0 else history.browse()
            if binding and binding.date_end and binding.date_end <= point["timestamp"]:
                binding = history.browse()
            point["binding_id"] = binding.id
            point["resource_id"] = binding.resource_id.id
        return points

    @api.model
    def _at_query(self, device, timestamp):
        return SQL(
            """
            SELECT b.id AS binding_id, b.resource_id, b.company_id, b.date_start,
                   CASE WHEN b.id IS NULL THEN
                       (SELECT MIN(next.date_start) FROM resource_gps_binding next
                         WHERE next.device_id = %(device)s AND next.date_start > %(timestamp)s)
                       ELSE b.date_end END AS date_end,
                   r.tz
              FROM (SELECT 1) anchor
              LEFT JOIN resource_gps_binding b
                ON b.device_id = %(device)s
               AND (b.date_start IS NULL OR b.date_start <= %(timestamp)s)
               AND (b.date_end IS NULL OR b.date_end > %(timestamp)s)
              LEFT JOIN resource_resource r ON r.id = b.resource_id
        """,
            device=device,
            timestamp=timestamp,
        )
