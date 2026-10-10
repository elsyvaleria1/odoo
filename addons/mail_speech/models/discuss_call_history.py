from odoo import fields, models


class DiscussCallHistory(models.Model):
    _name = "discuss.call.history"
    _inherit = ["discuss.call.history", "mixin.media.timeline"]

    recorder_session_id = fields.Many2one(
        comodel_name="discuss.channel.rtc.session",
        copy=False,
        readonly=True,
        ondelete="set null",
        help="The participant whose browser is recording this call; leaving the "
        "call releases it.",
    )
    recording_offset_ms = fields.Integer(
        copy=False,
        readonly=True,
        help="Where the current recording starts in this call's timeline: the "
        "recorder counts from zero, the timeline does not.",
    )
