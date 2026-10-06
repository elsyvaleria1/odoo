import hashlib
import hmac
import re

from odoo import api, fields, models, tools
from odoo.fields import Domain
from odoo.http import request
from odoo.libs import redact
from odoo.libs.debug_log import DebugLog
from odoo.service.transaction import retrying

from odoo.addons.mail.tools.discuss import EMPTY_EDIT_MARKER
from odoo.addons.portal.utils import (
    is_thread_hash_pid_valid,
    is_thread_token_valid,
    resolve_thread_for_credentials,
)

# a link's signed `hash` lets whoever holds it post as its `pid`; a `hash`
# without a `pid` beside it (a translations cache key) is no signature
_SIGNED_QUERY = re.compile(r"[?#][^\s'\"<>#]*")
_SIGNATURE = re.compile(r"(?<=[?&#])(_?hash=)[^&#]+")
_PARTNER = re.compile(r"[?&#]pid=")


def _mask_link_signature(query: re.Match[str]) -> str:
    if not _PARTNER.search(query[0]):
        return query[0]
    return _SIGNATURE.sub(rf"\1{redact.MASK}", query[0])


redact.register_pattern(_SIGNED_QUERY, _mask_link_signature)

_debug = DebugLog(__name__)

PARTNER_HASH_SCOPE = tools.register_signed_scope(
    "portal.partner_hash",
    purpose="post, react and edit in a record's portal chatter as the partner "
    "`pid` a link was sent to, over the access token that link carries",
    lifetime="undated: it holds while the access token it signs opens the record",
)
# ir.config_parameter: whether a hash signed with the bare database secret, as
# every link sent before portal 1.6 carries, is still accepted, and the last day
# one was; ir.config_parameter._gc_portal_legacy_hash turns it off once idle
LEGACY_HASH_ENABLED = "portal.legacy_hash_enabled"
LEGACY_HASH_LAST_USED = "portal.legacy_hash_last_used"
LEGACY_HASH_IDLE_DAYS = 30


# the one place a bare-secret hash is accepted: delete it, its parameters, its
# privilege, ir.config_parameter._gc_portal_legacy_hash and migration 1.6 once
# the fallback has turned itself off on every database
def _legacy_hash_valid(record: models.Model, signature: str, signed: tuple) -> bool:
    env = record.env
    settings = env.registry.settings
    if not settings.get_bool(env, LEGACY_HASH_ENABLED):
        return False
    secret = settings.get(env, "database.secret")
    if not secret:
        return False
    legacy = hmac.new(secret.encode(), repr(signed).encode(), hashlib.sha256)
    if not tools.consteq(signature, legacy.hexdigest()):
        return False
    today = fields.Date.to_string(fields.Date.today())
    last_used = settings.get(env, LEGACY_HASH_LAST_USED)
    _debug.logic(
        "legacy_hash_accepted",
        model=record._name,
        record=record.id,
        pid=signed[2],
        last_used=last_used,
    )
    if last_used and last_used >= today:
        return True

    def record_use(use_env: api.Environment) -> None:
        use_env["ir.config_parameter"].with_privilege(
            "portal.privilege_track_legacy_hash",
            reason="a legacy portal link was used today",
        ).set_param(LEGACY_HASH_LAST_USED, today)

    if request:
        # once the request's cursor is back in the pool, on one of its own: a
        # read-only request cannot write, and a request is never retried over it
        registry, uid = env.registry, env.uid

        def record_use_after_release() -> None:
            with registry.cursor() as cr:
                use_env = api.Environment(cr, uid, {})
                retrying(lambda: record_use(use_env), use_env)

        request.call_after_release(record_use_after_release)
    elif env.cr.readonly:
        _debug.logic("legacy_hash_use_not_recorded", reason="readonly")
    else:
        record_use(env)
    return True


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    _mail_post_token_field = "access_token"

    website_message_ids = fields.One2many(
        comodel_name="mail.message",
        inverse_name="res_id",
        string="Portal Messages",
        domain=lambda self: [
            ("model", "=", self._get_reference_model_name()),
            (
                "message_type",
                "in",
                ("comment", "email", "email_outgoing", "auto_comment", "out_of_office"),
            ),
        ],
        bypass_search_access=True,
        help="Portal communication history for this record.",
    )

    def _get_domain_portal_message_fetch(self, message_domain=None):
        MailMessage = self.env["mail.message"]
        field = self._fields["website_message_ids"]
        if message_domain is None:
            message_domain = self._get_domain_portal_message_non_empty()
        return (
            Domain(field.get_comodel_domain(self))
            & Domain("res_id", "in", self.ids)
            & Domain(MailMessage._get_search_domain_share())
            & Domain(message_domain)
        )

    def _get_domain_portal_message_non_empty(self):
        return Domain("body", "not in", [False, EMPTY_EDIT_MARKER]) | Domain(
            "attachment_ids", "!=", False
        )

    def _notify_get_recipients_groups(self, message, model_description, msg_vals=False):
        groups = super()._notify_get_recipients_groups(
            message, model_description, msg_vals=msg_vals
        )
        if not self:
            return groups

        portal_enabled = isinstance(self, self.env.registry["mixin.portal"])
        if not portal_enabled:
            return groups

        customer = self._mail_get_partners(introspect_fields=False)[self.id]
        if customer:
            access_token = self.sudo()._portal_get_or_create_token(customer[:1])
            local_msg_vals = dict(msg_vals or {})
            local_msg_vals["access_token"] = access_token
            local_msg_vals["pid"] = customer.id
            local_msg_vals["hash"] = self._sign_token(customer.id, token=access_token)
            local_msg_vals.update(customer.sudo().signup_get_auth_param()[customer.id])
            access_link = self._notify_get_action_link("view", **local_msg_vals)

            new_group = [
                (
                    "portal_customer",
                    lambda pdata: pdata["id"] == customer.id,
                    {
                        "active": True,
                        "button_access": {
                            "url": access_link,
                        },
                        "has_button_access": True,
                    },
                )
            ]
        else:
            new_group = []

        portal_group = next((g for g in groups if g[0] == "portal"), None)
        if portal_group is not None:
            portal_group[2]["active"] = True
            portal_group[2]["has_button_access"] = True

        return new_group + groups

    def _sign_token(self, pid, token: str | None = None) -> str:
        return tools.hmac(
            self.env(su=True), PARTNER_HASH_SCOPE, self._portal_hash_signed(pid, token)
        )

    def _verify_sign_token(self, signature, pid, token: str | None = None) -> bool:
        signed = self._portal_hash_signed(pid, token)
        if tools.is_hmac_valid(self.env, PARTNER_HASH_SCOPE, signed, signature):
            return True
        return _legacy_hash_valid(self, signature, signed)

    def _portal_hash_signed(self, pid, token: str | None) -> tuple:
        self.check_singleton()
        if self._mail_post_token_field not in self._fields:
            raise NotImplementedError(
                f"Model {self._name} does not support token signature, as it does "
                f"not have {self._mail_post_token_field} field."
            )
        return (self.env.cr.dbname, token or self[self._mail_post_token_field], pid)

    def _portal_verify_parent_hash(self, signature, pid, token=None) -> bool:
        return False

    @api.model
    def _get_allowed_access_params(self):
        return super()._get_allowed_access_params() | {"hash", "pid", "token"}

    @api.model
    def _get_thread_with_access(
        self, thread_id, *, hash=None, pid=None, token=None, **kwargs
    ):
        if thread := super()._get_thread_with_access(
            thread_id, hash=hash, pid=pid, token=token, **kwargs
        ):
            return thread
        thread = resolve_thread_for_credentials(self.browse(thread_id).sudo())
        if thread and (
            is_thread_hash_pid_valid(thread, hash, pid, token)
            or is_thread_token_valid(thread, token)
        ):
            return thread
        return self.browse()
