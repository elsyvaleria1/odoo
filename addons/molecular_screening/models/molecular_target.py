from odoo import api, fields, models
from odoo.tools import frozendict


class MolecularTarget(models.Model):
    _name = "molecular.target"
    _access_anchors = frozendict({"company": "campaign_id.company_id"})
    _description = "Molecular Screening Target"
    _order = "campaign_id, name"

    name = fields.Char(
        string="Key",
        required=True,
    )
    campaign_id = fields.Many2one(
        comodel_name="molecular.screening.campaign",
        index=True,
        required=True,
        ondelete="cascade",
    )
    pdb_code = fields.Char(string="PDB")
    reference_ligand = fields.Char(help="Residue code of the co-crystallised ligand.")
    reference_active = fields.Char(help="Known active the gate redocks.")
    reference_smiles = fields.Char()
    cofactors = fields.Char(string="Kept Cofactors")
    note = fields.Text()
    validation_run_ids = fields.One2many(
        comodel_name="molecular.validation.run",
        inverse_name="target_id",
        string="Validation Runs",
    )
    active_validation_id = fields.Many2one(
        comodel_name="molecular.validation.run",
        string="Governing Run",
        domain="[('target_id', '=', id)]",
        help="The validation run that decides whether this target may be docked. "
        "Earlier attempts stay on file.",
    )
    validation_run_count = fields.Integer(
        compute="_compute_validation",
        store=True,
    )
    validation_state = fields.Selection(
        selection=[("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail")],
        compute="_compute_validation",
        store=True,
    )
    rmsd_top = fields.Float(
        related="active_validation_id.rmsd_top",
        string="Top RMSD (Å)",
        digits=(16, 2),
    )
    rmsd_best = fields.Float(
        related="active_validation_id.rmsd_best",
        string="Best RMSD (Å)",
        digits=(16, 2),
    )
    affinity_top = fields.Float(
        related="active_validation_id.affinity_top",
        string="Top Affinity (kcal/mol)",
        digits=(16, 2),
    )
    job_ids = fields.One2many(
        comodel_name="molecular.docking.job",
        inverse_name="target_id",
        string="Docking Jobs",
    )

    _name_campaign_uniq = models.Constraint(
        "unique(campaign_id, name)",
        "A target key must be unique within a campaign.",
    )

    @api.depends("validation_run_ids", "active_validation_id.passed")
    def _compute_validation(self):
        for target in self:
            target.validation_run_count = len(target.validation_run_ids)
            if not target.active_validation_id:
                target.validation_state = "pending"
            else:
                target.validation_state = (
                    "pass" if target.active_validation_id.passed else "fail"
                )

    def action_activate_latest_run(self):
        """Let the most recent validation run govern the target."""
        for target in self:
            # Two runs recorded in the same second tie on create_date, so the id
            # breaks the tie and "latest" stays unambiguous.
            runs = target.validation_run_ids.sorted(
                lambda run: (run.create_date, run.id), reverse=True
            )
            target.active_validation_id = runs[:1]
