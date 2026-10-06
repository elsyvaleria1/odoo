from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict


class MolecularDockingResult(models.Model):
    _name = "molecular.docking.result"
    _access_anchors = frozendict({"company": "job_id.campaign_id.company_id"})
    _description = "Molecular Docking Result"
    _order = "job_id, score, pose_rank"

    job_id = fields.Many2one(
        comodel_name="molecular.docking.job",
        index=True,
        required=True,
        ondelete="cascade",
    )
    campaign_id = fields.Many2one(related="job_id.campaign_id")
    target_id = fields.Many2one(related="job_id.target_id")
    structure_id = fields.Many2one(
        comodel_name="molecular.structure",
        index=True,
        required=True,
        ondelete="restrict",
        help="The exact geometry that was docked, not just the compound.",
    )
    compound_id = fields.Many2one(related="structure_id.compound_id")
    score = fields.Float(
        string="Score (kcal/mol)",
        digits=(16, 2),
        required=True,
    )
    rmsd_lb = fields.Float(
        string="RMSD l.b. (Å)",
        digits=(16, 2),
    )
    rmsd_ub = fields.Float(
        string="RMSD u.b. (Å)",
        digits=(16, 2),
    )
    pose_rank = fields.Integer(
        default=1,
        required=True,
    )
    pose_molblock = fields.Text(string="Docked Pose")

    _pose_uniq = models.Constraint(
        "unique(job_id, structure_id, pose_rank)",
        "This pose is already recorded for the structure in this job.",
    )

    @api.constrains("job_id")
    def _check_job_not_blocked(self):
        for result in self:
            if result.job_id.status == "blocked":
                raise ValidationError(
                    self.env._(
                        "Job %(job)s is blocked because its target failed the "
                        "redocking gate, so it cannot hold results.",
                        job=result.job_id.display_name,
                    )
                )
