from odoo import api, fields, models
from odoo.libs.json import loads as json_loads
from odoo.tools.misc import format_datetime


class WizardSocialStreamPostCreateLead(models.TransientModel):
    """Simple wizard allowing to convert a social.stream.post or a comment/reply to a post into
    a lead.

    This wizard is typically used from the "Feed" social view, when the end user can interact with
    its community through their posts or view other people's posts.
    For more information about the 2 'sources' of conversion ('comment' and 'stream_post'), see
    #action_convert_to_lead.

    Please note that for obvious privacy reasons, the social media platforms will not provide us
    with people's email, phone or address information, we only have the author name and the content
    of their post/comment.
    For that reason, end users will probably often only convert to leads based on existing clients,
    since otherwise they will not have any mean to contact the created lead."""

    _name = "wizard.social.stream.post.create.lead"
    _description = "Convert Social Post to Lead"

    action = fields.Selection(
        selection=[
            ("create", "Create a new customer"),
            ("exist", "Link to an existing customer"),
            ("nothing", "Do not link to a customer"),
        ],
        string="Related Customer",
        compute="_compute_partner_action_data",
        store=True,
        readonly=False,
    )
    conversion_source = fields.Selection(
        selection=[
            ("comment", "From a comment"),
            ("stream_post", "From a stream post"),
        ],
        default="comment",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        compute="_compute_partner_action_data",
        store=True,
        readonly=False,
    )
    social_stream_post_id = fields.Many2one(comodel_name="social.stream.post")
    social_account_id = fields.Many2one(comodel_name="social.account")
    author_name = fields.Char(
        string="Post Author Name",
        compute="_compute_post_data",
        store=True,
        readonly=False,
    )
    post_content = fields.Html()
    post_datetime = fields.Datetime(
        compute="_compute_post_data",
        store=True,
        readonly=False,
    )
    post_link = fields.Char(
        compute="_compute_post_data",
        store=True,
        readonly=False,
    )
    post_image_urls = fields.Text(
        string="Post Images URLs"
    )
    utm_source_id = fields.Many2one(
        comodel_name="utm.source",
        compute="_compute_utm_data",
    )
    utm_medium_id = fields.Many2one(
        comodel_name="utm.medium",
        compute="_compute_utm_data",
    )
    utm_campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        compute="_compute_utm_data",
    )

    @api.depends("author_name")
    def _compute_partner_action_data(self) -> None:

        for wizard in self:
            partner = False
            if wizard.author_name and len(wizard.author_name) > 3:
                partner = self.env["res.partner"].name_search(wizard.author_name)
            if partner and len(partner) == 1:
                wizard.action = "exist"
                wizard.partner_id = partner[0][0]
            else:
                wizard.action = "create"
                wizard.partner_id = False

    @api.depends("social_stream_post_id", "conversion_source")
    def _compute_post_data(self) -> None:

        for wizard in self:
            if (
                wizard.conversion_source == "stream_post"
                and wizard.social_stream_post_id
            ):
                wizard.author_name = wizard.social_stream_post_id.author_name
                wizard.post_datetime = wizard.social_stream_post_id.published_date
                wizard.post_link = wizard.social_stream_post_id.post_link
            else:
                wizard.author_name = wizard.author_name or False
                wizard.post_datetime = wizard.post_datetime or False
                wizard.post_link = wizard.post_link or False

    @api.depends("social_stream_post_id", "social_account_id")
    def _compute_utm_data(self) -> None:

        utm_source_social_post = self.env.ref(
            "social_crm.utm_source_social_post", raise_if_not_found=False
        )
        for wizard in self:
            wizard.utm_campaign_id = False
            wizard.utm_medium_id = wizard.social_account_id.utm_medium_id.id
            wizard.utm_source_id = False

            if wizard.social_stream_post_id:
                social_post = wizard.social_stream_post_id.sudo()._get_matching_post()
                if social_post:
                    wizard.utm_campaign_id = social_post.utm_campaign_id.id
                    wizard.utm_source_id = social_post.source_id.id
                elif utm_source_social_post:
                    wizard.utm_source_id = utm_source_social_post.id

    def action_convert_to_lead(self):

        self.check_singleton()
        if self.action == "create":
            self.partner_id = self.env["res.partner"].create({"name": self.author_name})

        lead_values = {
            "name": self.env._("Request from %s", self.author_name),
            "partner_id": self.partner_id.id,
            "source_id": self.utm_source_id.id,
            "medium_id": self.utm_medium_id.id,
            "campaign_id": self.utm_campaign_id.id,
            "description": self.env["ir.qweb"]._render(
                "social_crm.social_post_to_lead_description",
                {
                    "object": self,
                    "post_datetime": format_datetime(
                        self.env,
                        self.post_datetime,
                        dt_format="yyyy-MM-dd HH:mm:ss (ZZZZ)",
                    ),
                    "post_image_urls": json_loads(self.post_image_urls)
                    if self.post_image_urls
                    else False,
                },
            ),
        }

        if self.action == "nothing":
            lead_values["contact_name"] = self.author_name

        lead_sudo = (
            self.env["crm.lead"]
            .with_context(mail_create_nosubscribe=True, mail_create_nolog=True)
            .sudo()
            .create(lead_values)
        )

        if not lead_sudo.with_env(self.env).has_access("read"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "success",
                    "message": self.env._("The lead has been created successfully."),
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }

        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "crm.crm_lead_all_leads"
        )
        action.update(
            {
                "res_id": lead_sudo.id,
                "view_mode": "form",
                "views": [(False, "form")],
            }
        )
        return action
