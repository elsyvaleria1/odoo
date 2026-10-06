import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import UserError

CHECKPOINT_TYPES = [
    ("load", "Loaded"),
    ("departure", "Departure"),
    ("arrival", "Arrival at customer"),
    ("delivery", "Delivery"),
    ("rejection", "Product rejected"),
    ("not_delivered", "Not delivered"),
    ("incident", "Incident reported"),
    ("incident_approved", "Incident approved"),
    ("incident_rejected", "Incident rejected"),
    ("handover", "Handover to another vehicle"),
    ("driver_change", "Relief driver"),
    ("fuel", "Refuelling"),
    ("return", "Return"),
    ("unload", "Unloading confirmed"),
    ("scan", "Code scanned"),
    ("correction", "Correction"),
]
METHODS = [
    ("system", "System"),
    ("manual", "Manual"),
    ("barcode", "Barcode"),
    ("gps", "GPS"),
]
# The fields whose values the hash seals, in a fixed order. A later reading of the
# chain recomputes the digest from these and from the previous checkpoint's.
HASHED_FIELDS = (
    "batch_id",
    "sequence",
    "event_type",
    "date",
    "picking_id",
    "product_id",
    "trace_id",
    "quantity",
    "reason_id",
    "incident_id",
    "odometer",
    "fuel_level",
    "weight_on_board",
    "latitude",
    "longitude",
    "method",
    "user_id",
    "employee_id",
    "note",
)


class StockTripCheckpoint(models.Model):
    """One event of a delivery trip, sealed to the one before it."""

    _name = "stock.trip.checkpoint"
    _description = "Trip Checkpoint"
    _order = "batch_id, sequence"
    _rec_name = "event_type"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index=True,
        required=True,
        ondelete="restrict",
    )
    company_id = fields.Many2one(
        related="batch_id.company_id",
    )
    sequence = fields.Integer(readonly=True)
    event_type = fields.Selection(
        selection=CHECKPOINT_TYPES,
        string="Event",
        required=True,
    )
    date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery",
        index="btree_not_null",
    )
    partner_id = fields.Many2one(related="picking_id.partner_id")
    product_id = fields.Many2one(comodel_name="product.product")
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot",
    )
    quantity = fields.Float(digits="Product Unit")
    reason_id = fields.Many2one(
        comodel_name="stock.picking.unbatch.reason",
        string="Reason",
    )
    incident_id = fields.Many2one(comodel_name="stock.trip.incident")
    odometer = fields.Float()
    fuel_level = fields.Float(help="Fuel on board when the event happened.")
    weight_on_board = fields.Float(
        string="Weight on Board",
        digits="Stock Weight",
        help="Theoretical weight of the goods on the vehicle right after the event.",
    )
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    method = fields.Selection(
        selection=METHODS,
        default="manual",
        required=True,
        help="How the event was captured. Only GPS, barcode and system events are "
        "verified; a manual one is someone's word.",
    )
    verified = fields.Boolean(compute="_compute_verified")
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Recorded By",
        default=lambda self: self.env.user,
        required=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Employee",
        help="Driver the event concerns, e.g. the relief driver who takes over.",
    )
    note = fields.Text()
    previous_hash = fields.Char(readonly=True)
    hash = fields.Char(
        index=True,
        readonly=True,
    )

    @api.depends("method")
    def _compute_verified(self) -> None:
        for checkpoint in self:
            checkpoint.verified = checkpoint.method in ("system", "barcode", "gps")

    def _hash_payload(self, previous_hash):
        """Serialize the sealed fields with the previous digest.

        :param str previous_hash: digest of the checkpoint before this one
        :rtype: str
        """
        self.check_singleton()
        values = {}
        for name in HASHED_FIELDS:
            value = self[name]
            if isinstance(value, models.BaseModel):
                value = value.id
            elif name == "date":
                value = fields.Datetime.to_string(value)
            elif isinstance(value, float):
                value = f"{value:.6f}"
            values[name] = value or False
        return json.dumps(
            {"previous": previous_hash or "", "values": values},
            sort_keys=True,
            default=str,
        )

    def _compute_hash(self, previous_hash):
        return hashlib.sha256(
            self._hash_payload(previous_hash).encode("utf-8")
        ).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        checkpoints = self.browse()
        # One at a time: each seals the one created just before it on its trip.
        for vals in vals_list:
            batch = self.env["stock.picking.batch"].browse(vals["batch_id"])
            batch.lock_for_update(wait=True)
            last = self.search(  # noqa: E8507 - each checkpoint seals the one before it, under the trip lock
                [("batch_id", "=", batch.id)], order="sequence desc", limit=1
            )
            checkpoint = super().create([{**vals, "sequence": last.sequence + 1}])
            digest = checkpoint._compute_hash(last.hash)
            # Written below the ORM write guard: nobody else may set these.
            super(StockTripCheckpoint, checkpoint).write(
                {"previous_hash": last.hash or "", "hash": digest}
            )
            checkpoints |= checkpoint
        return checkpoints

    def write(self, vals):
        if not self:
            return True
        raise UserError(
            self.env._(
                "A trip checkpoint cannot be changed. Record a correction instead."
            )
        )

    @api.ondelete(at_uninstall=True)
    def _unlink_never(self) -> None:
        raise UserError(
            self.env._(
                "A trip checkpoint cannot be deleted. Record a correction instead."
            )
        )

    def _check_chain(self):
        """Return the checkpoints whose digest no longer matches their content.

        :return: checkpoints edited behind the ORM, or whose predecessor was
        :rtype: recordset
        """
        broken = self.browse()
        previous = ""
        for checkpoint in self.sorted("sequence"):
            if (
                checkpoint.previous_hash != previous
                or checkpoint._compute_hash(previous) != checkpoint.hash
            ):
                broken |= checkpoint
            previous = checkpoint.hash
        return broken
