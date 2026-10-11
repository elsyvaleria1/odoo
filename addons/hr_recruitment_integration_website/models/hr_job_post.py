from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrJobPost(models.Model):
    _inherit = "hr.job.post"

    apply_method = fields.Selection(
        selection_add=[("redirect", "Redirect to Website")],
        ondelete={"redirect": "cascade"},
    )

    @api.depends("job_id.full_url")
    def _compute_apply_vector(self) -> None:
        redirect_records = self.filtered(lambda r: r.apply_method == "redirect")
        for record in redirect_records:
            record.apply_vector = record.job_id.full_url if record.job_id else False

        _debug.pipeline(
            "website_job_post_apply_vector",
            posts=self,
            redirect=redirect_records,
            delegated=self - redirect_records,
        )
        self -= redirect_records
        super()._compute_apply_vector()

    def _contact_point_to_vector(self):
        self.check_singleton()
        _debug.logic(
            "website_job_post_contact_point",
            post=self,
            apply_method=self.apply_method,
            by="job_apply_url" if self.apply_method == "redirect" else "super",
        )
        if self.apply_method == "redirect":
            return "job_apply_url"
        return super()._contact_point_to_vector()
