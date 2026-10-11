from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict

NUMBER_KEY_DIGITS = 10
NUMBER_KEY_MIN_DIGITS = 7


def number_key(number) -> str:
    digits = "".join(character for character in number or "" if character.isdigit())
    return digits[-NUMBER_KEY_DIGITS:] if len(digits) >= NUMBER_KEY_MIN_DIGITS else ""


class PhoneCall(models.Model):
    _name = "phone.call"
    _inherit = ["mixin.mail.thread.main.attachment", "mixin.media.timeline"]
    _description = "Phone call"
    _order = "create_date desc, id desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
            "owner": "user_id",
        }
    )

    phone_number = fields.Char(
        index=True,
        readonly=True,
        help="The other party's number, as the line reported it. Empty when the "
        "line named the call after a contact instead.",
    )
    contact_name = fields.Char(
        readonly=True,
        help="The other party's name as the line or the handset knew it",
    )
    channel = fields.Selection(
        selection=[
            ("softphone", "Softphone"),
            ("pbx", "Phone system"),
            ("mobile", "Company phone"),
        ],
        index=True,
        readonly=True,
        help="What carried the call: the browser softphone, the phone system "
        "behind the company's numbers, or a company handset's own line",
    )
    direction = fields.Selection(
        selection=[
            ("incoming", "Incoming"),
            ("outgoing", "Outgoing"),
        ],
        default="outgoing",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("aborted", "Aborted"),
            ("calling", "Calling"),
            ("missed", "Missed"),
            ("ongoing", "Ongoing"),
            ("rejected", "Rejected"),
            ("terminated", "Terminated"),
            ("voicemail", "Voicemail"),
            ("blocked", "Blocked"),
            ("unknown", "Unknown"),
        ],
        default="calling",
        index=True,
        readonly=True,
    )
    start_date = fields.Datetime(readonly=True)
    end_date = fields.Datetime(readonly=True)
    duration = fields.Float(
        compute="_compute_duration",
        readonly=True,
        help="Talk time in hours, from the call's start to its end",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
        index=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.uid,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        required=True,
        help="The company whose line carried the call; without a line, the "
        "responsible user's",
    )
    call_count = fields.Integer(
        compute="_compute_call_count",
        help="The total number of calls made to the same phone number.",
    )

    @api.depends("user_id")
    def _compute_company_id(self) -> None:
        active = self.env.company
        for call in self:
            if call.company_id:
                continue
            user = call.user_id
            if not user or active in user.company_ids:
                call.company_id = active
            else:
                call.company_id = user.company_id

    @api.depends("partner_id", "phone_number")
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_call_count(self) -> None:
        numbers = {number for number in self.mapped("phone_number") if number}
        partners = self.partner_id
        if not numbers and not partners:
            self.call_count = 1
            return
        related = self.search_fetch(
            Domain("phone_number", "in", list(numbers))
            | Domain("partner_id", "in", partners.ids),
            ["phone_number", "partner_id"],
        )
        for call in self:
            call.call_count = (
                len(
                    related.filtered(
                        lambda other, call=call: (
                            (
                                call.phone_number
                                and other.phone_number == call.phone_number
                            )
                            or (call.partner_id and other.partner_id == call.partner_id)
                        )
                    )
                    | call
                )
                if call.id
                else 1
            )

    @api.depends(
        "state", "direction", "phone_number", "contact_name", "partner_id.name"
    )
    def _compute_display_name(self):
        for call in self:
            call.display_name = call._call_name()

    def _call_name(self) -> str:
        self.check_singleton()
        number = self.phone_number or self.contact_name or self.env._("unknown number")
        if self.state == "aborted":
            return self.env._("Aborted call to %(phone_number)s", phone_number=number)
        if self.state == "missed":
            return self.env._("Missed call from %(phone_number)s", phone_number=number)
        if self.state == "voicemail":
            return self.env._("Voicemail from %(phone_number)s", phone_number=number)
        if self.state == "blocked":
            return self.env._("Blocked call from %(phone_number)s", phone_number=number)
        if self.state == "rejected":
            if self.direction == "incoming":
                return self.env._(
                    "Rejected call from %(phone_number)s", phone_number=number
                )
            return self.env._("Rejected call to %(phone_number)s", phone_number=number)
        who = self.partner_id.name or self.contact_name
        if self.direction == "incoming":
            if who:
                return self.env._("Call from %(correspondent)s", correspondent=who)
            return self.env._("Call from %(phone_number)s", phone_number=number)
        if self.direction == "outgoing":
            if who:
                return self.env._("Call to %(correspondent)s", correspondent=who)
            return self.env._("Call to %(phone_number)s", phone_number=number)
        return self.env._("Call with %(correspondent)s", correspondent=who or number)

    @api.depends("start_date", "end_date")
    def _compute_duration(self):
        for call in self:
            if call.start_date and call.end_date:
                call.duration = (call.end_date - call.start_date).total_seconds() / 3600
            else:
                call.duration = 0

    def _recording_timeline(self):
        self.check_singleton()
        return self

    def _on_call_details_completed(self) -> None:
        pass

    def _on_merged_into(self, call) -> None:
        pass

    def _file_recording(self, attachment, start_ms=None, end_ms=None, *, eta=None):
        self.check_singleton()
        return self._recording_timeline()._file_media(
            attachment, start_ms, end_ms, eta=eta
        )

    @api.model
    def _match_partners(self, numbers, company) -> dict:
        keys = {key for key in map(number_key, numbers) if key}
        if not keys:
            return {}
        company_ids = {company.id, False}
        matches = {}
        digits = Domain.OR([Domain("sanitized", "=like", f"%{key}") for key in keys])
        phones = (
            self.env["phone.number"]
            .sudo()
            .search(digits & Domain("partner_ids", "!=", False))
        )
        for phone in phones:
            key = number_key(phone.sanitized)
            partners = phone.partner_ids.filtered(
                lambda partner: partner.company_id.id in company_ids
            )
            if key in keys and partners:
                matches.setdefault(key, partners[0].id)
        return matches

    def action_view_calls(self) -> dict:
        self.check_singleton()
        domain = Domain("id", "=", self.id)
        if self.phone_number:
            domain |= Domain("phone_number", "=", self.phone_number)
        if self.partner_id:
            domain |= Domain("partner_id", "=", self.partner_id)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Calls"),
            "res_model": "phone.call",
            "view_mode": "list,form",
            "domain": domain,
        }
