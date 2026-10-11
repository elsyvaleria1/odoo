import base64
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from odoo import api, exceptions, fields, models, modules
from odoo.libs.datetime import timezone
from odoo.tools import frozendict

from .card_template import TEMPLATE_DIMENSIONS

if TYPE_CHECKING:
    from .card_card import CardCard


class CardCampaign(models.Model):
    _name = "card.campaign"
    _description = "Marketing Card Campaign"
    _inherit = ["mixin.mail.activity", "mixin.mail.render", "mixin.mail.thread"]
    _order = "id DESC"
    _unrestricted_rendering = True
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    def _default_card_template_id(self):
        return self.env["card.template"].search([], limit=1)

    def _selection_campaign_models(self) -> list:
        allowed_models = [
            "res.partner",
            "event.track",
            "event.booth",
            "event.registration",
        ]
        models = (
            self.env["ir.model"]
            .sudo()
            .search_fetch([("model", "in", allowed_models)], ["model", "name"])
        )
        return [(model.model, model.name) for model in models]

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    body_html = fields.Html(
        related="card_template_id.body",
        readonly=False,
        render_engine="qweb",
    )

    card_count = fields.Integer(compute="_compute_card_stats")
    card_click_count = fields.Integer(compute="_compute_card_stats")
    card_share_count = fields.Integer(compute="_compute_card_stats")

    mailing_ids = fields.One2many(
        comodel_name="mailing.mailing",
        inverse_name="card_campaign_id",
    )
    mailing_count = fields.Integer(compute="_compute_mailing_count")

    card_ids = fields.One2many(
        comodel_name="card.card",
        inverse_name="campaign_id",
    )
    card_template_id = fields.Many2one(
        comodel_name="card.template",
        string="Design",
        default=lambda self: self._default_card_template_id(),
        required=True,
    )
    image_preview = fields.Image(
        attachment=False,
        compute="_compute_image_preview",
        compute_sudo=False,
        store=True,
        readonly=True,
    )
    link_tracker_id = fields.Many2one(
        comodel_name="link.tracker",
        ondelete="restrict",
    )
    res_model = fields.Selection(
        selection="_selection_campaign_models",
        string="Model Name",
        compute="_compute_res_model",
        precompute=True,
        store=True,
        readonly=True,
        required=True,
    )

    post_suggestion = fields.Text(
        help="Description below the card and default text when sharing on X"
    )
    preview_record_ref = fields.Reference(
        selection="_selection_campaign_models",
        string="Preview On",
        required=True,
    )
    tag_ids = fields.Many2many(
        comodel_name="card.campaign.tag",
        string="Tags",
    )
    target_url = fields.Char(string="Post Link")
    target_url_click_count = fields.Integer(related="link_tracker_id.count")

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
    )

    reward_message = fields.Html(string="Thank You Message")
    reward_target_url = fields.Char(string="Reward Link")
    request_title = fields.Char(
        string="Request",
        default=lambda self: self.env._("Help us share the news"),
    )
    request_description = fields.Text()

    content_background = fields.Image(string="Background")
    content_button = fields.Char(string="Button")

    content_header = fields.Char(string="Header")
    content_header_dyn = fields.Boolean(string="Is Dynamic Header")
    content_header_path = fields.Char(string="Header Path")
    content_header_color = fields.Char(string="Header Color")

    content_sub_header = fields.Char(string="Sub-Header")
    content_sub_header_dyn = fields.Boolean(string="Is Dynamic Sub-Header")
    content_sub_header_path = fields.Char(string="Sub-Header Path")
    content_sub_header_color = fields.Char(string="Sub Header Color")

    content_section = fields.Char(string="Section")
    content_section_dyn = fields.Boolean(string="Is Dynamic Section")
    content_section_path = fields.Char(string="Section Path")

    content_sub_section1 = fields.Char(string="Sub-Section 1")
    content_sub_section1_dyn = fields.Boolean(string="Is Dynamic Sub-Section 1")
    content_sub_section1_path = fields.Char(string="Sub-Section 1 Path")

    content_sub_section2 = fields.Char(string="Sub-Section 2")
    content_sub_section2_dyn = fields.Boolean(string="Is Dynamic Sub-Section 2")
    content_sub_section2_path = fields.Char(string="Sub-Section 2 Path")

    content_image1_path = fields.Char(string="Dynamic Image 1")
    content_image2_path = fields.Char(string="Dynamic Image 2")

    @api.depends("card_ids")
    def _compute_card_stats(self) -> None:
        cards_by_status_count = self.env["card.card"]._read_group(
            domain=[("campaign_id", "in", self.ids)],
            groupby=["campaign_id", "share_status"],
            aggregates=["__count"],
            order="campaign_id ASC",
        )
        self.update(
            {
                "card_count": 0,
                "card_click_count": 0,
                "card_share_count": 0,
            }
        )
        for campaign, status, card_count in cards_by_status_count:
            if status == "shared":
                campaign.card_share_count += card_count
            if status in ("shared", "visited"):
                campaign.card_click_count += card_count
            campaign.card_count += card_count

    @api.model
    def _get_fields_render(self) -> list:
        return [
            "body_html",
            "content_background",
            "content_image1_path",
            "content_image2_path",
            "content_button",
            "content_header",
            "content_header_dyn",
            "content_header_path",
            "content_header_color",
            "content_sub_header",
            "content_sub_header_dyn",
            "content_sub_header_path",
            "content_section",
            "content_section_dyn",
            "content_section_path",
            "content_sub_section1",
            "content_sub_section1_dyn",
            "content_sub_header_color",
            "content_sub_section1_path",
            "content_sub_section2",
            "content_sub_section2_dyn",
            "content_sub_section2_path",
            "card_template_id",
        ]

    def _check_access_right_dynamic_template(self, fnames=None) -> None:
        return

    @api.depends(lambda self: self._get_fields_render() + ["preview_record_ref"])
    def _compute_image_preview(self) -> None:
        for campaign in self:
            if campaign.preview_record_ref and campaign.preview_record_ref.exists():
                image = campaign._get_image_b64(campaign.preview_record_ref)
            else:
                image = False
            campaign.image_preview = image

    @api.depends("mailing_ids")
    def _compute_mailing_count(self) -> None:
        self.mailing_count = 0
        mailing_counts = self.env["mailing.mailing"]._read_group(
            [("card_campaign_id", "in", self.ids)], ["card_campaign_id"], ["__count"]
        )
        for campaign, mailing_count in mailing_counts:
            campaign.mailing_count = mailing_count

    @api.depends("preview_record_ref")
    def _compute_res_model(self) -> None:
        for campaign in self:
            preview_model = (
                campaign.preview_record_ref and campaign.preview_record_ref._name
            )
            campaign.res_model = preview_model or campaign.res_model or "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        utm_source = self.env.ref(
            "marketing_card.utm_source_marketing_card", raise_if_not_found=False
        )
        link_trackers = (
            self.env["link.tracker"]
            .sudo()
            .create(
                [
                    {
                        "url": vals.get("target_url")
                        or self.env["card.campaign"].get_base_url(),
                        "title": vals[
                            "name"
                        ],
                        "source_id": utm_source.id if utm_source else None,
                        "label": f"marketing_card_campaign_{vals.get('name', '')}_{fields.Datetime.now()}",
                    }
                    for vals in vals_list
                ]
            )
        )
        return super().create(
            [
                {
                    **vals,
                    "link_tracker_id": link_tracker_id,
                }
                for vals, link_tracker_id in zip(
                    vals_list, link_trackers.ids, strict=True
                )
            ]
        )

    def write(self, vals):
        link_tracker_vals = {}
        if vals.keys() & set(self._get_fields_render()):
            self.env["card.card"].with_context(active_test=False).search(
                [("campaign_id", "in", self.ids)]
            ).requires_sync = True
        if "target_url" in vals:
            link_tracker_vals["url"] = (
                vals["target_url"] or self.env["card.campaign"].get_base_url()
            )
        if link_tracker_vals:
            self.link_tracker_id.sudo().write(link_tracker_vals)

        original_models = self.mapped("res_model")

        write_res = super().write(vals)

        updated_model_campaigns = self.env["card.campaign"].browse(
            [
                campaign.id
                for campaign, new_model, old_model in zip(
                    self, self.mapped("res_model"), original_models, strict=True
                )
                if new_model != old_model
            ]
        )
        for campaign in updated_model_campaigns:
            if campaign.card_count:
                raise exceptions.ValidationError(
                    self.env._(
                        "Model of campaign %(campaign)s may not be changed as it already has cards",
                        campaign=campaign.display_name,
                    )
                )
        return write_res

    def action_view_cards(self):
        self.check_singleton()
        return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_card.cards_card_action"
        ) | {
            "context": {},
            "domain": [("campaign_id", "=", self.id)],
        }

    def action_view_cards_clicked(self):
        self.check_singleton()
        return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_card.cards_card_action"
        ) | {
            "context": {"search_default_filter_visited": True},
            "domain": [("campaign_id", "=", self.id)],
        }

    def action_view_cards_shared(self):
        self.check_singleton()
        return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_card.cards_card_action"
        ) | {
            "context": {"search_default_filter_shared": True},
            "domain": [("campaign_id", "=", self.id)],
        }

    def action_view_mailings(self):
        self.check_singleton()
        return {
            "name": self.env._(
                "%(card_campaign_name)s Mailings", card_campaign_name=self.name
            ),
            "type": "ir.actions.act_window",
            "res_model": "mailing.mailing",
            "domain": [("card_campaign_id", "=", self.id)],
            "view_mode": "list,form",
            "target": "current",
        }

    def action_preview(self):
        self.check_singleton()
        card = self._acquire_preview_card()
        return {
            "type": "ir.actions.act_url",
            "url": card._get_path("preview"),
            "target": "new",
        }

    def action_share(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Send Cards"),
            "res_model": "mailing.mailing",
            "context": {
                "create": False,
                "default_subject": self.name,
                "default_card_campaign_id": self.id,
                "default_mailing_model_id": self.env["ir.model"]._get_id(
                    self.res_model
                ),
                "default_body_arch": self._action_share_get_default_body(),
            },
            "views": [[False, "form"]],
            "target": "current",
        }

    def _acquire_preview_card(self) -> CardCard:
        self.check_singleton()
        card = (
            self.env["card.card"]
            .with_context(active_test=False)
            .search(
                [
                    ("campaign_id", "=", self.id),
                    ("res_id", "=", self.preview_record_ref.id),
                ]
            )
        )
        preview_values = {"image": self.image_preview, "active": False}
        if card:
            card.write(preview_values)
        else:
            card = self.env["card.card"].create(
                {
                    "campaign_id": self.id,
                    "res_id": self.preview_record_ref.id,
                    **preview_values,
                }
            )
        return card

    def _action_share_get_default_body(self) -> str:
        preview_card = self._acquire_preview_card() if self else self.env["card.card"]
        return f"""
<div class="o_layout oe_unremovable oe_unmovable o_empty_theme" data-name="Mailing">
<style id="design-element"></style>
<div class="container o_mail_wrapper o_mail_regular oe_unremovable">
<div class="row">
<div class="col o_mail_no_options o_mail_wrapper_td bg-white oe_structure o_editable theme_selection_done">

<div class="s_text_block o_mail_snippet_general pt24 pb24" style="padding-left: 15px; padding-right: 15px;" data-snippet="s_text_block" data-name="Text">
    <div class="container s_allow_columns">
        <p">{self.env._("Hello everyone")}</p>
        <p>{self.env._("Here's the link to advertise your participation.")}
        <br>{self.env._("Your help with this promotion would be greatly appreciated!")}</p>
        <p>{self.env._("Many thanks")}</p>
    </div>
</div>

<div class="s_call_to_share_card o_mail_snippet_general" style="padding-top: 10px; padding-bottom: 10px;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0">
        <tbody>
            <tr>
                <td align="center">
                    <a href="/cards/{preview_card.id or 0}/preview" style="padding-left: 3px !important; padding-right: 3px !important">
                        <img src="/web/image/card.campaign/{self.id or 0}/image_preview" alt="{self.env._("Card Preview")}" class="img-fluid" style="width: 540px;"
                            data-original-src="/web/image/card.campaign/{self.id or 0}/image_preview"/>
                    </a>
                </td>
            </tr>
        </tbody>
    </table>
</div>

</div></div></div></div>
"""


    def _get_image_b64(self, record):
        if not self.card_template_id.body:
            return ""

        image_bytes = self.env["ir.actions.report"]._render_html_to_image(
            [
                self._render_field(
                    "body_html", record.ids, add_context={"card_campaign": self}
                )[record.id]
            ],
            *TEMPLATE_DIMENSIONS,
        )[0]

        if image_bytes is None and not modules.module.current_test:
            raise exceptions.UserError(
                self.env._(
                    "An error occured while rendering a card for %(record_name)s. "
                    "Try again or check the server logs for more details.",
                    record_name=record.display_name,
                )
            )
        return image_bytes and base64.b64encode(image_bytes)


    def _update_cards(self, domain, auto_commit=False):
        self.check_singleton()
        TargetModel = self.env[self.res_model]
        res_ids = TargetModel.search(domain).ids
        cards = (
            self.env["card.card"]
            .with_context(active_test=False)
            .search_fetch(
                [
                    ("campaign_id", "=", self.id),
                    ("res_id", "in", res_ids),
                ],
                ["res_id", "requires_sync"],
            )
        )
        cards.active = True
        self.env["card.card"].create(
            [
                {"campaign_id": self.id, "res_id": res_id}
                for res_id in set(res_ids) - set(cards.mapped("res_id"))
            ]
        )

        updated_cards = self.env["card.card"]
        while cards := self.env["card.card"].search_fetch(
            [
                ("requires_sync", "=", True),
                ("campaign_id", "=", self.id),
                ("res_id", "in", res_ids),
            ],
            ["res_id"],
            limit=100,
        ):
            if auto_commit and updated_cards:
                self.env["ir.cron"]._commit_progress()
                self.env["card.card"].invalidate_model(["image"])
            TargetModelPrefetch = TargetModel.with_prefetch(cards.mapped("res_id"))
            for card in cards.filtered("requires_sync"):
                card.write(
                    {
                        "image": self._get_image_b64(
                            TargetModelPrefetch.browse(card.res_id)
                        ),
                        "requires_sync": False,
                        "active": True,
                    }
                )
            cards.flush_recordset()
            updated_cards += cards
        return updated_cards

    def _get_url_from_res_id(self, res_id, suffix="preview"):
        card = self.env["card.card"].search(
            [("campaign_id", "=", self.id), ("res_id", "=", res_id)]
        )
        return (card and card._get_path(suffix)) or self.target_url


    @api.depends("res_model")
    def _compute_render_model(self) -> None:
        for campaign in self:
            campaign.render_model = campaign.res_model

    def _prepare_card_element_vals(self, record) -> dict[str, Any]:
        self.check_singleton()
        result = {
            "image1": images[0]
            if (
                images := self.content_image1_path
                and self.content_image1_path in record
                and record.mapped(self.content_image1_path)
            )
            else False,
            "image2": images[0]
            if (
                images := self.content_image2_path
                and self.content_image2_path in record
                and record.mapped(self.content_image2_path)
            )
            else False,
        }
        campaign_text_element_fields = (
            ("header", "content_header", "content_header_dyn", "content_header_path"),
            (
                "sub_header",
                "content_sub_header",
                "content_sub_header_dyn",
                "content_sub_header_path",
            ),
            (
                "section",
                "content_section",
                "content_section_dyn",
                "content_section_path",
            ),
            (
                "sub_section1",
                "content_sub_section1",
                "content_sub_section1_dyn",
                "content_sub_section1_path",
            ),
            (
                "sub_section2",
                "content_sub_section2",
                "content_sub_section2_dyn",
                "content_sub_section2_path",
            ),
        )
        for el, text_field, dyn_field, path_field in campaign_text_element_fields:
            if not self[dyn_field]:
                result[el] = self[text_field]
            elif not (field_path := self[path_field]):
                result[el] = record
            else:
                fnames = field_path.split(".")
                try:
                    value = record
                    while fnames and (fname := fnames.pop(0)):
                        value.fetch([fname])
                        value = value[fname]
                    m = record.mapped(field_path)
                    result[el] = (m and m[0]) or False
                except AttributeError, ValueError:
                    result[el] = field_path
                if isinstance(result[el], (date, datetime)) and (
                    tz := record._mail_get_timezone()
                ):
                    result[el] = (
                        result[el]
                        .replace(tzinfo=UTC)
                        .astimezone(timezone(tz))
                        .replace(tzinfo=None)
                    )
        return result
