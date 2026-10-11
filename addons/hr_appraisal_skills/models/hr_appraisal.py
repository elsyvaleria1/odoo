from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import convert

_debug = DebugLog(__name__)


class HrAppraisal(models.Model):
    _name = "hr.appraisal"
    _inherit = ["mixin.hr.individual.skill.owner", "hr.appraisal"]

    target_job_id = fields.Many2one(comodel_name="hr.job")
    appraisal_skill_ids = fields.One2many(
        comodel_name="hr.appraisal.skill",
        inverse_name="appraisal_id",
        string="Skills",
        domain=[
            "|",
            ("skill_type_id.active", "=", True),
            ("appraisal_id.state", "=", "3_done"),
        ],
    )
    current_appraisal_skill_ids = fields.One2many(
        comodel_name="hr.appraisal.skill",
        inverse_name="appraisal_id",
        compute="_compute_current_appraisal_skill_ids",
        readonly=False,
    )

    def _individual_skill_field_name(self):
        return "appraisal_skill_ids"

    def _current_individual_skill_field_name(self):
        return "current_appraisal_skill_ids"

    def _individual_skill_command_field_names(self) -> tuple:
        return ("current_appraisal_skill_ids",)

    @api.depends("appraisal_skill_ids.valid_to", "appraisal_skill_ids.is_certification")
    def _compute_current_appraisal_skill_ids(self) -> None:
        for appraisal in self:
            appraisal.current_appraisal_skill_ids = (
                appraisal.appraisal_skill_ids.filtered(
                    lambda appraisal_skill: (
                        appraisal_skill.is_certification
                        or not appraisal_skill.valid_to
                        or appraisal_skill.valid_to >= fields.Date.today()
                    )
                )
            )

    def _prepare_target_job_skill_commands(self):
        self.check_singleton()
        today = fields.Date.today()
        target_skills = self.target_job_id.current_job_skill_ids
        placeholders = self.appraisal_skill_ids.filtered(
            lambda appraisal_skill: not appraisal_skill.skill_level_id
        )
        assessed = self.appraisal_skill_ids.filtered(
            lambda appraisal_skill: (
                appraisal_skill.skill_level_id
                and (
                    appraisal_skill.is_certification
                    or not appraisal_skill.valid_to
                    or appraisal_skill.valid_to >= today
                )
            )
        )
        commands = [
            Command.unlink(placeholder.id)
            for placeholder in placeholders
            if placeholder.skill_id not in target_skills.skill_id
            or placeholder.skill_id in assessed.skill_id
        ]
        covered = assessed.skill_id | placeholders.skill_id
        commands += [
            Command.create(
                {
                    "skill_id": job_skill.skill_id.id,
                    "skill_type_id": job_skill.skill_type_id.id,
                    "skill_level_id": False,
                    "valid_from": today,
                    "valid_to": False,
                    "appraisal_id": self._origin.id,
                }
            )
            for job_skill in target_skills
            if job_skill.skill_id not in covered
        ]
        _debug.pipeline(
            "target_job_skills_synced",
            appraisal=self,
            target_job=self.target_job_id,
            target_skills=target_skills,
            placeholders=placeholders,
            assessed=assessed,
            commands=len(commands),
        )
        return commands

    def _sync_target_job_skills(self) -> None:
        for appraisal in self:
            if commands := appraisal._prepare_target_job_skill_commands():
                appraisal.write({"appraisal_skill_ids": commands})

    @api.onchange("target_job_id")
    def _onchange_target_job_id(self) -> None:
        if commands := self._prepare_target_job_skill_commands():
            self.appraisal_skill_ids = commands

    @api.model_create_multi
    def create(self, vals_list):
        appraisals = super().create(vals_list)
        appraisals.filtered("target_job_id")._sync_target_job_skills()
        return appraisals

    def write(self, vals):
        if "state" in vals and vals["state"] == "2_pending":
            new_appraisals = self.filtered(lambda a: a.state == "1_new")
            _debug.pipeline("skills_copied_on_confirm", appraisals=new_appraisals)
            new_appraisals._copy_skills_when_confirmed()

        if "state" in vals and (vals["state"] == "3_done"):
            _debug.pipeline("skills_applied_on_done", appraisals=self)
            for appraisal in self:
                appraisal._apply_skills_to_employee()
        result = super().write(vals)
        if "target_job_id" in vals:
            self._sync_target_job_skills()
        return result

    def _apply_skills_to_employee(self) -> None:
        self.check_singleton()
        employee_skills = self.employee_id.current_employee_skill_ids
        employee_skills_by_skill = employee_skills.grouped("skill_id")
        appraisal_skills = self.current_appraisal_skill_ids.filtered("skill_level_id")
        commands = []
        updated_skills = []
        added_skills = []
        for appraisal_skill in appraisal_skills:
            held = employee_skills_by_skill.get(appraisal_skill.skill_id)
            if not held:
                added_skills.append(appraisal_skill.skill_id.name)
                commands.append(
                    Command.create(
                        {
                            "skill_id": appraisal_skill.skill_id.id,
                            "skill_level_id": appraisal_skill.skill_level_id.id,
                            "skill_type_id": appraisal_skill.skill_type_id.id,
                            "valid_from": appraisal_skill.valid_from
                            if appraisal_skill.is_certification
                            else fields.Date.today(),
                            "valid_to": appraisal_skill.valid_to
                            if appraisal_skill.is_certification
                            else False,
                        }
                    )
                )
                continue
            latest = held.sorted("valid_from")[-1:]
            if latest.skill_level_id == appraisal_skill.skill_level_id:
                continue
            updated_skills.append(
                {
                    "name": appraisal_skill.skill_id.name,
                    "old_level": latest.level_progress,
                    "new_level": appraisal_skill.level_progress,
                    "justification": appraisal_skill.justification,
                }
            )
            commands.append(
                Command.update(
                    latest.id, {"skill_level_id": appraisal_skill.skill_level_id.id}
                )
            )
        deleted_skills = employee_skills.filtered(
            lambda skill: skill.skill_id not in appraisal_skills.skill_id
        )
        commands += [Command.delete(skill.id) for skill in deleted_skills]
        if not commands:
            return
        self.employee_id.sudo().write({"current_employee_skill_ids": commands})
        rendered = self.env["ir.qweb"]._render(
            "hr_appraisal_skills.appraisal_skills_update_template",
            {
                "updated_skills": updated_skills,
                "added_skills": added_skills,
                "deleted_skills": deleted_skills.mapped("skill_id.name"),
            },
            raise_if_not_found=False,
        )
        self.message_post(body=rendered)

    def _copy_skills_when_confirmed(self) -> None:
        vals = []
        for appraisal in self:
            employee_skills = appraisal.employee_id.current_employee_skill_ids
            if appraisal.appraisal_skill_ids:
                appraisal.appraisal_skill_ids.unlink()
            vals += [
                {
                    "appraisal_id": appraisal.id,
                    "skill_id": skill.skill_id.id,
                    "previous_skill_level_id": skill.skill_level_id.id,
                    "skill_level_id": skill.skill_level_id.id,
                    "skill_type_id": skill.skill_type_id.id,
                    "valid_from": skill.valid_from,
                    "valid_to": skill.valid_to,
                }
                for skill in employee_skills
            ]
        self.env["hr.appraisal.skill"].sudo().create(vals)

    def _load_demo_data(self) -> dict | None:
        super()._load_demo_data()
        convert.convert_file(
            self.env,
            "hr_appraisal_skills",
            "demo/scenarios/scenario_appraisal_demo.xml",
            None,
            mode="init",
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
