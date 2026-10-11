from odoo import api, fields, models
from odoo.fields import Domain


class MarketingParticipant(models.Model):
    _name = "marketing.participant"
    _description = "Marketing Participant"
    _order = "id ASC"
    _rec_name = "resource_ref"

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if "res_id" in fields and not defaults.get("res_id"):
            model_name = defaults.get("model_name")
            if not model_name and defaults.get("campaign_id"):
                model_name = (
                    self.env["marketing.campaign"]
                    .browse(defaults["campaign_id"])
                    .model_name
                )
            if model_name and model_name in self.env:
                resource = self.env[model_name].search([], limit=1)
                defaults["res_id"] = resource.id
        return defaults

    @api.model
    def _selection_target_model(self):
        models = self.env["ir.model"].sudo().search([("is_mail_thread", "=", True)])
        return [(model.model, model.name) for model in models]

    def _search_resource_ref(self, operator, value):
        if operator in Domain.NEGATIVE_OPERATORS:
            return NotImplemented
        ir_model_ids = []
        for [model_name] in self.env["marketing.campaign"]._read_group(
            [], ["model_name"]
        ):
            model = self.env.get(model_name)
            if model is None:
                continue
            ir_model_ids += (
                self.env["marketing.participant"]
                .search(
                    [
                        "&",
                        ("model_name", "=", model_name),
                        (
                            "res_id",
                            "in",
                            [name[0] for name in model.name_search(name=value)],
                        ),
                    ],
                    order="id",
                )
                .ids
            )
        return [("id", "in", ir_model_ids)]

    campaign_id = fields.Many2one(
        comodel_name="marketing.campaign",
        index=True,
        required=True,
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        related="campaign_id.model_id",
        string="Model",
        readonly=True,
    )
    model_name = fields.Char(
        related="campaign_id.model_id.model",
        string="Record model",
        readonly=True,
    )
    runtime_id = fields.Many2one(
        comodel_name="automation.runtime",
        string="Workflow Run",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    res_id = fields.Integer(
        related="runtime_id.res_id",
        string="Record ID",
        readonly=False,
    )
    resource_ref = fields.Reference(
        selection="_selection_target_model",
        string="Record",
        compute="_compute_resource_ref",
        inverse="_inverse_resource_ref",
        search="_search_resource_ref",
    )
    trace_ids = fields.One2many(
        comodel_name="marketing.trace",
        inverse_name="participant_id",
        string="Actions",
    )
    state = fields.Selection(
        selection=[
            ("running", "Running"),
            ("completed", "Completed"),
            ("unlinked", "Removed"),
        ],
        compute="_compute_state",
        store=True,
        index=True,
        readonly=False,
        help="Removed means the related record does not exist anymore.",
    )
    is_test = fields.Boolean(
        string="Test Record",
        default=False,
    )

    @api.depends("model_name", "res_id")
    def _compute_resource_ref(self) -> None:
        for participant in self:
            if participant.model_name and participant.model_name in self.env:
                participant.resource_ref = "%s,%s" % (
                    participant.model_name,
                    participant.res_id or 0,
                )
            else:
                participant.resource_ref = None

    def _inverse_resource_ref(self) -> None:
        for participant in self:
            if participant.resource_ref:
                participant.res_id = participant.resource_ref.id

    @api.depends("runtime_id.state")
    def _compute_state(self):
        for participant in self:
            if participant.state == "unlinked":
                continue
            participant.state = (
                "completed"
                if participant.runtime_id.state in ("done", "error", "cancel")
                else "running"
            )

    @api.model_create_multi
    def create(self, vals_list):
        campaigns = self.env["marketing.campaign"].browse(
            [vals["campaign_id"] for vals in vals_list]
        )
        runtimes = (
            self.env["automation.runtime"]
            .sudo()
            .with_context(tracking_disable=True)
            .create(
                [
                    {
                        "automation_id": campaign.automation_rule_id.id,
                        "res_model": campaign.model_name,
                        "res_id": vals.pop("res_id", False) or 0,
                    }
                    for vals, campaign in zip(vals_list, campaigns, strict=True)
                ]
            )
        )
        for vals, runtime in zip(vals_list, runtimes, strict=True):
            vals["runtime_id"] = runtime.id
        participants = super().create(vals_list)
        participants._launch()
        return participants

    def _launch(self) -> None:
        self.runtime_id.sudo().filtered(
            lambda run: run.state == "draft" and run.automation_id.action_server_ids
        )._launch()

    def unlink(self):
        runtimes = self.runtime_id.sudo()
        res = super().unlink()
        runtimes.exists().unlink()
        return res

    def action_set_completed(self) -> None:
        self._action_set_completed(trace_message=self.env._("Marked as completed"))

    def _action_set_completed(self, trace_message=False) -> None:
        self._close(state="completed", trace_message=trace_message)

    def _close(self, state, trace_message=False):
        runtimes = self.runtime_id.sudo()
        if trace_message:
            runtimes.line_ids.filtered(
                lambda line: line.state not in ("done", "error", "skipped", "cancel"),
            ).error_message = trace_message
        runtimes.action_cancel()
        self.state = state

    def action_set_running(self) -> None:
        for participant in self:
            runtime = participant.runtime_id.sudo()
            if runtime.state == "done":
                runtime.state = "in_progress"
        self.state = "running"

    def action_set_unlink(self) -> None:
        self._close(state="unlinked", trace_message=self.env._("Record deleted"))
