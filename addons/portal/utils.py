from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from odoo.models import BaseModel

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused


def get_url_with_params(
    url_string, query_params, remove_duplicates=True, *, doseq=False
):
    """Merge query parameters while preserving the URL path and fragment.

    Replace only supplied keys by default; repeated unrelated keys and blank
    values retain their meaning. Set ``remove_duplicates=False`` to append,
    or ``doseq=True`` to encode sequence values as repeated parameters.
    """
    if not query_params:
        return url_string
    url = urlsplit(url_string)
    url_params = parse_qsl(url.query, keep_blank_values=True)
    if remove_duplicates:
        url_params = [
            (key, value) for key, value in url_params if key not in query_params
        ]
    url_params.extend(query_params.items())
    return urlunsplit(url._replace(query=urlencode(url_params, doseq=doseq)))


def resolve_message_thread(message: BaseModel) -> BaseModel:
    if not message.res_id or not message._is_thread_model():
        return message.env["mixin.mail.thread"]
    return message._get_thread_model().browse(message.res_id)


def resolve_thread_for_credentials(thread: BaseModel) -> BaseModel:
    return thread.exists() if thread.ids else thread


def thread_link(thread: BaseModel, token: str | None, action: str | None = None):
    """The live access.link `token` opens `thread` with, or an empty link."""
    Link = thread.env["access.link"]
    if not thread:
        return Link
    try:
        return Link._resolve(
            token, model=thread._name, res_id=thread.id, action=action
        ).link
    except LinkRefused, LinkLoginRequired:
        return Link


def is_thread_hash_pid_valid(
    thread: BaseModel,
    _hash: str | None,
    pid: int | str | None,
    token: str | None = None,
) -> bool:
    if not isinstance(_hash, str) or not _hash or not pid:
        return False
    if thread._mail_post_token_field not in thread._fields:
        return False
    if isinstance(pid, bool) or not isinstance(pid, (int, str)):
        return False
    try:
        pid = int(pid)
    except ValueError:
        return False
    # a hash signs the token its URL carries: an old URL's token is a link
    # carried over from before, and its hash still holds over it
    signed_over = token if token and thread_link(thread, token) else None
    return thread._verify_sign_token(
        _hash, pid, token=signed_over
    ) or thread._portal_verify_parent_hash(_hash, pid, token=token)


def is_thread_token_valid(thread: BaseModel, token: str | None) -> bool:
    token_field = thread._mail_post_token_field
    if not isinstance(token, str) or not token or token_field not in thread._fields:
        return False
    return bool(thread_link(thread, token, action="comment"))


def get_portal_partner(
    thread: BaseModel,
    _hash: str | None,
    pid: int | str | None,
    token: str | None,
) -> BaseModel:
    thread = resolve_thread_for_credentials(thread)
    if not thread:
        return thread.env["res.partner"]
    if is_thread_hash_pid_valid(thread, _hash, pid, token):
        return thread.env["res.partner"].sudo().browse(int(pid)).exists()
    if is_thread_token_valid(thread, token):
        if (link := thread_link(thread, token)) and link.partner_id:
            return link.partner_id
        if partner := thread._mail_get_partners()[thread.id][:1]:
            return partner
    return thread.env["res.partner"]
