import collections
import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import lxml.html
from lxml import etree
from werkzeug.urls import iri_to_uri

from odoo import http
from odoo.exceptions import MissingError
from odoo.http import abort, request
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


_URL_IGNORED_CHARS = ("\t", "\r", "\n")


def _is_local_url(url: str | None) -> bool:
    if not url or not isinstance(url, str):
        return False
    for char in _URL_IGNORED_CHARS:
        url = url.replace(char, "")
    if not url:
        return False
    if "\\" in url or url.startswith("//"):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return not parsed.scheme and not parsed.netloc


def get_model(env: Any, model_name: str) -> Any:
    Model = env.get(model_name) if isinstance(model_name, str) else None
    if Model is None:
        _debug.logic("get_model_unknown", model=model_name)
        raise MissingError(env._("The model '%s' does not exist", model_name))
    return Model


def is_id_literal(part: str) -> bool:
    return part.isascii() and part.isdigit()


def parse_id_list(raw: str | None) -> list[int]:
    ids = []
    for part in (raw or "").split(","):
        part = part.strip()
        if is_id_literal(part) and (record_id := int(part)):
            ids.append(record_id)
    return ids


def clean_action(action: dict, env: Any) -> dict:
    action_type = action.setdefault("type", "ir.actions.act_window_close")
    if action_type == "ir.actions.act_window" and not action.get("views"):
        _debug.logic(
            "clean_action_views_derived",
            action_id=action.get("id"),
            view_mode=action.get("view_mode"),
        )
        update_action_views(action)

    action_model = env[action["type"]]
    readable_fields = (
        action_model._get_fields_readable() | action_model._get_keys_client_only()
    )
    action_type_fields = action_model._fields.keys()

    cleaned_action = {
        field: value
        for field, value in action.items()
        if field in readable_fields or field not in action_type_fields
    }

    action_name = action.get("name") or action
    custom_properties = action.keys() - readable_fields - action_type_fields
    _debug.pipeline(
        "clean_action",
        action_id=action.get("id"),
        action_type=action_type,
        keys=len(action),
        kept=len(cleaned_action),
        custom=len(custom_properties),
    )
    if custom_properties:
        _logger.warning(
            "Action %r contains custom properties %s. Passing them "
            "via the `params` or `context` properties is recommended instead",
            action_name,
            ", ".join(map(repr, custom_properties)),
        )

    return cleaned_action


def select_db(redirect: str = "/web/database/selector", db: str | None = None) -> None:
    _debug.lifecycle(
        "select_db",
        explicit=db,
        param=request.params.get("db"),
        session_db=request.session.db,
    )
    if db is None:
        db = (raw_db := request.params.get("db")) and raw_db.strip()

    if db and db not in request.app.filter_dbs_served([db]):
        _debug.logic("select_db_not_served", db=db)
        db = None

    if db and not request.session.db:
        r = request.httprequest
        url_redirect = urlsplit(r.base_url)
        if r.query_string:
            query_string = iri_to_uri(r.query_string.decode())
            url_redirect = url_redirect._replace(query=query_string)
        request.session.db = db
        _debug.pipeline("select_db_bind_session", db=db, status=302)
        abort(request.redirect(urlunsplit(url_redirect), 302))

    if (
        not db
        and request.session.db
        and request.app.filter_dbs_served([request.session.db])
    ):
        db = request.session.db
        _debug.logic("select_db_from_session", db=db)

    if not db:
        all_dbs = request.app.get_dbs_served()
        _debug.logic("select_db_served_scan", served=len(all_dbs))
        if len(all_dbs) == 1:
            db = all_dbs[0]

    if not db:
        _debug.pipeline("select_db_unresolved", redirect=redirect, status=303)
        abort(request.redirect(redirect, 303))

    if db != request.session.db:
        _debug.pipeline(
            "select_db_new_session", session_db=request.session.db, db=db, status=302
        )
        request.session = http.root.session_store.new()
        request.session.update(http.prepare_default_session(), db=db)
        request.session.context["lang"] = request.get_default_lang()
        abort(request.redirect(request.httprequest.url, 302))
    _debug.logic("select_db_settled", db=db)


def update_action_views(action: dict) -> None:
    view_id = action.get("view_id") or False
    if isinstance(view_id, (list, tuple)):
        view_id = view_id[0]

    view_modes = action["view_mode"].split(",")
    _debug.logic("update_action_views", view_id=view_id, modes=view_modes)

    if len(view_modes) > 1:
        if view_id:
            raise ValueError(
                f"Non-db action dictionaries should provide "
                f"either multiple view modes or a single view "
                f"mode and an optional view id.\n\n Got view "
                f"modes {view_modes!r} and view id {view_id!r} for action {action!r}"
            )
        action["views"] = [(False, mode) for mode in view_modes]
        return
    action["views"] = [(view_id, view_modes[0])]


def get_action(env: Any, path_part: str) -> Any:
    Actions = env["ir.actions.actions"]

    if path_part.startswith("action-"):
        someid = path_part.removeprefix("action-")
        if is_id_literal(someid):
            _debug.logic("action_path_resolve", path_part=path_part, by="id")
            action = Actions.sudo().browse(int(someid)).exists()
        elif "." in someid:
            _debug.logic("action_path_resolve", path_part=path_part, by="xmlid")
            action = env.ref(someid, False)
            if not action or not action._name.startswith("ir.actions"):
                _debug.logic("action_path_xmlid_not_action", path_part=path_part)
                action = Actions
        else:
            _debug.logic("action_path_malformed", path_part=path_part)
            action = Actions
    elif path_part.startswith("m-") or "." in path_part:
        model = path_part.removeprefix("m-")
        if model in env and not env[model]._abstract:
            action = (
                env["ir.actions.act_window"]
                .sudo()
                .search([("res_model", "=", model)], limit=1)
            )
            _debug.logic(
                "action_path_resolve",
                path_part=path_part,
                by="model",
                model=model,
                source="first_act_window" if action else "synthetic_formview",
            )
            if not action:
                action = env["ir.actions.act_window"].new(
                    env[model].get_formview_action()
                )
        else:
            _debug.logic("action_path_model_unusable", path_part=path_part)
            action = Actions
    else:
        _debug.logic("action_path_resolve", path_part=path_part, by="path")
        return Actions._get_action_by_path(path_part)

    if action and action._name == "ir.actions.actions":
        action = action._get_concrete()

    _debug.pipeline("action_path_resolved", path_part=path_part, action=action)
    return action


def get_action_triples(
    env: Any, path: str, *, start_pos: int = 0
) -> Iterator[tuple[int | None, Any, int | None]]:
    parts = collections.deque(path.strip("/").split("/"))
    word_count = len(parts)
    active_id = None
    record_id = None

    while parts:
        action_name = parts.popleft()
        action = get_action(env, action_name)
        if not action:
            word = word_count - len(parts) - 1 + start_pos
            _debug.logic(
                "action_triples_no_action",
                action_name=action_name,
                word=word,
                path=path,
            )
            raise ValueError(
                f"expected action at word {word} but found “{action_name}”"
            )

        record_id = None
        if parts:
            if parts[0] == "new":
                parts.popleft()
            elif is_id_literal(parts[0]):
                record_id = int(parts.popleft())

        _debug.pipeline(
            "action_triple",
            action_name=action_name,
            active_id=active_id,
            record_id=record_id,
            rest=len(parts),
        )
        yield (active_id, action, record_id)

        if len(parts) > 1 and is_id_literal(parts[0]):
            active_id = int(parts.popleft())
        elif record_id:
            active_id = record_id


def _get_login_redirect_url(uid: int, redirect: str | None = None) -> str:
    if request.session.uid:
        if redirect and _is_local_url(redirect):
            _debug.logic("login_redirect_local", uid=uid, redirect=redirect)
            return redirect
        internal = is_user_internal(request.session.uid)
        _debug.logic(
            "login_redirect_dropped", uid=uid, internal=internal, redirect=redirect
        )
        return "/odoo" if internal else "/web/login_successful"

    url = request.env(user=uid)["res.users"].browse(uid)._get_mfa_url()
    _debug.logic("login_redirect_mfa", uid=uid, redirect=redirect)
    if not redirect or not _is_local_url(redirect):
        return url

    parsed = urlsplit(url)
    qs = dict(parse_qsl(parsed.query))
    qs["redirect"] = redirect
    return urlunsplit(parsed._replace(query=urlencode(qs)))


def is_user_internal(uid: int) -> bool:
    return request.env["res.users"].browse(uid)._is_internal()


type FragmentSwap = Literal["morph", "inner", "outer"]


@dataclass(frozen=True, slots=True)
class Fragment:
    template: str
    values: Mapping[str, Any] = field(default_factory=dict)
    key: str | None = None
    swap: FragmentSwap = "morph"


class RenderedFragment(TypedDict):
    key: str
    html: str
    swap: FragmentSwap


class FragmentEvent(TypedDict):
    name: str
    detail: Mapping[str, Any]


class FragmentResponse(TypedDict):
    fragments: list[RenderedFragment]
    events: list[FragmentEvent]
    redirect: str | None
    data: Mapping[str, Any]


def render_fragments(
    env: Any,
    *fragments: Fragment,
    events: Mapping[str, Mapping[str, Any]] | None = None,
    redirect: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> FragmentResponse:
    if redirect is not None and not _is_local_url(redirect):
        raise ValueError(f"fragment redirect must be a local URL, got {redirect!r}")
    View = env["ir.ui.view"]
    rendered: list[RenderedFragment] = []
    for fragment in fragments:
        key = fragment.key or fragment.template
        if any(done["key"] == key for done in rendered):
            raise ValueError(f"fragment key {key!r} is rendered twice")
        html = str(View._render_template(fragment.template, dict(fragment.values)))
        _check_fragment_root(html, key)
        rendered.append({"key": key, "html": html, "swap": fragment.swap})
    return {
        "fragments": rendered,
        "events": [
            {"name": name, "detail": detail or {}}
            for name, detail in (events or {}).items()
        ],
        "redirect": redirect,
        "data": data or {},
    }


# sent by @web/public/fragment_form: the answer to a form post is wanted as
# fragments, not as the page a browser would be redirected to
FRAGMENTS_HEADER = "X-Odoo-Fragments"


def fragments_or_redirect(
    env: Any,
    location: str,
    *fragments: Fragment,
    events: Mapping[str, Mapping[str, Any]] | None = None,
    data: Mapping[str, Any] | None = None,
    redirect: str | None = None,
) -> Any:
    if request.httprequest.headers.get(FRAGMENTS_HEADER):
        return request.prepare_json_response(
            render_fragments(
                env, *fragments, events=events, redirect=redirect, data=data
            )
        )
    return request.redirect(location, code=303)


def _check_fragment_root(html: str, key: str) -> None:
    try:
        nodes = lxml.html.fragments_fromstring(html)
    except etree.ParserError:
        nodes = []
    elements = [
        node
        for node in nodes
        if not isinstance(node, str) and node.tag is not etree.Comment
    ]
    stray_text = any(node.strip() for node in nodes if isinstance(node, str))
    if (
        len(elements) != 1
        or stray_text
        or (elements[0].tail or "").strip()
        or elements[0].get("data-fragment") != key
    ):
        raise ValueError(
            f"fragment {key!r} must render one root element carrying "
            f'data-fragment="{key}"'
        )
