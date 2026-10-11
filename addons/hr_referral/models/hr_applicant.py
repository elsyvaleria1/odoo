from typing import Any

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import frozendict
from odoo.tools.misc import str2bool

_debug = DebugLog(__name__)


class HrApplicant(models.Model):
    _inherit = "hr.applicant"
    _access_anchors = frozendict(
        {
            "job_interviewer": models.Anchor("job_id.interviewer_ids", kind="owner"),
            "owner": "interviewer_ids",
            "ref_user": models.Anchor("ref_user_id", kind="owner"),
        }
    )

    ref_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Referred By User",
        compute="_compute_ref_user_id",
        store=True,
        copy=False,
        readonly=False,
        tracking=True,
    )
    source_id = fields.Many2one(
        compute="_compute_source_id",
        store=True,
        readonly=False,
    )
    referral_points_ids = fields.One2many(
        comodel_name="hr.referral.points",
        inverse_name="applicant_id",
        copy=False,
    )
    earned_points = fields.Integer(compute="_compute_earned_points")
    referral_state = fields.Selection(
        selection=[
            ("progress", "Ongoing"),
            ("hired", "Hired"),
            ("closed", "Not Hired"),
        ],
        default="progress",
        required=True,
    )
    shared_item_infos = fields.Text(compute="_compute_shared_item_infos")
    max_points = fields.Integer(related="job_id.max_points")
    friend_id = fields.Many2one(
        comodel_name="hr.referral.friend",
        copy=False,
    )
    last_valuable_stage_id = fields.Many2one(comodel_name="hr.recruitment.stage")
    is_accessible_to_current_user = fields.Boolean(
        compute="_compute_is_accessible_to_current_user",
        search="_search_is_accessible_to_current_user",
    )

    def _search_is_accessible_to_current_user(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        if self.env.user.has_group("hr_recruitment.group_hr_recruitment_user"):
            return []
        applications = (
            self.env["hr.applicant"]
            .with_context(active_test=False)
            .search(
                [
                    "|",
                    ("job_id", "any", [("interviewer_ids", "in", self.env.user.id)]),
                    ("interviewer_ids", "in", self.env.user.id),
                ]
            )
        )
        return [("id", operator, applications.ids)]

    @api.depends_context("uid")
    def _compute_is_accessible_to_current_user(self) -> None:
        if self.env.user.has_group("hr_recruitment.group_hr_recruitment_user"):
            self.is_accessible_to_current_user = True
        else:
            for applicant in self:
                interviewers = applicant.interviewer_ids
                corresponding_job_interviewers = applicant.job_id.interviewer_ids
                applicant.is_accessible_to_current_user = (
                    self.env.user in interviewers
                    or self.env.user in corresponding_job_interviewers
                )
                if not applicant.is_accessible_to_current_user:
                    raise AccessError(
                        self.env._(
                            "You are not allowed to access this application record because you're not one of the interviewers of this application. If you think that's an error, please contact your administrator."
                        )
                    )

    @api.depends("source_id")
    def _compute_ref_user_id(self) -> None:
        utm_source_referral = self.env.ref(
            "utm.utm_source_referral", raise_if_not_found=False
        )
        for applicant in self:
            if applicant.source_id != utm_source_referral:
                applicant.ref_user_id = False

    @api.depends("ref_user_id")
    def _compute_source_id(self) -> None:
        utm_source_referral = self.env.ref(
            "utm.utm_source_referral", raise_if_not_found=False
        )
        for applicant in self:
            if applicant.ref_user_id and utm_source_referral:
                applicant.source_id = utm_source_referral.id

    @api.depends("referral_points_ids")
    def _compute_shared_item_infos(self) -> None:
        for applicant in self:
            stages = self.env["hr.recruitment.stage"].search(
                [
                    ("use_in_referral", "=", True),
                    "|",
                    ("job_ids", "=", False),
                    ("job_ids", "=", applicant.job_id.id),
                ]
            )
            points_by_stage = applicant.referral_points_ids.grouped("stage_id")
            infos = [
                {
                    "name": stage.name,
                    "points": stage.points,
                    "done": bool(len(points_by_stage.get(stage, ())) % 2),
                    "seq": stage.sequence,
                }
                for stage in stages
            ]
            applicant.shared_item_infos = json_dumps(infos)

    def _compute_earned_points(self) -> None:
        for applicant in self:
            applicant.earned_points = sum(
                applicant.referral_points_ids.mapped("points")
            )

    def write(self, vals):
        _debug.lifecycle("write", applicants=self, fields=list(vals))
        res = super().write(vals)
        if "ref_user_id" in vals or "stage_id" in vals or "date_closed" in vals:
            for applicant in self.filtered(lambda a: a.ref_user_id):
                if "ref_user_id" in vals:
                    _debug.lifecycle(
                        "referrer_changed_points_cleared",
                        applicant=applicant,
                        points=applicant.referral_points_ids,
                    )
                    applicant.referral_points_ids.unlink()
                applicant.sudo()._update_points(
                    applicant.stage_id.id, vals.get("last_stage_id", False)
                )
                if vals.get("stage_id"):
                    applicant.last_valuable_stage_id = vals["stage_id"]
                if "date_closed" in vals:
                    if not vals["date_closed"] and not applicant.stage_id.hired_stage:
                        applicant.referral_state = "progress"
        return res

    @api.model_create_multi
    def create(self, vals_list):
        applicants = super().create(vals_list)
        _debug.lifecycle("create", applicants=applicants, count=len(vals_list))
        for applicant in applicants:
            if applicant.ref_user_id and applicant.stage_id:
                applicant.sudo()._update_points(applicant.stage_id.id, False)
                applicant.last_valuable_stage_id = applicant.stage_id
        return applicants

    def _send_notification(
        self, body, action_value="hr_referral.action_hr_applicant_employee_referral"
    ):
        if referrer := self.ref_user_id:
            if self.partner_name:
                subject = self.env._(
                    "Referral: %(partner)s (%(applicant)s)",
                    partner=self.partner_name,
                    applicant=self.display_name,
                )
            else:
                subject = self.env._("Referral: %s", self.display_name)
            action_url = f"/odoo/action-{action_value}?active_model={self._name}"
            body = Markup("<a class='o_document_link' href=%s>%s</a><br>%s") % (
                action_url,
                subject,
                body,
            )
            odoobot = self.env.ref("base.partner_root")
            self.env["mixin.mail.thread"].sudo().message_notify(
                model=referrer._name,
                res_id=referrer.id,
                subject=subject,
                body=body,
                author_id=odoobot.id,
                partner_ids=[self.ref_user_id.partner_id.id],
                email_layout_xmlid="mail.mail_notification_light",
            )

    def _update_points(self, new_state_id, old_state_id) -> None:
        if not self.company_id:
            _debug.logic("points_refused", reason="no_company", applicant=self)
            raise UserError(self.env._("Applicant must have a company."))
        new_state = self.env["hr.recruitment.stage"].browse(new_state_id)
        old_state = self.env["hr.recruitment.stage"].browse(old_state_id)
        if old_state and old_state.use_in_referral:
            old_state_sequence = old_state.sequence
            by = "old_state"
        elif self.last_valuable_stage_id:
            old_state_sequence = self.last_valuable_stage_id.sequence
            by = "last_valuable_stage"
        else:
            old_state_sequence = -1
            by = "never_scored"
        _debug.logic(
            "points_baseline",
            by=by,
            applicant=self,
            old_sequence=old_state_sequence,
            new_sequence=new_state.sequence,
        )
        point_stage = []

        if new_state.sequence < old_state_sequence:
            _debug.pipeline("points_revoked", applicant=self, to=new_state)
            stages_to_remove = self.env["hr.referral.points"]._read_group(
                [
                    ("stage_id.use_in_referral", "=", True),
                    ("applicant_id", "=", self.id),
                    ("stage_id.sequence", "<=", old_state_sequence),
                    ("stage_id.sequence", ">", new_state.sequence),
                ],
                ["stage_id"],
                ["points:sum"],
            )
            for stage, point_sum in stages_to_remove:
                point_stage.append(
                    {
                        "applicant_id": self.id,
                        "stage_id": stage.id,
                        "points": -point_sum,
                        "ref_user_id": self.ref_user_id.id,
                        "company_id": self.company_id.id,
                    }
                )
            if not self.date_closed and not new_state.hired_stage:
                self.referral_state = "progress"

        elif new_state.sequence > old_state_sequence:
            stages_to_add = self.env["hr.recruitment.stage"].search(
                [
                    ("use_in_referral", "=", True),
                    ("sequence", ">", old_state_sequence),
                    ("sequence", "<=", new_state.sequence),
                    "|",
                    ("job_ids", "=", False),
                    ("job_ids", "=", self.job_id.id),
                ]
            )
            gained_points = 0
            available_points = sum(
                self.env["hr.referral.points"]
                .search(
                    [
                        ("ref_user_id", "=", self.ref_user_id.id),
                        ("company_id", "=", self.company_id.id),
                    ]
                )
                .mapped("points")
            )
            for stage in stages_to_add:
                gained_points += stage.points
                point_stage.append(
                    {
                        "applicant_id": self.id,
                        "stage_id": stage.id,
                        "points": stage.points,
                        "sequence_stage": stage.sequence,
                        "ref_user_id": self.ref_user_id.id,
                        "company_id": self.company_id.id,
                    }
                )
            available_points += gained_points
            additional_message = ""
            if gained_points > 0:
                additional_message = escape(
                    self.env._(
                        " You've gained {gained} points with this progress.{new_line}"
                        "It makes you a new total of {total} points. Visit {link1}this link{link2} to pick a gift!"
                    )
                ).format(
                    gained=gained_points,
                    new_line=Markup("<br/>"),
                    total=available_points,
                    link1=Markup(
                        '<a href="/odoo/action-hr_referral.action_hr_referral_reward?active_model=hr.referral.reward">'
                    ),
                    link2=Markup("</a>"),
                )
            if new_state.use_in_referral:
                if self.stage_id.hired_stage:
                    self.referral_state = "hired"
                    self._send_notification(
                        self.env._(
                            "Your referrer is hired! %(message)s",
                            message=additional_message,
                        )
                    )
                else:
                    self._send_notification(
                        self.env._(
                            "Your referrer got a step further! %(message)s",
                            message=additional_message,
                        )
                    )

        self.env["hr.referral.points"].create(point_stage)
        self.invalidate_recordset(["earned_points"])

    def choose_a_friend(self, friend_id) -> None:
        self.check_singleton()
        self_sudo = self.sudo()
        if not self.env.user:
            return
        if self_sudo.ref_user_id == self.env.user and not self_sudo.friend_id:
            self_sudo.write({"friend_id": friend_id})

    def _get_onboarding_steps(self) -> list:
        return [
            {"text": onboarding.text, "image": onboarding.image}
            for onboarding in self.env["hr.referral.onboarding"].search([])
        ]

    def _get_friends(self, applicant_names) -> list:
        return [
            {
                "id": friend.id,
                "friend": applicant_names.get(friend.id, ""),
                "name": applicant_names.get(friend.id, friend.name),
                "position": friend.position,
                "image": friend.image,
            }
            for friend in self.env["hr.referral.friend"].search([])
            if friend.id in applicant_names
        ]

    def _get_friends_head(self, applicant_names) -> list:
        return [
            {
                "id": friend.id,
                "friend": applicant_names.get(friend.id, ""),
                "name": friend.name,
                "image": friend.image_head,
            }
            for friend in self.env["hr.referral.friend"].search([])
        ]

    @api.model
    def get_referral_data(self) -> dict:
        return {
            "show_grass": str2bool(
                self.env.registry.settings.get(
                    self.env, "hr_referral.show_grass", False
                )
            ),
        }

    @api.model
    def acquire_referral_welcome_screen(self) -> dict[str, Any]:
        result = self.get_referral_data()
        user_id = self.env.user

        result["id"] = user_id.id
        if not user_id.hr_referral_onboarding_page:
            result["onboarding_screen"] = True
            result["onboarding"] = self._get_onboarding_steps()
            return result

        applicant = self.sudo().search(
            [
                ("ref_user_id", "=", user_id.id),
                ("company_id", "in", self.env.companies.ids),
            ]
        )
        applicants_hired = applicant.filtered(lambda r: r.referral_state == "hired")
        applicant_name = {
            applicant_hired.friend_id.id: applicant_hired.partner_name
            for applicant_hired in applicants_hired
        }
        applicant_without_friend = applicants_hired.filtered(lambda r: not r.friend_id)

        available_friend_count = self.env["hr.referral.friend"].search_count([])
        if bool(applicant_without_friend) and (
            len(applicants_hired) - len(applicant_without_friend)
            < available_friend_count
        ):
            result["choose_new_friend"] = True
            result["new_friend_name"] = applicant_without_friend[0].partner_name
            result["new_friend_id"] = applicant_without_friend[0].id

            result["friends"] = self._get_friends_head(applicant_name)
            return result

        result["friends"] = self._get_friends(applicant_name)

        referal_points = self.env["hr.referral.points"].search(
            [("ref_user_id", "=", user_id.id)]
        )
        result["point_received"] = sum(
            referal_points.filtered(lambda x: not x.hr_referral_reward_id).mapped(
                "points"
            )
        )
        result["point_to_spend"] = sum(referal_points.mapped("points"))

        if not user_id.hr_referral_level_id:
            user_id.hr_referral_level_id = (
                self.env["hr.referral.level"].search([], order="points asc", limit=1).id
            )

        current_level = user_id.hr_referral_level_id
        next_level = self.env["hr.referral.level"].search(
            [("points", ">", current_level.points)], order="points asc", limit=1
        )

        result["level"] = {
            "image": current_level.image,
            "name": current_level.name,
            "points": current_level.points,
        }

        result["level_percentage"] = 100
        if next_level:
            if result["point_received"] >= next_level["points"]:
                result["reach_new_level"] = True
            step_level = next_level["points"] - current_level["points"]
            result["level_percentage"] = round(
                (
                    min(result["point_received"], next_level["points"])
                    - current_level["points"]
                )
                * 100
                / step_level
            )

        result["referral"] = {
            "all": len(applicant),
            "hired": len(applicant.filtered(lambda r: r.referral_state == "hired")),
            "progress": len(
                applicant.filtered(lambda r: r.referral_state == "progress")
            ),
        }

        today = fields.Date.today()
        messages = self.env["hr.referral.alert"].search(
            [
                ("active", "=", True),
                ("dismissed_user_ids", "not in", self.env.user.id),
                "|",
                ("date_from", "<=", today),
                ("date_from", "=", False),
                "|",
                ("date_to", ">", today),
                ("date_to", "=", False),
            ]
        )

        result["message"] = []
        for message in messages:
            msg = {"id": message.id, "text": message.name}
            if message.onclick == "url":
                msg["url"] = message.url
            elif message.onclick == "all_jobs":
                msg["url"] = "/odoo/action-hr_referral.action_hr_job_employee_referral"
            result["message"].append(msg)

        return result

    @api.model
    def upgrade_level(self) -> None:
        if not self.env.user:
            return
        user_id = self.env.user
        user_points = sum(
            self.env["hr.referral.points"]
            .search(
                [
                    ("ref_user_id", "=", user_id.id),
                    ("hr_referral_reward_id", "=", False),
                ]
            )
            .mapped("points")
        )
        next_referral_level = self.env["hr.referral.level"].search(
            [
                ("points", ">", user_id.hr_referral_level_id.points),
                ("points", "<=", user_points),
            ],
            order="points asc",
            limit=1,
        )
        if next_referral_level:
            user_id.write({"hr_referral_level_id": next_referral_level.id})

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        utm_source_referral = self.env.ref(
            "utm.utm_source_referral", raise_if_not_found=False
        )
        if (
            "ref_user_id" in fields
            and (utm_source := values.get("source_id"))
            and (
                user := self.env["res.users"].search(
                    [("utm_source_id", "=", utm_source)], limit=1
                )
            )
        ):
            values["ref_user_id"] = user.id
            values["source_id"] = (
                utm_source_referral.id if utm_source_referral else False
            )
        return values

    def reset_applicant(self) -> None:
        super().reset_applicant()
        self.write({"referral_state": "progress"})


class HrRecruitmentStage(models.Model):
    _inherit = "hr.recruitment.stage"

    points = fields.Integer(
        help="Amount of points that the referent will receive when the applicant will reach this stage"
    )
    use_in_referral = fields.Boolean(
        string="Show in Referrals",
        help="This option is used in app 'Referrals'. If checked, the stage is displayed in 'Referrals Dashboard' and points are given to the employee.",
    )
