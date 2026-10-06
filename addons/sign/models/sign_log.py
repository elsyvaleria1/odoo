import base64
import logging
from hashlib import sha256
from json import dumps

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import frozendict

_logger = logging.getLogger(__name__)

# 1: the creation entry hashes the text of the first document's base64 only.
# 2: the creation entry hashes every document, and a completion entry hashes the
#    signed PDFs delivered; each keeps the per-file digests it was computed from.
HASH_VERSION = 2
CHAINED_ACTIONS = ("create", "sign", "complete")

# version 2 binds who acted by the user and the signer row, which merging
# duplicate contacts leaves alone, not by the contact it rewrites
HASHED_FIELDS = [
    "log_date",
    "action",
    "request_state",
    "latitude",
    "longitude",
    "ip",
    "user_id",
    "sign_request_item_id",
]

LOG_FIELDS = [
    "log_date",
    "action",
    "partner_id",
    "request_state",
    "latitude",
    "longitude",
    "ip",
]


class SignLog(models.Model):
    _name = "sign.log"
    _order = "log_date, id"
    _description = "Sign requests access history"
    _access_anchors = frozendict(
        {
            "owner": "sign_request_id.create_uid",
            "partner": "sign_request_id.request_item_ids.partner_id",
        }
    )

    # Accessed on ?
    log_date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    sign_request_id = fields.Many2one(
        comodel_name="sign.request",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sign_request_item_id = fields.Many2one(comodel_name="sign.request.item")
    # Accessed as ?
    user_id = fields.Many2one(
        comodel_name="res.users",
        groups="sign.group_sign_manager",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
    )

    # Accessed from ?
    # If defined on request item when signing: take from it
    # Else : taken from geoip
    latitude = fields.Float(
        digits=(10, 7),
        groups="sign.group_sign_manager",
    )
    longitude = fields.Float(
        digits=(10, 7),
        groups="sign.group_sign_manager",
    )
    ip = fields.Char(
        string="IP address of the visitor",
        required=True,
        groups="sign.group_sign_manager",
    )
    log_hash = fields.Char(
        string="Inalterability Hash",
        copy=False,
        readonly=True,
    )
    hash_version = fields.Integer(
        default=HASH_VERSION,
        copy=False,
        readonly=True,
    )
    digests = fields.Json(
        string="File Digests",
        copy=False,
        readonly=True,
        help="SHA-256 of each file a creation or completion entry covers, in "
        "document order, as the entry's hash was computed from them.",
    )
    declared_name = fields.Char(
        readonly=True,
        help="The name a visitor without an account gave when refusing a shared "
        "request; not verified.",
    )
    declared_email = fields.Char(
        readonly=True,
        help="The email a visitor without an account gave when refusing a shared "
        "request; not verified.",
    )

    # Accessed for ?
    action = fields.Selection(
        selection=[
            ("create", "Creation"),
            ("open", "View/Download"),
            ("save", "Save"),
            ("sign", "Signature"),
            ("refuse", "Refuse"),
            ("cancel", "Cancel"),
            ("update_mail", "Mail Update"),
            ("update", "Update"),
            ("complete", "Completion"),
        ],
        string="Action Performed",
        required=True,
    )

    request_state = fields.Selection(
        selection=[
            ("shared", "Shared"),
            ("sent", "Before Signature"),
            ("signed", "After Signature"),
            ("refused", "Refused Signature"),
            ("canceled", "Cancelled"),
            ("expired", "Expired"),
        ],
        string="State of the request on action log",
        required=True,
        groups="sign.group_sign_manager",
    )

    def write(self, vals):
        if self:
            raise ValidationError(
                self.env._("Log history of sign requests cannot be modified!")
            )
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self) -> None:
        raise ValidationError(
            self.env._("Log history of sign requests cannot be deleted!")
        )

    @api.model_create_multi
    def create(self, vals_list):
        """
        1/ if action=='create': get initial shasign from template (checksum pdf)
        2/ if action == 'sign': search for logs with hash for the same request and use that to compute new hash
        """
        vals_list = [
            {**self.default_get(["sign_request_item_id"]), **vals} for vals in vals_list
        ]
        vals_list_request_item = [
            vals for vals in vals_list if vals.get("sign_request_item_id")
        ]
        sign_request_items = self.env["sign.request.item"].browse(
            [vals["sign_request_item_id"] for vals in vals_list_request_item]
        )
        vals_list_request = [
            vals
            for vals in vals_list
            if not vals.get("sign_request_item_id") and vals.get("sign_request_id")
        ]
        sign_requests = self.env["sign.request"].browse(
            [vals["sign_request_id"] for vals in vals_list_request]
        )
        for vals, sign_request_item in zip(
            vals_list_request_item, sign_request_items, strict=True
        ):
            vals |= self._prepare_vals_from_item(sign_request_item) | vals
        for vals, sign_request in zip(vals_list_request, sign_requests, strict=True):
            vals |= self._prepare_vals_from_request(sign_request) | vals
        if self.env.context.get("logged_user_id"):
            user_id = self.env.context["logged_user_id"]
        else:
            user_id = self.env.user.id if not self.env.user._is_public() else None

        ip = request.httprequest.remote_addr if request else "0.0.0.0"
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.update(
                {
                    "user_id": user_id,
                    "ip": ip,
                    "log_date": now,
                    "hash_version": HASH_VERSION,
                }
            )
            if vals["action"] in ("create", "complete"):
                vals["digests"] = self._get_file_digests(vals)
            vals["log_hash"] = self._get_or_check_hash(vals)
        return super().create(vals_list)

    def _get_file_digests(self, vals) -> list[str]:
        """SHA-256 of the files a creation (the template's documents) or a
        completion entry (the signed PDFs delivered) covers, in document order."""
        # the form view reads under bin_size, which turns binaries into sizes
        sign_request = (
            self.env["sign.request"]
            .with_context(bin_size=False, bin_size_raw=False, bin_size_file=False)
            .browse(vals["sign_request_id"])
        )
        if vals["action"] == "create":
            return [
                sha256(document.attachment_id.raw or b"").hexdigest()
                for document in sign_request.template_id.document_ids.sorted(
                    lambda document: (document.sequence, document.id)
                )
            ]
        return [
            sha256(base64.b64decode(completed.file or b"")).hexdigest()
            for completed in sign_request.completed_document_ids.sorted(
                lambda completed: (completed.document_id.sequence, completed.id)
            )
        ]

    def _get_or_check_hash(self, vals):
        """The chained hash of an entry: its previous chained entry's hash, then
        what the entry vouches for, as of the entry's hash version."""
        if vals["action"] not in CHAINED_ACTIONS:
            return False
        domain = [
            ("sign_request_id", "=", vals["sign_request_id"]),
            ("action", "in", CHAINED_ACTIONS),
        ]
        if "id" in vals:
            domain.append(("id", "<", vals["id"]))
        prev_activity = self.sudo().search(domain, limit=1, order="id desc")
        if (vals.get("hash_version") or 1) == 1:
            return self._get_legacy_hash(vals, prev_activity)
        return sha256(
            ((prev_activity.log_hash or "") + self._get_payload_to_hash(vals)).encode(
                "utf-8"
            )
        ).hexdigest()

    def _get_payload_to_hash(self, vals) -> str:
        """Version 2: what an entry vouches for -- its own facts (when, by which
        user for which signer, from where, in which state), then the values the
        signer filled for a signature, or the file digests for a creation or a
        completion."""
        payload = {field: str(vals.get(field) or False) for field in HASHED_FIELDS}
        # as stored: coordinates keep 7 decimals
        for field in ("latitude", "longitude"):
            payload[field] = f"{float(vals[field] or 0.0):.7f}"
        if vals["action"] == "sign":
            payload["values"] = {
                str(value.id): str(value.value)
                for value in self.env["sign.request.item.value"].search(
                    [("sign_request_item_id", "=", vals["sign_request_item_id"])]
                )
            }
        else:
            payload["files"] = vals["digests"]
        return dumps(payload, sort_keys=True, ensure_ascii=True, indent=None)

    def _get_legacy_hash(self, vals, prev_activity):
        """Version 1, kept so the entries written under it still verify."""
        # Multiple signers lead to multiple creation actions but for them, the hash of the PDF must be calculated.
        previous_hash = ""
        sign_request = not prev_activity and self.env["sign.request"].browse(
            vals["sign_request_id"]
        )
        if sign_request and sign_request.template_id.document_ids:
            body = (
                sign_request.template_id.document_ids[0]
                .with_context(bin_size=False)
                .attachment_id.datas
            )
        else:
            # ``prev_activity`` can be an empty recordset here (no previous
            # activity, and no document to hash either): reading a Char field
            # off an empty recordset returns ``False``, not "".
            previous_hash = prev_activity.log_hash or ""
            body = self._get_string_to_hash(vals)
        return sha256((previous_hash + str(body)).encode("utf-8")).hexdigest()

    def _get_string_to_hash(self, vals):
        """Version 1's payload of a signature entry, kept for the entries written
        under it."""
        values = {}
        for field in LOG_FIELDS:
            values[field] = str(vals[field])
        # Values are filtered by the signing item itself. Keying this on the item's
        # id (stable) rather than its access_token (which _cancel rotates) keeps the
        # hash reproducible after another signer refuses or the request is cancelled.
        item_values = self.env["sign.request.item.value"].search(
            [
                ("sign_request_id", "=", vals["sign_request_id"]),
                ("sign_request_item_id", "=", vals.get("sign_request_item_id")),
            ]
        )
        for item_value in item_values:
            values[str(item_value.id)] = str(item_value.value)
        return dumps(values, sort_keys=True, ensure_ascii=True, indent=None)

    def _get_hash_vals(self) -> dict:
        """The entry's stored values as its hash was computed from them."""
        self.check_singleton()
        return {
            key: value[0] if isinstance(value, tuple) else value
            for key, value in self.read()[0].items()
        } | {"digests": self.digests or []}

    def _get_integrity_error(self) -> str | None:
        """Why these entries no longer vouch for their request, or None: the
        first file that changed since an entry fingerprinted it, else the first
        entry whose chained hash no longer matches."""
        action_labels = dict(self._fields["action"]._description_selection(self.env))
        for log in self.filtered(lambda log: log.action in CHAINED_ACTIONS).sorted(
            "id"
        ):
            action = action_labels[log.action]
            vals = log._get_hash_vals()
            if log.hash_version >= 2 and log.action in ("create", "complete"):
                recorded_digests = log.digests or []
                current = self._get_file_digests(vals)
                for index, (recorded, now) in enumerate(
                    zip(recorded_digests, current, strict=False), start=1
                ):
                    if recorded != now:
                        return self.env._(
                            "File %(index)s changed after the %(action)s entry of %(date)s.",
                            index=index,
                            action=action,
                            date=log.log_date,
                        )
                if len(recorded_digests) != len(current):
                    return self.env._(
                        "Files were added or removed after the %(action)s entry of %(date)s.",
                        action=action,
                        date=log.log_date,
                    )
            if self._get_or_check_hash(vals) != log.log_hash:
                return self.env._(
                    "The %(action)s entry of %(date)s no longer matches its hash.",
                    action=action,
                    date=log.log_date,
                )
        return None

    def _prepare_vals_from_item(self, request_item) -> dict:
        sign_request = request_item.sign_request_id
        # NOTE: We update request_item.latitude/longitude when the request_item is opened and not 'completed'/'refused'
        # And If the signer accepted the browser geolocation request, the coordinates will be more precise.
        # We should forcely use the GeoIP ones only if the request_item is 'completed'/'refused'
        latitude = 0.0
        longitude = 0.0
        if request:
            latitude = (
                (request.geoip.location.latitude or 0.0)
                if request_item.state != "sent"
                else request_item.latitude
            )
            longitude = (
                (request.geoip.location.longitude or 0.0)
                if request_item.state != "sent"
                else request_item.longitude
            )
        return {
            "sign_request_item_id": request_item.id,
            "sign_request_id": sign_request.id,
            "request_state": sign_request.state,
            "latitude": latitude,
            "longitude": longitude,
            "partner_id": request_item.partner_id.id,
        }

    def _prepare_vals_from_request(self, sign_request) -> dict:
        return {
            "sign_request_id": sign_request.id,
            "request_state": sign_request.state,
            "latitude": (request.geoip.location.latitude or 0.0) if request else 0.0,
            "longitude": (request.geoip.location.longitude or 0.0) if request else 0.0,
            "partner_id": False
            if self.env.user._is_public()
            else self.env.user.partner_id.id,
        }
