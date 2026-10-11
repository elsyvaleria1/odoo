from odoo import api, fields, models

ONBOARDING_PROGRESS_STATES = [
    ("not_done", "Not done"),
    ("just_done", "Just done"),
    ("done", "Done"),
]


class OnboardingProgress(models.Model):
    _name = "onboarding.progress"
    _description = "Onboarding Progress Tracker"
    _rec_name = "onboarding_id"

    onboarding_state = fields.Selection(
        selection=ONBOARDING_PROGRESS_STATES,
        string="Onboarding progress",
        compute="_compute_onboarding_state",
        store=True,
    )
    is_onboarding_closed = fields.Boolean(string="Was panel closed?")
    company_id = fields.Many2one(
        comodel_name="res.company",
        ondelete="cascade",
    )
    onboarding_id = fields.Many2one(
        comodel_name="onboarding.onboarding",
        string="Related onboarding tracked",
        index=True,
        required=True,
        ondelete="cascade",
    )
    progress_step_ids = fields.Many2many(
        comodel_name="onboarding.progress.step",
        string="Progress Steps Trackers",
    )

    _onboarding_company_uniq = models.UniqueIndex(
        "(onboarding_id, COALESCE(company_id, 0))"
    )

    @api.depends(
        "onboarding_id.step_ids", "progress_step_ids", "progress_step_ids.step_state"
    )
    def _compute_onboarding_state(self) -> None:
        for progress in self:
            progress.onboarding_state = (
                "not_done"
                if (
                    len(
                        progress.progress_step_ids.filtered(
                            lambda p: p.step_state in {"just_done", "done"}
                        )
                    )
                    != len(progress.onboarding_id.step_ids)
                )
                else "done"
            )

    def _recompute_progress_step_ids(self) -> None:
        for progress in self:
            progress.progress_step_ids = (
                progress.onboarding_id.step_ids.current_progress_step_id
            )

    def action_close(self):
        self.is_onboarding_closed = True

    def action_toggle_visibility(self) -> None:
        for progress in self:
            progress.is_onboarding_closed = not progress.is_onboarding_closed

    def _get_and_update_onboarding_state(self):
        self.check_singleton()
        onboarding_states_values = {}
        progress_steps_to_consolidate = self.env["onboarding.progress.step"]

        for step in self.onboarding_id.step_ids:
            step_state = step.current_step_state
            if step_state == "just_done":
                progress_steps_to_consolidate |= step.current_progress_step_id
            onboarding_states_values[step.id] = step_state

        progress_steps_to_consolidate.action_consolidate_just_done()

        if self.is_onboarding_closed:
            onboarding_states_values["onboarding_state"] = "closed"
        elif self.onboarding_state == "done":
            onboarding_states_values["onboarding_state"] = (
                "just_done" if progress_steps_to_consolidate else "done"
            )
        return onboarding_states_values
