from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict


class MolecularDockingJob(models.Model):
    _name = "molecular.docking.job"
    _access_anchors = frozendict({"company": "campaign_id.company_id"})
    _description = "Molecular Docking Job"
    _order = "campaign_id, target_id"
    _rec_name = "display_name"

    campaign_id = fields.Many2one(
        comodel_name="molecular.screening.campaign",
        index=True,
        required=True,
        ondelete="cascade",
    )
    target_id = fields.Many2one(
        comodel_name="molecular.target",
        index=True,
        required=True,
        ondelete="cascade",
    )
    status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("running", "Running"),
            ("ok", "Done"),
            ("error", "Error"),
            ("blocked", "Blocked"),
        ],
        default="pending",
        required=True,
        help="Blocked means the target did not pass its redocking gate, so its "
        "ranking would not be trustworthy. Other targets are unaffected.",
    )
    pairs_expected = fields.Integer(default=0)
    pairs_done = fields.Integer(
        compute="_compute_pairs_done",
        store=True,
    )
    error_msg = fields.Text(string="Error")
    started_at = fields.Datetime()
    finished_at = fields.Datetime()
    engine = fields.Char()
    engine_ver = fields.Char(string="Engine Version")
    result_ids = fields.One2many(
        comodel_name="molecular.docking.result",
        inverse_name="job_id",
        string="Results",
    )

    _target_campaign_uniq = models.Constraint(
        "unique(campaign_id, target_id)",
        "This target already has a docking job in the campaign.",
    )

    @api.depends("target_id.name", "campaign_id.name")
    def _compute_display_name(self):
        for job in self:
            job.display_name = "{} — {}".format(
                job.campaign_id.name or "", job.target_id.name or ""
            )

    @api.depends("result_ids.compound_id")
    def _compute_pairs_done(self):
        for job in self:
            job.pairs_done = len(job.result_ids.compound_id)

    @api.constrains("campaign_id", "target_id")
    def _check_same_campaign(self):
        for job in self:
            if job.target_id.campaign_id != job.campaign_id:
                raise ValidationError(
                    self.env._("The target belongs to another campaign.")
                )

    @api.constrains("status", "target_id")
    def _check_gate(self):
        for job in self:
            if job.status in ("running", "ok") and (
                job.target_id.validation_state != "pass"
            ):
                raise ValidationError(
                    self.env._(
                        "Target %(target)s has not passed its redocking gate, so its "
                        "job cannot run. Record a passing validation run first.",
                        target=job.target_id.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            target = self.env["molecular.target"].browse(vals.get("target_id"))
            if target.validation_state != "pass" and not vals.get("status"):
                vals["status"] = "blocked"
        return super().create(vals_list)

    def action_refresh_gate(self):
        for job in self:
            passed = job.target_id.validation_state == "pass"
            if not passed and job.status in ("pending", "running"):
                job.status = "blocked"
            elif passed and job.status == "blocked":
                job.status = "pending"
