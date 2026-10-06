from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import RedirectWarning
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrJobPost(models.Model):
    _name = "hr.job.post"
    _description = "Job Post"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _order = "write_date desc"

    job_id = fields.Many2one(
        comodel_name="hr.job",
        index=True,
        readonly=True,
        required=True,
    )
    recruiter_id = fields.Many2one(
        comodel_name="res.users",
        related="job_id.user_id",
        string="Recruiter",
        readonly=True,
    )
    platform_id = fields.Many2one(
        comodel_name="hr.recruitment.platform",
        readonly=True,
        required=True,
    )
    platform_icon = fields.Binary(
        related="platform_id.avatar_128",
        export_string_translation=False,
    )
    apply_method = fields.Selection(
        selection=[
            ("email", "Email"),
        ],
        string="Contact Method",
        default="email",
        required=True,
    )
    apply_vector = fields.Char(
        string="Contact Point",
        compute="_compute_apply_vector",
        store=True,
        readonly=False,
        help="The email address, phone number, url to send applications to.",
    )
    post_html = fields.Html(
        string="Description",
        required=True,
        prefetch=False,
    )
    status = fields.Selection(
        selection=[
            ("success", "Success"),
            ("warning", "Warning"),
            ("pending", "Pending"),
            ("failure", "Failure"),
            ("expired", "Expired"),
            ("deleted", "Deleted"),
        ],
        readonly=True,
        required=True,
    )
    status_message = fields.Text(
        readonly=True,
        prefetch=False,
    )
    api_data = fields.Json(
        string="API Data",
        readonly=True,
        prefetch=False,
    )
    campaign_start_date = fields.Date(
        default=fields.Date.today,
        help="The date when the campaign will start.",
    )
    campaign_end_date = fields.Date(
        help="The date when the campaign will end. If not set, "
        "the campaign will run indefinitely or to the maximum allowed by a platform."
    )
    company_id = fields.Many2one(related="job_id.company_id")

    def _compute_display_name(self):
        for record in self:
            record.display_name = self.env._(
                "%(job)s on %(platform)s",
                job=record.job_id.name,
                platform=record.platform_id.name,
            )

    @api.depends(
        "apply_method",
        "job_id.alias_id.alias_full_name",
        "job_id.user_id.employee_id",
        "job_id.user_id.employee_id.work_email",
    )
    def _compute_apply_vector(self) -> None:
        for record in self:
            if record.apply_method != "email":
                continue
            job = record.job_id
            if job and job.alias_id.alias_full_name:
                record.apply_vector = job.alias_id.alias_full_name
            elif job and job.user_id and job.user_id.employee_id:
                record.apply_vector = job.user_id.employee_id.work_email
            else:
                record.apply_vector = False

    def unlink(self):
        for job_post in self:
            job_post.sudo()._remove_post()
        return super().unlink()

    def _start_new_campaign(self) -> None:
        posts_to_start = self.env["hr.job.post"].search(
            [
                ("status", "=", "pending"),
                ("campaign_start_date", "<=", fields.Date.today()),
                "|",
                ("campaign_end_date", ">=", fields.Date.today()),
                ("campaign_end_date", "=", False),
            ],
            order="campaign_start_date",
            limit=5,
        )
        wizards = self.env["wizard.hr.job.create.post"].create(
            [
                {
                    "job_id": post.job_id.id,
                    "apply_method": post.apply_method,
                    "platform_ids": [Command.set(post.platform_id.ids)],
                    "campaign_start_date": post.campaign_start_date,
                    "campaign_end_date": post.campaign_end_date,
                    "post_html": post.post_html,
                    "post_ids": post.ids,
                    post._contact_point_to_vector(): post.apply_vector,
                }
                for post in posts_to_start
            ]
        )
        _debug.pipeline("campaigns_started", posts=posts_to_start, wizards=wizards)
        for wizard in wizards:
            wizard._post_job()
        if len(posts_to_start) == 5:
            _debug.logic("campaign_cron_retriggered", phase="start")
            self.env.ref(
                "hr_recruitment_integration_base.job_board_campaign_manager_start"
            )._trigger()

    def _stop_finished_campaign(self) -> None:
        posts_to_end = self.env["hr.job.post"].search(
            [
                ("status", "not in", ["deleted", "expired"]),
                ("campaign_end_date", "<=", fields.Date.today()),
            ],
            order="campaign_end_date",
            limit=5,
        )
        _debug.pipeline("campaigns_stopped", posts=posts_to_end)
        for post in posts_to_end:
            post._remove_post()
        if len(posts_to_end) == 5:
            _debug.logic("campaign_cron_retriggered", phase="stop")
            self.env.ref(
                "hr_recruitment_integration_base.job_board_campaign_manager_stop"
            )._trigger()

    def _remove_post(self):
        """Delete the post on the platform.
        to be overridden by the specific platform module."""
        pass

    def _contact_point_to_vector(self):
        self.check_singleton()
        if self.apply_method == "email":
            return "job_apply_mail"
        return ""

    def action_update_job_post_check(self) -> None:
        self.check_singleton()
        if self.platform_id.price_to_update:
            raise RedirectWarning(
                message=self.env._(
                    "This action will update the job post on the platform. "
                    "This action will cost %(price)s credits. Do you want to continue?",
                    price=self.platform_id.price_to_update,
                ),
                action=self.env.ref(
                    "hr_recruitment_integration_base.hr_job_post_double_check_action"
                ).id,
                additional_context={"active_id": self.id},
                button_text=self.env._("Update"),
            )
        self.action_update_job_post()

    def action_update_job_post(self) -> dict:
        self.check_singleton()
        post_wizard = self.env["wizard.hr.job.create.post"].create(
            {
                "job_id": self.job_id.id,
                "apply_method": self.apply_method,
                "platform_ids": [Command.set(self.platform_id.ids)],
                "campaign_start_date": self.campaign_start_date,
                "campaign_end_date": self.campaign_end_date,
                "post_html": self.post_html,
                "post_ids": self.ids,
                self._contact_point_to_vector(): self.apply_vector,
                "api_data": self.api_data,
            }
        )
        post_wizard.action_post_job()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def action_post_job(self):
        view_name = "hr_recruitment_post_job_wizard_view_form"
        if not self.job_id:
            view_name = "hr_recruitment_post_job_wizard_view_job_selectable_form"
        view_id = self.env.ref("hr_recruitment_integration_base." + view_name).id
        return {
            "name": self.env._("Publish on a Job Board"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.hr.job.create.post",
            "view_mode": "form",
            "view_id": view_id,
            "context": {
                "default_job_id": self.job_id.id if self.job_id else False,
                "from_global_view": not self.job_id,
                "default_apply_method": self.apply_method or "email",
                "post_html": self.post_html,
            },
            "views": [(view_id, "form")],
            "target": "new",
        }

    def action_post_now(self) -> None:
        self.check_singleton()
        self.sudo().write(
            {
                "campaign_start_date": fields.Date.today(),
            }
        )
        self._start_new_campaign()

    def action_stop_campaign(self) -> None:
        self.check_singleton()
        self.sudo().write(
            {
                "campaign_end_date": fields.Date.today(),
            }
        )
        self._stop_finished_campaign()

    @api.model_create_multi
    def create(self, vals_list):
        posts = super().create(vals_list)
        posts._log_post_modifications()
        return posts

    def _log_post_modifications(self, mode=None) -> None:
        if mode is None:
            mode = self.env._("created")
        for post in self:
            post.message_post(
                author_id=self.env.user.partner_id.id,
                subject=self.env._(
                    "Job Post on %(platform)s has been modified",
                    platform=post.platform_id.name,
                ),
                body=Markup(
                    """
                        <strong>%(line_1)s</strong> <br/>
                        <strong>%(line_2)s</strong>  %(job)s\n<br/>
                        <strong>%(line_3)s</strong>  %(status)s<br/>
                        <strong>%(line_4)s</strong> %(status_message)s<br/>
                        <strong>%(line_5)s</strong> %(method)s<br/>
                        <strong>%(line_6)s</strong> %(vector)s<br/>
                        <strong>%(line_7)s</strong> %(start_date)s<br/>
                        <strong>%(line_8)s</strong> %(end_date)s <br/>
                        <strong>%(line_9)s</strong> %(company)s
                    """
                )
                % {
                    "line_1": self.env._(
                        "Job Post on %(platform)s has been %(mode)s",
                        platform=post.platform_id.name,
                        mode=mode,
                    ),
                    "line_2": self.env._("Job:"),
                    "line_3": self.env._("Status:"),
                    "line_4": self.env._("Status Message:"),
                    "line_5": self.env._("Contact Method:"),
                    "line_6": self.env._("Contact Point:"),
                    "line_7": self.env._("Campaign Start Date:"),
                    "line_8": self.env._("Campaign End Date:"),
                    "line_9": self.env._("Company:"),
                    "job": post.job_id.name,
                    "status": dict(post._fields["status"].selection).get(post.status),
                    "status_message": post.status_message,
                    "method": dict(post._fields["apply_method"].selection).get(
                        post.apply_method
                    ),
                    "vector": post.apply_vector,
                    "start_date": post.campaign_start_date,
                    "end_date": post.campaign_end_date or self.env._("No Limit"),
                    "company": post.company_id.name,
                },
            )
