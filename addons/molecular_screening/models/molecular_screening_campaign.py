from odoo import api, fields, models


class MolecularScreeningCampaign(models.Model):
    _name = "molecular.screening.campaign"
    _description = "Molecular Screening Campaign"
    _inherit = ["mixin.mail.thread"]
    _order = "date desc, id desc"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )

    name = fields.Char(
        required=True,
        tracking=True,
    )
    date = fields.Date(default=fields.Date.context_today)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("validation", "Validation"),
            ("selection", "Selection"),
            ("docking", "Docking"),
            ("done", "Closed"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
    )
    note = fields.Html(string="Notes")
    target_ids = fields.One2many(
        comodel_name="molecular.target",
        inverse_name="campaign_id",
        string="Targets",
    )
    role_ids = fields.One2many(
        comodel_name="molecular.compound.role",
        inverse_name="campaign_id",
        string="Compound Roles",
    )
    job_ids = fields.One2many(
        comodel_name="molecular.docking.job",
        inverse_name="campaign_id",
        string="Docking Jobs",
    )
    target_count = fields.Integer(compute="_compute_counts")
    target_passed_count = fields.Integer(compute="_compute_counts")
    compound_count = fields.Integer(compute="_compute_counts")
    candidate_count = fields.Integer(compute="_compute_counts")
    job_count = fields.Integer(compute="_compute_counts")

    @api.depends(
        "target_ids.validation_state",
        "role_ids.role",
        "job_ids",
    )
    def _compute_counts(self):
        for campaign in self:
            candidates = campaign._get_compounds("candidate")
            campaign.target_count = len(campaign.target_ids)
            campaign.target_passed_count = len(
                campaign.target_ids.filtered(lambda t: t.validation_state == "pass")
            )
            campaign.compound_count = len(campaign.role_ids.compound_id)
            campaign.candidate_count = len(candidates)
            campaign.job_count = len(campaign.job_ids)

    def _get_compounds(self, role):
        self.check_singleton()
        return self.role_ids.filtered(lambda r: r.role == role).compound_id

    def action_prepare_docking_jobs(self):
        Job = self.env["molecular.docking.job"]
        for campaign in self:
            for target in campaign.target_ids - campaign.job_ids.target_id:
                Job.create(
                    {
                        "campaign_id": campaign.id,
                        "target_id": target.id,
                        "pairs_expected": campaign.candidate_count,
                    }
                )

    def _action_open_related(self, xmlid, domain):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(xmlid)
        action["domain"] = domain
        action["context"] = {"default_campaign_id": self.id}
        return action

    def action_open_targets(self):
        return self._action_open_related(
            "molecular_screening.molecular_target_action",
            [("campaign_id", "=", self.id)],
        )

    def action_open_compounds(self):
        return self._action_open_related(
            "molecular_screening.molecular_compound_action",
            [("role_ids.campaign_id", "=", self.id)],
        )

    def action_open_jobs(self):
        return self._action_open_related(
            "molecular_screening.molecular_docking_job_action",
            [("campaign_id", "=", self.id)],
        )
