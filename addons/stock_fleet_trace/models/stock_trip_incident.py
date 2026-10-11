from odoo import api, fields, models
from odoo.exceptions import UserError

LOSS_TYPES = ("spill", "damage", "theft")


class StockTripIncident(models.Model):

    _name = "stock.trip.incident"
    _description = "Trip Incident"
    _inherit = ["mixin.mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(
        default=lambda self: self.env._("New"),
        copy=False,
        readonly=True,
        required=True,
    )
    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index=True,
        required=True,
        domain="[('date_departure', '!=', False)]",
        ondelete="restrict",
    )
    company_id = fields.Many2one(
        related="batch_id.company_id",
    )
    vehicle_id = fields.Many2one(related="batch_id.vehicle_id")
    incident_type = fields.Selection(
        selection=[
            ("spill", "Spill"),
            ("damage", "Damaged goods"),
            ("theft", "Theft or robbery"),
            ("breakdown", "Vehicle breakdown or accident"),
            ("driver_change", "Relief driver"),
            ("fuel", "Refuelling"),
            ("other", "Other"),
        ],
        string="Type",
        required=True,
        tracking=True,
    )
    date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    description = fields.Text(required=True)
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    odometer = fields.Float()
    fuel_liters = fields.Float(string="Litres Loaded")
    fuel_amount = fields.Monetary(string="Amount Paid")
    currency_id = fields.Many2one(related="company_id.currency_id")
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Relief Driver",
        help="Driver who takes the vehicle over from here.",
    )
    line_ids = fields.One2many(
        comodel_name="stock.trip.incident.line",
        inverse_name="incident_id",
        string="Goods Lost",
    )
    is_loss = fields.Boolean(compute="_compute_is_loss")
    negligence = fields.Boolean(
        tracking=True,
        help="The loss is attributed to the driver's negligence.",
    )
    trip_rescue_batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Rescue Trip",
        copy=False,
        readonly=True,
        help="Trip that took over the load after this breakdown.",
    )
    state = fields.Selection(
        selection=[
            ("reported", "Reported"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="reported",
        required=True,
        tracking=True,
    )
    reviewed_uid = fields.Many2one(
        comodel_name="res.users",
        string="Reviewed By",
        copy=False,
        readonly=True,
    )
    review_note = fields.Text()
    scrap_ids = fields.One2many(
        comodel_name="stock.scrap",
        inverse_name="trip_incident_id",
        string="Write-offs",
    )

    @api.depends("incident_type")
    def _compute_is_loss(self) -> None:
        for incident in self:
            incident.is_loss = incident.incident_type in LOSS_TYPES

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", self.env._("New")) == self.env._("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "stock.trip.incident"
                ) or self.env._("New")
        incidents = super().create(vals_list)
        for incident in incidents:
            incident._check_trip_on_route()
            incident.batch_id._trip_checkpoint(
                "incident",
                incident_id=incident.id,
                odometer=incident.odometer,
                latitude=incident.latitude,
                longitude=incident.longitude,
                employee_id=incident.employee_id.id,
                note=f"{incident.name}: {incident.description}",
            )
        return incidents

    def _check_trip_on_route(self) -> None:
        self.check_singleton()
        if not self.batch_id.date_departure or self.batch_id.date_return:
            raise UserError(
                self.env._(
                    "Trip %s is not on the route: incidents are recorded between its "
                    "departure and its return.",
                    self.batch_id.name,
                )
            )

    def _check_reviewer(self) -> None:
        self.check_singleton()
        if self.env.user == self.batch_id.supervisor_id or self.has_access("unlink"):
            return
        raise UserError(
            self.env._(
                "Incident %(incident)s is reviewed by the trip's supervisor or a stock "
                "manager.",
                incident=self.name,
            )
        )

    def action_approve(self):
        for incident in self:
            if incident.state != "reported":
                raise UserError(
                    self.env._("Incident %s was already reviewed.", incident.name)
                )
            incident._check_reviewer()
            if incident.is_loss:
                if not incident.line_ids:
                    raise UserError(
                        self.env._(
                            "Incident %s is a loss: list the goods lost first.",
                            incident.name,
                        )
                    )
                incident._write_off_goods()
            incident.write({"state": "approved", "reviewed_uid": self.env.uid})
            incident.batch_id._trip_checkpoint(
                "incident_approved",
                incident_id=incident.id,
                method="system",
                note=incident.review_note or incident.name,
            )

    def action_reject(self):
        for incident in self:
            if incident.state != "reported":
                raise UserError(
                    self.env._("Incident %s was already reviewed.", incident.name)
                )
            incident._check_reviewer()
            incident.write({"state": "rejected", "reviewed_uid": self.env.uid})
            incident.batch_id._trip_checkpoint(
                "incident_rejected",
                incident_id=incident.id,
                method="system",
                note=incident.review_note or incident.name,
            )

    def _write_off_goods(self):
        self.check_singleton()
        batch = self.batch_id
        scraps = self.env["stock.scrap"]
        for line in self.line_ids:
            location = batch._trip_location_holding(line.product_id, line.trace_id)
            if not location:
                raise UserError(
                    self.env._(
                        "%(product)s is not on the vehicle of trip %(batch)s.",
                        product=line.product_id.display_name,
                        batch=batch.name,
                    )
                )
            batch._trip_free_reservation(
                location, line.product_id, line.trace_id, line.quantity, line.picking_id
            )
            scrap = self.env["stock.scrap"].create(
                {
                    "product_id": line.product_id.id,
                    "product_uom_id": line.product_id.uom_id.id,
                    "trace_id": line.trace_id.id,
                    "scrap_qty": line.quantity,
                    "location_id": location.id,
                    "company_id": batch.company_id.id,
                    "origin": f"{batch.name} / {self.name}",
                    "trip_incident_id": self.id,
                }
            )
            scrap._action_done()
            scrap.move_ids.write(
                {"trip_batch_id": batch.id, "trip_move_kind": "write_off"}
            )
            scraps |= scrap
        return scraps


class StockTripIncidentLine(models.Model):

    _name = "stock.trip.incident.line"
    _description = "Trip Incident Line"

    incident_id = fields.Many2one(
        comodel_name="stock.trip.incident",
        index=True,
        required=True,
        ondelete="cascade",
    )
    batch_id = fields.Many2one(related="incident_id.batch_id")
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery",
        domain="[('batch_id', '=', batch_id)]",
        help="Delivery the lost goods were for, when known: its reservation is the "
        "one reduced.",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
    )
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot",
        domain="[('product_id', '=', product_id)]",
    )
    quantity = fields.Float(
        digits="Product Unit",
        required=True,
    )
    uom_id = fields.Many2one(related="product_id.uom_id")

    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "The quantity lost must be positive.",
    )

    def _trip_goods_weight(self):
        return sum(line.product_id._trip_weight(line.quantity) for line in self)


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    trip_incident_id = fields.Many2one(
        comodel_name="stock.trip.incident",
        index="btree_not_null",
        readonly=True,
    )
