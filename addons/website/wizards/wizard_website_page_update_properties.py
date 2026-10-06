from collections import defaultdict

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardWebsitePageUpdateProperties(models.TransientModel):
    _name = "wizard.website.page.update.properties"
    _description = "Page Properties"
    _inherit = [
        "wizard.website.update.page.properties",
    ]

    target_model_id = fields.Many2one(comodel_name="website.page")
    name = fields.Char(
        related="target_model_id.name",
        readonly=False,
    )
    url = fields.Char(
        related="target_model_id.url",
        readonly=False,
    )
    date_publish = fields.Datetime(
        related="target_model_id.date_publish",
        readonly=False,
    )
    website_indexed = fields.Boolean(
        related="target_model_id.website_indexed",
        readonly=False,
    )
    visibility = fields.Selection(
        related="target_model_id.visibility",
        readonly=False,
    )
    visibility_password_display = fields.Char(
        related="target_model_id.visibility_password_display",
        readonly=False,
    )
    group_ids = fields.Many2many(
        related="target_model_id.group_ids",
        readonly=False,
    )
    is_new_page_template = fields.Boolean(
        related="target_model_id.is_new_page_template",
        readonly=False,
    )

    old_url = fields.Char()
    redirect_old_url = fields.Boolean(
        default=False,
        store=False,
    )
    redirect_type = fields.Selection(
        selection=[
            ("301", "301 Moved permanently"),
            ("302", "302 Moved temporarily"),
        ],
        default="301",
        store=False,
        required=True,
    )

    @api.depends("url", "website_id.homepage_url")
    def _compute_is_homepage(self) -> None:
        for record in self:
            url = record.url
            current_homepage_url = record.website_id.homepage_url or "/"
            record.is_homepage = url == current_homepage_url

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.old_url = record.url
        return records

    def write(self, vals):
        write_result = super().write(vals)

        if "url" not in vals:
            return write_result
        moved = [record for record in self if record.old_url != record.url]
        if not moved:
            return write_result

        # One search and one create for the whole batch. Both used to run per
        # record inside the loop, so renaming N pages cost N searches plus N
        # inserts -- and `website.rewrite` is exactly the table a bulk rename
        # touches most.
        #
        # `dfd50c87d614` fixed the search half of this independently and landed
        # in the same branch; this batches the archives and the creates as
        # well. Only the search half is gated -- `lint_n_plus_one_query_odoo` reads
        # six query methods and no write, so the inserts here were invisible to
        # it: the rule (n-plus-one-query, E8507) sees no write, and this method
        # is the loop of writes it cannot see.
        #
        # The search carries both clauses. An earlier version of this dropped
        # the `website_id` one and filtered on the key afterwards, to avoid
        # putting a `False` into an `in` list; `dfd50c87d614` shipped exactly
        # that and it resolves to IS NULL as it should, so the reason for the
        # wider fetch was never a real one.
        Rewrite = self.env["website.rewrite"]
        website_by_record = {
            record: (vals.get("website_id") or record.website_id.id or False)
            for record in moved
        }
        obsolete_by_key = defaultdict(Rewrite.browse)
        for rewrite in Rewrite.search(
            [
                ("url_from", "in", list({record.url for record in moved})),
                ("website_id", "in", list(set(website_by_record.values()))),
            ]
        ):
            obsolete_by_key[(rewrite.url_from, rewrite.website_id.id or False)] |= (
                rewrite
            )

        to_archive = Rewrite.browse()
        redirects_to_create = []
        for record in moved:
            website_id = website_by_record[record]
            _debug.lifecycle(
                "page_properties_url_changed",
                page=record.target_model_id.id,
                old=record.old_url,
                new=record.url,
                redirect=bool(vals.get("redirect_old_url")),
            )
            if obsolete := obsolete_by_key.get((record.url, website_id)):
                _debug.lifecycle(
                    "obsolete_rewrites_archived",
                    page=record.target_model_id.id,
                    url=record.url,
                    rewrites=obsolete.ids,
                )
                to_archive |= obsolete
            if vals.get("redirect_old_url"):
                redirects_to_create.append(
                    {
                        "name": vals.get("name") or record.name,
                        "redirect_type": vals.get("redirect_type")
                        or record.redirect_type,
                        "url_from": record.old_url,
                        "url_to": record.url,
                        "website_id": website_id,
                    }
                )

        if to_archive:
            to_archive.active = False
        if redirects_to_create:
            Rewrite.create(redirects_to_create)
        for record in moved:
            record.old_url = record.url

        return write_result
