from odoo import fields, models


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    trigger_ids = fields.One2many(
        comodel_name="iot.trigger",
        inverse_name="workcenter_id",
        string="Triggers",
    )


class IotTrigger(models.Model):
    _name = "iot.trigger"
    _description = "IOT Trigger"
    _order = "sequence"

    sequence = fields.Integer(default=1)
    device_id = fields.Many2one(
        comodel_name="iot.device",
        index=True,
        required=True,
        domain="[('type', '=', 'keyboard')]",
    )
    key = fields.Char()
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        index="btree_not_null",
    )
    action = fields.Selection(
        selection=[
            ("picture", "Take Picture"),
            ("SKIP", "Skip"),
            ("PAUS", "Pause"),
            ("PREV", "Previous"),
            ("NEXT", "Next"),
            ("VALI", "Validate"),
            ("CLMO", "Close MO"),
            ("CLWO", "Close WO"),
            ("FINI", "Finish"),
            ("RECO", "Record Production"),
            ("CANC", "Cancel"),
            ("PROP", "Print Operation"),
            ("PRSL", "Print Delivery Slip"),
            ("PRNT", "Print Labels"),
            ("PACK", "Pack"),
            ("SCRA", "Scrap"),
        ]
    )


class IotDevice(models.Model):
    _inherit = "iot.device"

    trigger_ids = fields.One2many(
        comodel_name="iot.trigger",
        inverse_name="device_id",
    )
