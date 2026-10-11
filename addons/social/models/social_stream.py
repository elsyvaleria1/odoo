import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SocialStream(models.Model):
    """ "social.streams are used to fill the 'Feed' view that allows users to follow the social.media activity
    based on their interest (a Facebook Page, a Twitter hashtag, ...).

    They use the social.media third party API to fetch the stream data and create social.stream.posts
    that are displayed on the Feed kanban view."""

    _name = "social.stream"
    _description = "Social Stream"
    _order = "sequence asc, id asc"

    name = fields.Char(
        string="Title",
        translate=True,
    )
    media_id = fields.Many2one(
        comodel_name="social.media",
        string="Social Media",
        required=True,
    )
    media_image = fields.Binary(
        related="media_id.image",
        string="The related Social Media's image",
    )
    sequence = fields.Integer(
        help="Sequence used to order streams (mainly for the 'Feed' kanban view)"
    )
    account_id = fields.Many2one(
        comodel_name="social.account",
        string="Social Account",
        required=True,
        ondelete="cascade",
    )
    stream_type_id = fields.Many2one(
        comodel_name="social.stream.type",
        string="Type",
        required=True,
        ondelete="cascade",
    )
    stream_type_type = fields.Char(related="stream_type_id.stream_type")
    stream_post_ids = fields.One2many(
        comodel_name="social.stream.post",
        inverse_name="stream_id",
        string="Posts",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="account_id.company_id",
        string="Company",
    )

    @api.onchange("media_id", "account_id")
    def _onchange_media_id(self) -> None:
        for stream in self:
            if stream.account_id and stream.account_id.media_id != stream.media_id:
                stream.account_id = False
            stream_type_ids = self.env["social.stream.type"].search(
                [("media_id", "=", stream.media_id.id)], limit=2
            )
            stream.stream_type_id = (
                stream_type_ids.id if len(stream_type_ids) == 1 else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res._apply_default_name()
        for stream in res:
            stream._sync_stream_data()
        return res

    @api.model
    def refresh_all(self):

        new_content = False
        for stream in self.env["social.stream"].search([]):
            try:
                new_content |= stream._sync_stream_data()
            except requests.exceptions.ConnectionError, requests.exceptions.Timeout:
                _logger.warning("Failed to fetch %s data.", stream.name, exc_info=True)

        return new_content

    def _sync_stream_data(self):

        self.check_singleton()

    def _apply_default_name(self) -> None:
        for stream in self:
            stream.write({"name": stream.stream_type_id.name})
