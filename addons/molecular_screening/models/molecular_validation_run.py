from odoo import api, fields, models
from odoo.tools import frozendict


class MolecularValidationRun(models.Model):
    _name = "molecular.validation.run"
    _access_anchors = frozendict({"company": "target_id.campaign_id.company_id"})
    _description = "Redocking Validation Run"
    _order = "target_id, create_date desc"
    _rec_name = "display_name"

    target_id = fields.Many2one(
        comodel_name="molecular.target",
        index=True,
        required=True,
        ondelete="cascade",
    )
    campaign_id = fields.Many2one(related="target_id.campaign_id")
    ref_ligand = fields.Char(
        required=True,
        help="Residue code redocked by this run.",
    )
    box_center_x = fields.Float(digits=(16, 2))
    box_center_y = fields.Float(digits=(16, 2))
    box_center_z = fields.Float(digits=(16, 2))
    box_size_x = fields.Float(digits=(16, 2))
    box_size_y = fields.Float(digits=(16, 2))
    box_size_z = fields.Float(digits=(16, 2))
    autobox_padding = fields.Float(
        string="Autobox Padding (Å)",
        digits=(16, 2),
        help="Padding added around the reference ligand when the box came from it.",
    )
    engine = fields.Char(
        required=True,
        help="Docking engine, e.g. smina.",
    )
    engine_ver = fields.Char(
        string="Engine Version",
        required=True,
    )
    scoring = fields.Char(help="Scoring function, e.g. vina or vinardo.")
    exhaustiveness = fields.Integer()
    rmsd_top = fields.Float(
        string="Top RMSD (Å)",
        digits=(16, 2),
        required=True,
        help="RMSD of the top-ranked pose against the crystallographic pose.",
    )
    threshold = fields.Float(
        string="Threshold (Å)",
        digits=(16, 2),
        default=2.0,
        required=True,
    )
    passed = fields.Boolean(
        compute="_compute_passed",
        store=True,
    )
    rmsd_best = fields.Float(
        digits=(16, 2),
        compute="_compute_poses",
        store=True,
    )
    best_pose_rank = fields.Integer(
        compute="_compute_poses",
        store=True,
    )
    affinity_top = fields.Float(
        digits=(16, 2),
        compute="_compute_poses",
        store=True,
    )
    pose_ids = fields.One2many(
        comodel_name="molecular.validation.pose",
        inverse_name="run_id",
        string="Poses",
    )
    notes = fields.Text()

    @api.depends("target_id.name", "engine", "scoring")
    def _compute_display_name(self):
        for run in self:
            parts = [run.target_id.name or "", run.engine or "", run.scoring or ""]
            run.display_name = " / ".join(part for part in parts if part)

    @api.depends("rmsd_top", "threshold")
    def _compute_passed(self):
        for run in self:
            # The gate judges the top-ranked pose only: a correct pose buried
            # further down means the scoring cannot be trusted to rank.
            run.passed = run.rmsd_top <= run.threshold

    @api.depends("pose_ids.rank", "pose_ids.rmsd", "pose_ids.affinity")
    def _compute_poses(self):
        for run in self:
            poses = run.pose_ids.sorted("rank")
            if not poses:
                run.rmsd_best = run.affinity_top = 0.0
                run.best_pose_rank = 0
                continue
            best = min(poses, key=lambda pose: pose.rmsd)
            run.rmsd_best = best.rmsd
            run.best_pose_rank = best.rank
            run.affinity_top = poses[0].affinity

    def action_set_active(self):
        """Make this run the one that governs its target."""
        for run in self:
            run.target_id.active_validation_id = run


class MolecularValidationPose(models.Model):
    _name = "molecular.validation.pose"
    _access_anchors = frozendict({"company": "run_id.target_id.campaign_id.company_id"})
    _description = "Validation Pose"
    _order = "run_id, rank"

    run_id = fields.Many2one(
        comodel_name="molecular.validation.run",
        index=True,
        required=True,
        ondelete="cascade",
    )
    rank = fields.Integer(required=True)
    affinity = fields.Float(
        string="Affinity (kcal/mol)",
        digits=(16, 2),
    )
    rmsd = fields.Float(
        string="RMSD (Å)",
        digits=(16, 2),
    )

    _rank_uniq = models.Constraint(
        "unique(run_id, rank)", "Two poses of a run cannot share a rank."
    )
