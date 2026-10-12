from odoo import fields, models
from odoo.exceptions import UserError


class WizardStockTripHandover(models.TransientModel):
    _name = "wizard.stock.trip.handover"
    _description = "Trip Handover"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        required=True,
        ondelete="cascade",
    )
    vehicle_id = fields.Many2one(
        comodel_name="resource.asset.vehicle",
        string="Rescue Vehicle",
        required=True,
    )
    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Rescue Driver",
        required=True,
    )
    odometer_departure = fields.Float(
        string="Rescue Vehicle Odometer",
        required=True,
    )
    fuel_departure = fields.Float(
        string="Rescue Vehicle Fuel",
        required=True,
    )
    reason = fields.Text(required=True)
    breakdown_date = fields.Datetime(
        string="Breakdown Time",
        default=fields.Datetime.now,
        required=True,
        help="When the vehicle broke down, as the driver reported it: the "
        "logistic support's response time is measured from it.",
    )

    def action_confirm(self):
        self.check_singleton()
        source = self.batch_id
        if not source.date_departure or source.date_return:
            raise UserError(
                self.env._(
                    "Only a trip on the route hands its load over; %s is not.",
                    source.name,
                )
            )
        if not source.date_departure <= self.breakdown_date <= fields.Datetime.now():
            raise UserError(
                self.env._(
                    "The breakdown time must fall between the departure of trip %s "
                    "and now.",
                    source.name,
                )
            )
        if self.vehicle_id == source.vehicle_id:
            raise UserError(self.env._("Choose a vehicle other than the trip's own."))
        incidents = self.env["stock.trip.incident"]
        if self.env.user != source.supervisor_id and not incidents.has_access("unlink"):
            raise UserError(
                self.env._(
                    "The handover of trip %s is authorised by its supervisor or a "
                    "stock manager.",
                    source.name,
                )
            )
        target = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": source.picking_type_id.id,
                "company_id": source.company_id.id,
                "vehicle_id": self.vehicle_id.id,
                "operator_id": self.operator_id.id,
                "supervisor_id": source.supervisor_id.id,
                "odometer_departure": self.odometer_departure,
                "fuel_departure": self.fuel_departure,
                "fuel_unit": source.fuel_unit,
                "description": self.env._("Rescue of %s", source.name),
            }
        )
        incident = self.env["stock.trip.incident"].create(
            {
                "batch_id": source.id,
                "incident_type": "breakdown",
                "description": self.reason,
                "date": self.breakdown_date,
                "trip_rescue_batch_id": target.id,
            }
        )
        source._trip_handover(target)
        target.action_depart()
        incident.write({"state": "approved", "reviewed_uid": self.env.uid})
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking.batch",
            "res_id": target.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
