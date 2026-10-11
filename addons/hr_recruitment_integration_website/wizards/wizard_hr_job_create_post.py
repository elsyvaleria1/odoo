from odoo import api, fields, models
from odoo.exceptions import RedirectWarning
from odoo.libs.debug_log import DebugLog
from odoo.tools.mail import is_html_empty

_debug = DebugLog(__name__)


class WizardHrJobCreatePost(models.TransientModel):
    _inherit = "wizard.hr.job.create.post"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        job = self.env["hr.job"].browse(res.get("job_id"))
        if not job:
            return res
        if "job_apply_url" in fields:
            res["job_apply_url"] = job.full_url
        return res

    apply_method = fields.Selection(
        selection_add=[
            ("redirect", "Redirect to company's website"),
        ],
        default="redirect",
    )
    job_apply_url = fields.Char(
        string="Job url",
        compute="_compute_job_apply_url",
        store=True,
        readonly=False,
    )
    post_html = fields.Html(required=False)
    platform_ids = fields.Many2many(required=False)
    campaign_start_date = fields.Date(required=False)
    job_is_published = fields.Boolean(related="job_id.is_published")

    @api.depends("job_id")
    def _compute_post_html(self) -> None:
        super()._compute_post_html()
        post_job_wizards_with_job = self.filtered(lambda job_wizard: job_wizard.job_id)
        for post_job_wizard in post_job_wizards_with_job:
            post_job_wizard.post_html = (
                post_job_wizard.job_id._get_plain_text_description()
            )

    @api.depends("job_id")
    def _compute_job_apply_url(self) -> None:
        for post_job_wizard in self:
            post_job_wizard.job_apply_url = (
                post_job_wizard.job_id.full_url if post_job_wizard.job_id else False
            )

    def _get_apply_vector(self):
        self.check_singleton()
        _debug.logic(
            "website_post_job_apply_vector",
            wizard=self,
            job=self.job_id,
            apply_method=self.apply_method,
            by="job_apply_url" if self.apply_method == "redirect" else "super",
            url=self.job_apply_url,
        )
        if self.apply_method == "redirect":
            return self.job_apply_url
        return super()._get_apply_vector()

    def _check_fields_before_posting(self, error_msg=""):
        if is_html_empty(self.post_html):
            error_msg += self.env._("Description is required.\n")
        if not self.platform_ids:
            error_msg += self.env._("At least one job board must be selected.\n")
        if self.apply_method == "redirect" and not self.job_apply_url:
            error_msg += self.env._(
                "URL is required if the apply method is 'Redirect to company's website'.\n"
            )
        if not self.campaign_start_date:
            error_msg += self.env._("Campaign Start Date is required.\n")
        _debug.logic(
            "website_post_job_field_check",
            wizard=self,
            job=self.job_id,
            apply_method=self.apply_method,
            description_is_empty=is_html_empty(self.post_html),
            platforms=len(self.platform_ids),
            has_apply_url=bool(self.job_apply_url),
            has_campaign_start_date=bool(self.campaign_start_date),
            message_length=len(error_msg),
        )
        return super()._check_fields_before_posting(error_msg)

    def action_post_job(self):
        res = super().action_post_job()
        _debug.lifecycle(
            "website_post_job_posted",
            wizard=self,
            job=self.job_id,
            apply_method=self.apply_method,
            published_as_a_side_effect=self.apply_method == "redirect"
            and not self.job_id.is_published,
        )
        if self.apply_method == "redirect" and not self.job_id.is_published:
            self.job_id.is_published = True
        return res

    def action_generate_post(self, warning=True):
        self.check_singleton()
        _debug.pipeline(
            "website_post_job_generate_requested",
            wizard=self,
            job=self.job_id,
            warning=warning,
            by="confirmation_asked" if self.post_html and warning else "generated",
            existing_description_length=len(self.post_html or ""),
            from_global_view=self.env.context.get("from_global_view", False),
        )
        if self.post_html and warning:
            additional_ctx = {
                "active_id": self.id,
                "from_global_view": self.env.context.get("from_global_view", False),
            }
            raise RedirectWarning(
                message=self.env._(
                    "The Job Description will be replaced with the generated one, do you want to continue?"
                ),
                action=self.env.ref(
                    "hr_recruitment_integration_website.hr_recruitment_post_job_wizard_action_regenerate_post"
                ).id,
                button_text=self.env._("Generate"),
                additional_context=additional_ctx,
            )
        self.post_html = self.job_id._generate_post()
        view_id = False
        if self.env.context.get("from_global_view"):
            view_id = self.env.ref(
                "hr_recruitment_integration_base.hr_recruitment_post_job_wizard_view_job_selectable_form"
            ).id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Publish on a Job Board"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "views": [(view_id, "form")],
            "context": {"active_model": self._name},
            "target": "new",
        }
