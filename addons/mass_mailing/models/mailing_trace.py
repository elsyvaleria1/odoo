from odoo import api, fields, models

from odoo.addons.mail.tools.failure_type import DELIVERY_FAILURE_TYPES


class MailingTrace(models.Model):

    _name = "mailing.trace"
    _description = "Mailing Statistics"
    _rec_name = "id"
    _order = "create_date DESC"

    trace_type = fields.Selection(
        selection=[("mail", "Email")],
        string="Type",
        default="mail",
        required=True,
    )
    is_test_trace = fields.Boolean(string="Generated for testing")
    mail_mail_id = fields.Many2one(
        comodel_name="mail.mail",
        string="Mail",
        index="btree_not_null",
    )
    mail_mail_id_int = fields.Integer(
        string="Mail ID (tech)",
        index="btree_not_null",
        help="ID of the related mail_mail. This field is an integer field because "
        "the related mail_mail can be deleted separately from its statistics. "
        "However the ID is needed for several action and controllers.",
    )
    email = fields.Char(help="Normalized email address")
    message_id = fields.Char(string="Message-ID")
    medium_id = fields.Many2one(related="mass_mailing_id.medium_id")
    source_id = fields.Many2one(related="mass_mailing_id.source_id")
    model = fields.Char(
        string="Document model",
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="model",
        string="Document ID",
    )
    mass_mailing_id = fields.Many2one(
        comodel_name="mailing.mailing",
        string="Mailing",
        index=True,
        ondelete="cascade",
    )
    campaign_id = fields.Many2one(
        related="mass_mailing_id.campaign_id",
        string="Campaign",
        readonly=True,
    )
    sent_datetime = fields.Datetime(string="Sent On")
    open_datetime = fields.Datetime(string="Opened On")
    reply_datetime = fields.Datetime(string="Replied On")
    trace_status = fields.Selection(
        selection=[
            ("outgoing", "Outgoing"),
            ("process", "Processing"),
            ("pending", "Sent"),
            ("sent", "Delivered"),
            ("open", "Opened"),
            ("reply", "Replied"),
            ("bounce", "Bounced"),
            ("error", "Exception"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="outgoing",
    )
    failure_type = fields.Selection(
        selection=DELIVERY_FAILURE_TYPES,
        string="Failure type",
    )
    failure_reason = fields.Text(
        string="Failure reason",
        copy=False,
        readonly=True,
    )
    links_click_ids = fields.One2many(
        comodel_name="link.tracker.click",
        inverse_name="mailing_trace_id",
        string="Links click",
    )
    links_click_datetime = fields.Datetime(
        string="Clicked On",
        help="Stores last click datetime in case of multi clicks.",
    )

    _check_res_id_is_set = models.Constraint(
        "CHECK(res_id IS NOT NULL AND res_id !=0 )",
        "Traces have to be linked to records with a not null res_id.",
    )

    @api.depends("trace_type", "mass_mailing_id")
    def _compute_display_name(self):
        for trace in self:
            trace.display_name = (
                f"{trace.trace_type}: {trace.mass_mailing_id.name} ({trace.id})"
            )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "mail_mail_id" in values:
                values["mail_mail_id_int"] = values["mail_mail_id"]
        return super().create(vals_list)

    def action_view_contact(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self.model,
            "target": "current",
            "res_id": self.res_id,
        }

    def set_sent(self, domain=None):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.write(
            {
                "trace_status": "sent",
                "sent_datetime": fields.Datetime.now(),
                "failure_type": False,
            }
        )
        return traces

    def set_opened(self, domain=None):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.filtered(lambda t: t.trace_status not in ("open", "reply")).write(
            {"trace_status": "open", "open_datetime": fields.Datetime.now()}
        )
        return traces

    def set_clicked(self, domain=None):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.write({"links_click_datetime": fields.Datetime.now()})
        return traces

    def set_replied(self, domain=None):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.write({"trace_status": "reply", "reply_datetime": fields.Datetime.now()})
        return traces

    def set_bounced(self, domain=None, bounce_message=False):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.write(
            {
                "failure_reason": bounce_message,
                "failure_type": "mail_bounce",
                "trace_status": "bounce",
            }
        )
        return traces

    def set_failed(self, domain=None, failure_type=False):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.write({"trace_status": "error", "failure_type": failure_type})
        return traces

    def set_canceled(self, domain=None):
        traces = self + (self.search(domain) if domain else self.env["mailing.trace"])
        traces.write({"trace_status": "cancel"})
        return traces
