from typing import Any

from odoo import api, fields, models
from odoo.db.schema import column_exists
from odoo.fields import Domain
from odoo.libs.documents import CUES
from odoo.tools import SQL, plaintext2html

from odoo.addons.mail.tools.discuss import Store
from odoo.addons.phone_call.models.phone_call import number_key

# the transcript and summary columns of upstream's AI call features
RETIRED_COLUMNS = ("transcript", "transcription_status", "summary")


class PhoneCall(models.Model):
    _name = "phone.call"
    _inherit = ["phone.call", "mixin.voip.country.code"]

    is_within_same_company = fields.Boolean(
        compute="_compute_is_within_same_company",
        store=True,
    )
    # Since activities are deleted from the database once marked as done, the
    # activity name is saved here in order to be preserved.
    activity_name = fields.Char(
        help="The name of the activity related to this phone call, if any."
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        compute="_compute_country_id",
        store=True,
    )
    country_flag_url = fields.Char(
        related="country_id.image_url",
        string="Country Flag",
    )
    image_1920 = fields.Binary(related="partner_id.image_1920")
    avatar_128 = fields.Binary(related="partner_id.avatar_128")

    @api.depends("activity_name")
    def _compute_display_name(self):
        super()._compute_display_name()
        for call in self.filtered("activity_name"):
            call.display_name = call.activity_name

    @api.depends(
        "partner_id.commercial_partner_id", "user_id.partner_id.commercial_partner_id"
    )
    def _compute_is_within_same_company(self) -> None:
        for call in self:
            user_company = call.user_id.partner_id.commercial_partner_id
            partner_company = call.partner_id.commercial_partner_id
            call.is_within_same_company = (
                user_company and user_company == partner_company
            )

    @api.depends("country_code_from_phone")
    def _compute_country_id(self) -> None:
        country_codes = set()
        for call in self:
            code = call.country_code_from_phone
            if code:
                country_codes.add(code.upper())
        countries = self.env["res.country"].search_read(
            [("code", "in", list(country_codes))],
            fields=["id", "code"],
        )
        country_id_by_iso_code = {
            country["code"].lower(): country["id"] for country in countries
        }

        for call in self:
            call.country_id = country_id_by_iso_code.get(
                call.country_code_from_phone, False
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_send_notification(self) -> None:
        for partner, calls in self.grouped(lambda c: c.user_id.partner_id).items():
            self.env["bus.bus"]._sendone(
                partner,
                "phone.call/delete",
                {"ids": calls.ids},
            )

    @api.model
    def create_and_format(
        self,
        phone_number: str | None = None,
        partner_id: int | None = None,
        direction: str = "outgoing",
        res_id: int | None = None,
        res_model: str | None = None,
    ) -> dict:
        """Creates a call from the provided values and returns it formatted for
        use in JavaScript. If a record is provided via its id and model,
        introspects it for a recipient.

        :param phone_number: The phone number to call
        :param partner_id: ID of the partner related to this call
        :param direction: Direction of the call ('incoming' or 'outgoing')
        :param res_id: Optional record ID to extract partner from
        :param res_model: Optional model name to extract partner from
        :return: Dictionary with created call IDs and formatted data
        """
        self.check_access("read")
        values = {
            "phone_number": phone_number,
            "partner_id": partner_id,
            "direction": direction,
            "state": "calling",
            "user_id": self.env.uid,
            "channel": "softphone",
        }
        if res_id and res_model:
            related_record = self.env[res_model].browse(res_id)
            related_record.check_access("read")
            values["partner_id"] = next(
                iter(
                    related_record._mail_get_partners(introspect_fields=True)[
                        related_record.id
                    ]
                ),
                self.env["res.partner"],
            ).id
        calls = self.sudo().create(values).sudo(False)
        return {
            "ids": [call.id for call in calls],
            "store_data": Store()
            .add(calls, calls._get_fields_voip_store())
            .get_result(),
        }

    @api.model
    def get_recent_phone_calls(
        self, search_terms: str | None = None, offset: int = 0, limit: int | None = None
    ):
        domain = Domain("user_id", "=", self.env.uid)
        if search_terms:
            search_fields = ["phone_number", "partner_id.name", "activity_name"]
            domain &= Domain.OR(
                [Domain(field, "ilike", search_terms) for field in search_fields]
            )
        calls = self.search(
            domain, offset=offset, limit=limit, order="create_date DESC"
        )
        return Store().add(calls, calls._get_fields_voip_store()).get_result()

    @api.model
    def _get_number_of_missed_calls(self) -> int:
        domain = [("user_id", "=", self.env.uid), ("state", "=", "missed")]
        last_seen_phone_call = self.env.user.last_seen_phone_call
        if last_seen_phone_call:
            domain += [("id", ">", last_seen_phone_call.id)]
        return self.search_count(domain)

    def abort_call(self):
        self.check_access("read")
        self.sudo().state = "aborted"
        return Store().add(self, self._get_fields_voip_store()).get_result()

    def start_call(self):
        self.check_access("read")
        calls_sudo = self.sudo()
        calls_sudo.start_date = fields.Datetime.now()
        calls_sudo.state = "ongoing"
        return Store().add(self, self._get_fields_voip_store()).get_result()

    def end_call(self, activity_name: str | None = None):
        self.check_access("read")
        calls_sudo = self.sudo()
        calls_sudo.end_date = fields.Datetime.now()
        calls_sudo.state = "terminated"
        if activity_name:
            calls_sudo.activity_name = activity_name
        return Store().add(self, self._get_fields_voip_store()).get_result()

    def reject_call(self):
        self.check_access("read")
        self.sudo().state = "rejected"
        return Store().add(self, self._get_fields_voip_store()).get_result()

    def miss_call(self):
        self.check_access("read")
        self.sudo().state = "missed"
        return Store().add(self, self._get_fields_voip_store()).get_result()

    def acquire_contact_info(self) -> dict[str, Any] | None:
        self.check_singleton()
        number = self.phone_number or ""
        partner = self.env["res.partner"]
        if number_key(number):
            partner = partner.browse(
                self._match_partners([number], self.company_id).get(
                    number_key(number), ()
                )
            )
        elif number:
            # an internal extension is a few digits a contact may still carry
            partner = partner.search([("phone_ids.number", "=", number)], limit=1)
        if not partner and number:
            partner = (
                self.env["res.users.settings"]
                .sudo()
                .search([("voip_username", "=", number)], limit=1)
                .user_id.partner_id.sudo(False)
            )
        if not partner:
            return None
        self.check_access("read")
        self.sudo().partner_id = partner
        return Store().add(self, self._get_fields_voip_store()).get_result()

    def _get_fields_voip_store(self) -> list:
        return [
            "create_date",
            "direction",
            "display_name",
            "end_date",
            Store.One("partner_id", self.partner_id._voip_get_store_fields()),
            Store.One(
                "phone_country_id", self.phone_country_id._voip_get_store_fields()
            ),
            "phone_number",
            "start_date",
            "state",
        ]

    def _voip_get_phone_char_fields(self) -> list:
        return ["phone_number"]

    @api.model
    def _absorb_retired_transcripts(self) -> None:
        cr = self.env.cr
        present = [c for c in RETIRED_COLUMNS if column_exists(cr, "phone_call", c)]
        if not present:
            return

        def column(name):
            return SQL.identifier(name) if name in present else SQL("NULL")

        cr.execute(
            SQL(
                "SELECT id, %(text)s, %(gist)s FROM phone_call"
                " WHERE COALESCE(%(text)s, '') != '' OR COALESCE(%(gist)s, '') != ''",
                text=column("transcript"),
                gist=column("summary"),
            )
        )
        for call_id, text, gist in cr.fetchall():
            call = self.browse(call_id).sudo()
            if text and not call._file_retired_transcript(text):
                call.message_post(
                    body=self.env._(
                        "Transcript kept from before recordings were transcribed:"
                    )
                    + plaintext2html(text),
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
            if gist:
                call.message_post(
                    body=self.env._("Summary: %s", gist),
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
        for name in present:
            cr.execute(
                SQL("ALTER TABLE phone_call DROP COLUMN %s", SQL.identifier(name))
            )

    def _file_retired_transcript(self, text: str) -> bool:
        self.check_singleton()
        if self.segment_ids:
            return False
        recording = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("mimetype", "=like", "audio/%"),
                ],
                order="create_date desc",
                limit=1,
            )
        )
        if not recording:
            return False
        seconds = max((self.duration or 0.0) * 3600, 0.001)
        self._add_media_segment(recording, 0, max(int(seconds * 1000), 1))
        cues = [
            {
                "start": 0.0,
                "end": seconds,
                "text": text,
                "speaker": "",
                "confidence": 0.0,
            }
        ]
        recording._store_reading(CUES, cues, read_by="voip_ai", announce=False)
        return True
