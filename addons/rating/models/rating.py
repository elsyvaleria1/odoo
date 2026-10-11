import base64

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools.misc import file_open

from odoo.addons.rating.models import rating_data


class RatingRating(models.Model):
    _name = "rating.rating"
    _description = "Rating"
    _order = "write_date desc, id desc"
    _rec_name = "res_name"

    @api.model
    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env["ir.model"].sudo().search([])
        ]

    create_date = fields.Datetime(string="Submitted on")
    res_name = fields.Char(
        string="Resource name",
        compute="_compute_res_name",
        store=True,
    )
    res_model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Related Document Model",
        index=True,
        ondelete="cascade",
    )
    res_model = fields.Char(
        related="res_model_id.model",
        string="Document Model",
        store=True,
        index=True,
        readonly=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Document",
        index=True,
        required=True,
    )
    resource_ref = fields.Reference(
        selection="_selection_target_model",
        compute="_compute_resource_ref",
        readonly=True,
    )
    parent_res_name = fields.Char(
        string="Parent Document Name",
        compute="_compute_parent_res_name",
        store=True,
    )
    parent_res_model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Parent Related Document Model",
        index=True,
        ondelete="cascade",
    )
    parent_res_model = fields.Char(
        related="parent_res_model_id.model",
        string="Parent Document Model",
        store=True,
        index=True,
    )
    parent_res_id = fields.Integer(
        string="Parent Document",
        index=True,
    )
    parent_ref = fields.Reference(
        selection="_selection_target_model",
        compute="_compute_parent_ref",
        readonly=True,
    )
    rated_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Rated Operator",
    )
    rated_partner_name = fields.Char(related="rated_partner_id.name")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
    )
    rating = fields.Float(
        string="Rating Value",
        default=0,
        aggregator="avg",
    )
    rating_image = fields.Binary(
        string="Image",
        compute="_compute_rating_images",
    )
    rating_image_url = fields.Char(
        string="Image URL",
        compute="_compute_rating_images",
    )
    rating_text = fields.Selection(
        selection=rating_data.RATING_TEXT,
        string="Rating",
        compute="_compute_rating_text",
        store=True,
        readonly=True,
    )
    feedback = fields.Text(string="Comment")
    message_id = fields.Many2one(
        comodel_name="mail.message",
        index=True,
        ondelete="cascade",
    )
    is_internal = fields.Boolean(
        related="message_id.is_internal",
        string="Visible Internally Only",
        readonly=False,
    )
    access_token = fields.Char(
        string="Security Token",
        compute="_compute_access_token",
        help="The token of the link the customer rates with; the link is an "
        "access.link row holding its hash.",
    )
    consumed = fields.Boolean(string="Filled Rating")
    rated_on = fields.Datetime()

    _rating_range = models.Constraint(
        "check(rating >= 0 and rating <= 5)",
        "Rating should be between 0 and 5",
    )

    _consumed_idx = models.Index(
        "(res_model, res_id, write_date) WHERE consumed IS TRUE"
    )
    _parent_consumed_idx = models.Index(
        "(parent_res_model, parent_res_id, write_date) WHERE consumed IS TRUE"
    )

    @api.depends("res_model", "res_id")
    def _compute_res_name(self) -> None:
        for rating in self:
            if rating.res_model and rating.res_id:
                name = (
                    self.env[rating.res_model].sudo().browse(rating.res_id).display_name
                )
            else:
                name = False
            rating.res_name = name or f"{rating.res_model}/{rating.res_id}"

    @api.depends("res_model", "res_id")
    def _compute_resource_ref(self) -> None:
        for rating in self:
            if rating.res_model and rating.res_model in self.env:
                rating.resource_ref = "%s,%s" % (rating.res_model, rating.res_id or 0)
            else:
                rating.resource_ref = None

    @api.depends("parent_res_model", "parent_res_id")
    def _compute_parent_ref(self) -> None:
        for rating in self:
            if rating.parent_res_model and rating.parent_res_model in self.env:
                rating.parent_ref = "%s,%s" % (
                    rating.parent_res_model,
                    rating.parent_res_id or 0,
                )
            else:
                rating.parent_ref = None

    @api.depends("parent_res_model", "parent_res_id")
    def _compute_parent_res_name(self) -> None:
        for rating in self:
            name = False
            if rating.parent_res_model and rating.parent_res_id:
                name = (
                    self.env[rating.parent_res_model]
                    .sudo()
                    .browse(rating.parent_res_id)
                    .display_name
                )
                name = name or f"{rating.parent_res_model}/{rating.parent_res_id}"
            rating.parent_res_name = name

    def _get_rating_image_filename(self) -> str:
        self.check_singleton()
        return "rating_%s.png" % rating_data._rating_to_threshold(self.rating)

    @api.depends("rating")
    def _compute_rating_images(self) -> None:
        self.rating_image_url = False
        self.rating_image = False
        for rating in self:
            image_path = f"rating/static/src/img/{rating._get_rating_image_filename()}"
            rating.rating_image_url = f"/{image_path}"
            try:
                with file_open(image_path, "rb", filter_ext=(".png",)) as f:
                    rating.rating_image = base64.b64encode(f.read())
            except OSError:
                rating.rating_image = False

    @api.depends("rating")
    def _compute_rating_text(self) -> None:
        for rating in self:
            rating.rating_text = rating_data._rating_to_text(rating.rating)


    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("res_model_id") and values.get("res_id"):
                values.update(self._get_parent_data(values))
            if "rating" in values or "feedback" in values:
                values["rated_on"] = fields.Datetime.now()
        ratings = super().create(vals_list)
        for rating in ratings.filtered(lambda rating: not rating.consumed):
            rating._issue_link()
        return ratings

    def _compute_access_token(self) -> None:
        links = (
            self.env["access.link"]
            ._record_links(
                self.filtered("id"),
                Domain("cause", "in", ("notification", "migration"))
                & Domain("audience", "=", "anyone"),
            )
            .sorted("id", reverse=True)
        )
        shown = links._tokens()
        tokens = {}
        for link in links:
            if link.res_id not in tokens and link.id in shown:
                tokens[link.res_id] = shown[link.id]
        for rating in self:
            rating.access_token = tokens.get(rating.id, False)

    def _issue_link(self) -> str:
        self.check_singleton()
        __, token = self.env["access.link"]._issue(
            self, partner=self.partner_id, role="comment", cause="notification"
        )
        self._update_cache({"access_token": token}, validate=False)
        return token

    def write(self, vals):
        if vals.get("res_model_id") and vals.get("res_id"):
            vals.update(self._get_parent_data(vals))
        if "rating" in vals or "feedback" in vals:
            vals["rated_on"] = fields.Datetime.now()
        return super().write(vals)

    def _is_open_through_link(self) -> bool:
        self.check_singleton()
        if not self.consumed:
            return True
        given = self.message_id.create_date or self.rated_on or self.write_date
        return fields.Datetime.now() < given + rating_data.RATING_CHANGE_WINDOW

    def unlink(self):
        self.env["mail.message"].search([("rating_ids", "in", self.ids)]).unlink()
        return super().unlink()

    def _get_parent_data(self, values):
        current_model_name = (
            self.env["ir.model"].sudo().browse(values["res_model_id"]).model
        )
        current_record = self.env[current_model_name].browse(values["res_id"])
        data = {
            "parent_res_model_id": False,
            "parent_res_id": False,
        }
        if hasattr(current_record, "_rating_get_parent_field_name"):
            current_record_parent = current_record._rating_get_parent_field_name()
            if current_record_parent:
                parent_res_model = getattr(current_record, current_record_parent)
                data["parent_res_model_id"] = (
                    self.env["ir.model"]
                    ._get(parent_res_model._get_reference_model_name())
                    .id
                )
                data["parent_res_id"] = parent_res_model.id
        return data


    def action_view_rated_object(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [[False, "form"]],
        }


    def _classify_by_model(self):
        data_by_model = {}
        for rating in self.filtered(lambda act: act.res_model and act.res_id):
            if rating.res_model not in data_by_model:
                data_by_model[rating.res_model] = {
                    "ratings": self.env["rating.rating"],
                    "record_ids": [],
                }
            data_by_model[rating.res_model]["ratings"] += rating
            data_by_model[rating.res_model]["record_ids"].append(rating.res_id)
        return data_by_model

    def _to_store_defaults(self, target):
        return ["rating", "rating_image_url", "rating_text"]
