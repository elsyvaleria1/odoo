from odoo import api, exceptions, fields, models


class RatingRating(models.Model):
    _inherit = "rating.rating"

    publisher_comment = fields.Text(string="Publisher comment")
    publisher_id = fields.Many2one(
        comodel_name="res.partner",
        string="Commented by",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )
    publisher_datetime = fields.Datetime(
        string="Commented on",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._prepare_publisher_values(values)
        ratings = super().create(vals_list)
        if any(rating.publisher_comment for rating in ratings):
            ratings._check_publisher_values()
        return ratings

    def write(self, vals):
        if vals.get("publisher_comment"):
            self._check_publisher_values()
        self._prepare_publisher_values(vals)
        return super().write(vals)

    def _check_publisher_values(self) -> None:
        editor_group = self.env["ir.model.data"]._xmlid_to_res_id(
            "website.group_website_restricted_editor"
        )
        if editor_group and self.env.user.has_group(
            "website.group_website_restricted_editor"
        ):
            return
        for model, model_data in self._classify_by_model().items():
            records = self.env[model].browse(model_data["record_ids"])
            try:
                records.check_access("write")
            except exceptions.AccessError as e:
                raise exceptions.AccessError(
                    self.env._(
                        "Updating rating comment require write access on related record"
                    )
                ) from e

    def _prepare_publisher_values(self, values):
        if values.get("publisher_comment"):
            if not values.get("publisher_datetime"):
                values["publisher_datetime"] = fields.Datetime.now()
            values["publisher_id"] = self.env.user.partner_id.id
        return values
