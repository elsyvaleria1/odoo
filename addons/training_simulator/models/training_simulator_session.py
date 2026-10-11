from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict


class TrainingSimulatorSession(models.Model):
    _name = "training.simulator.session"
    _description = "Training Simulator Session"
    _order = "date_start desc, id desc"
    _rec_name = "simulator_id"
    _access_anchors = frozendict({"owner": "user_id"})

    simulator_id = fields.Many2one(
        comodel_name="training.simulator",
        index=True,
        required=True,
        ondelete="cascade",
    )
    area = fields.Selection(related="simulator_id.area")
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        index=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    scenario = fields.Char()
    variant = fields.Char(
        help="What the scenario was played on, e.g. the route of a trip."
    )
    mode = fields.Char(help="How it was played, e.g. automatic or by hand.")
    state = fields.Selection(
        selection=[("running", "Playing"), ("done", "Finished")],
        default="running",
        required=True,
    )
    date_start = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    date_end = fields.Datetime()
    duration = fields.Float(
        compute="_compute_duration",
        store=True,
        help="Minutes played.",
    )
    passed = fields.Boolean(
        string="Completed without mistakes",
        help="The player went through the whole flow as it is done in operation.",
    )
    error_count = fields.Integer(help="Mistakes the game counted, e.g. rejected scans.")
    summary = fields.Text(help="What the game reports at the end, for the instructor.")
    snapshot = fields.Json(help="Real data read when the session started.")
    result = fields.Json(help="Everything the game sent back when it finished.")

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for session in self:
            session.duration = (
                (session.date_end - session.date_start).total_seconds() / 60
                if session.date_end and session.date_start
                else 0.0
            )

    def _training_finish(self, result):
        self.check_singleton()
        if self.state != "running" or self.user_id != self.env.user:
            raise UserError(self.env._("Only the player can finish a running session."))
        self.write(
            {
                "state": "done",
                "date_end": fields.Datetime.now(),
                "scenario": result.get("scenario") or self.scenario,
                "variant": result.get("variant") or self.variant,
                "mode": result.get("mode") or self.mode,
                "passed": bool(result.get("passed")),
                "error_count": int(result.get("error_count") or 0),
                "summary": result.get("summary") or False,
                "result": result,
            }
        )
