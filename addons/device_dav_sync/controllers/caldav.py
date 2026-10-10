import logging
from datetime import datetime

from lxml import etree

from odoo import fields, http
from odoo.http import Response, request

from ..lib import webdav_utils as dav
from ..lib.webdav_utils import NS_CALDAV, NS_CS, NS_DAV

_logger = logging.getLogger(__name__)

ICAL_CONTENT_TYPE = "text/calendar; charset=utf-8"
NS_APPLE_ICAL = "http://apple.com/ns/ical/"
_ALLOW = "OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, REPORT"


def _parse_caldav_datetime(value):
    try:
        return datetime.strptime(value or "", "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def _resourcetype_calendar():
    rt = etree.Element("rt")
    etree.SubElement(rt, f"{{{NS_DAV}}}collection")
    etree.SubElement(rt, f"{{{NS_CALDAV}}}calendar")
    return rt


def _supported_component_set():
    scs = etree.Element("scs")
    comp = etree.SubElement(scs, f"{{{NS_CALDAV}}}comp")
    comp.set("name", "VEVENT")
    return scs


def _supported_report_set():
    srs = etree.Element("srs")
    for ns, name in (
        (NS_CALDAV, "calendar-query"),
        (NS_CALDAV, "calendar-multiget"),
        (NS_DAV, "sync-collection"),
    ):
        supported = etree.SubElement(srs, f"{{{NS_DAV}}}supported-report")
        report = etree.SubElement(supported, f"{{{NS_DAV}}}report")
        etree.SubElement(report, f"{{{ns}}}{name}")
    return srs


class CalDAVController(http.Controller):
    def _dav_env(self):
        request.update_env(user=request.admission.extra["user"].id)
        return request.env

    def _authorize(self, env, username):
        user = env.user
        if username and username != user.login:
            return user.has_group("device_dav_sync.group_dav_manager")
        return True

    def _resolve_disabled_response(self, env):
        device = self._device(env)
        config = dav.config_for_device(env, device)
        if not dav.config_protocol_enabled(config, "calendar"):
            return Response("Not Found", status=404)
        if not dav.device_protocol_enabled(device, "calendar"):
            return Response("Not Found", status=404)
        return None

    def _device(self, env):
        return dav.get_or_create_dav_device(env, env.user)

    def _record_states(self, env, records):
        if not records:
            return
        try:
            with env.cr.savepoint():
                device = self._device(env)
                env["dav.sync.state"].sudo()._record_many(device, records)
                device.dav_last_sync = fields.Datetime.now()
        except Exception:
            _logger.warning("Failed to record CalDAV sync state", exc_info=True)

    def _resolve_put_conflict(self, env, resource_type, model, record, if_match, field):
        return dav.resolve_put_conflict(
            env,
            self._device(env),
            resource_type,
            model,
            record.id,
            if_match,
            dav.prepare_etag(record[field]),
        )

    def _options(self):
        return Response(
            "",
            status=200,
            headers={
                "DAV": dav.DAV_COMPLIANCE,
                "Allow": _ALLOW,
                "Content-Length": "0",
            },
        )

    def _calendar(self, username, calendar_id):
        calendar = request.env["dav.calendar"].sudo().browse(calendar_id).exists()
        if not calendar or calendar.user_id.login != username:
            return None
        return calendar

    def _events(self, env, calendar, date_from=None, date_to=None):
        config = dav.config_for_device(env, self._device(env))
        limit = dav.get_max_items_per_sync(env, config) or None
        return env["calendar.event"].search(
            calendar._get_domain_event(date_from, date_to),
            limit=limit,
            order="start asc",
        )

    def _sync_token(self, env, calendar):
        events = (
            env["calendar.event"]
            .with_context(active_test=False)
            .search(calendar._get_domain_event())
        )
        newest = max((e.write_date for e in events if e.write_date), default=None)
        return f"odoo-caldav-{calendar.id}-{dav.get_sync_timestamp(newest)}"

    @staticmethod
    def _token_epoch(token):
        try:
            return int((token or "").rsplit("-", 1)[-1])
        except ValueError, IndexError:
            return 0

    @http.route(
        [
            "/dav/calendars",
            "/dav/calendars/",
            "/dav/calendars/<string:username>",
            "/dav/calendars/<string:username>/",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["PROPFIND", "REPORT", "OPTIONS"],
        csrf=False,  # auth="receiver": the device's bearer token or its user's Basic login
        typed=True,
    )
    def calendar_home(self, username: str | None = None, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._options()
        env = self._dav_env()
        username = username or env.user.login
        if not self._authorize(env, username):
            return Response("Forbidden", status=403)
        disabled = self._resolve_disabled_response(env)
        if disabled:
            return disabled

        owner = env["res.users"].sudo().search([("login", "=", username)], limit=1)
        if not owner:
            return dav.prepare_multistatus_response(
                [{"href": f"/dav/calendars/{username}/", "status": 404}]
            )

        env["dav.calendar"].sudo()._provision_default_calendars(owner)
        calendars = env["dav.calendar"].sudo().search([("user_id", "=", owner.id)])

        home_href = f"/dav/calendars/{username}/"
        responses = [
            {
                "href": home_href,
                "props": {
                    f"{{{NS_DAV}}}resourcetype": self._collection_element(),
                    f"{{{NS_DAV}}}displayname": "Calendars",
                    f"{{{NS_DAV}}}current-user-principal": dav.prepare_href_property(
                        f"/dav/principals/users/{username}/"
                    ),
                },
            }
        ]

        depth = request.httprequest.headers.get("Depth", "0")
        if depth in ("1", "infinity"):
            responses.extend(
                self._calendar_response(username, calendar, env)
                for calendar in calendars
            )

        return dav.prepare_multistatus_response(responses)

    @staticmethod
    def _collection_element():
        rt = etree.Element("rt")
        etree.SubElement(rt, f"{{{NS_DAV}}}collection")
        return rt

    def _calendar_response(self, username, calendar, env):
        return {
            "href": f"/dav/calendars/{username}/{calendar.id}/",
            "props": {
                f"{{{NS_DAV}}}resourcetype": _resourcetype_calendar(),
                f"{{{NS_DAV}}}displayname": calendar.name,
                f"{{{NS_CS}}}getctag": calendar.ctag,
                f"{{{NS_DAV}}}sync-token": self._sync_token(env, calendar),
                f"{{{NS_CALDAV}}}calendar-description": calendar.description or "",
                f"{{{NS_CALDAV}}}supported-calendar-component-set": (
                    _supported_component_set()
                ),
                f"{{{NS_APPLE_ICAL}}}calendar-color": calendar.color or "",
                f"{{{NS_DAV}}}supported-report-set": _supported_report_set(),
            },
        }

    @http.route(
        [
            "/dav/calendars/<string:username>/<int:calendar_id>",
            "/dav/calendars/<string:username>/<int:calendar_id>/",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["PROPFIND", "REPORT", "OPTIONS"],
        csrf=False,  # auth="receiver": the device's bearer token or its user's Basic login
        typed=True,
    )
    def calendar_collection(self, username: str, calendar_id: int, **kw):  # pylint: disable=too-many-return-statements
        method = request.httprequest.method
        if method == "OPTIONS":
            return self._options()
        env = self._dav_env()
        if not self._authorize(env, username):
            return Response("Forbidden", status=403)
        disabled = self._resolve_disabled_response(env)
        if disabled:
            return disabled
        calendar = self._calendar(username, calendar_id)
        if not calendar:
            return dav.prepare_multistatus_response(
                [
                    {
                        "href": f"/dav/calendars/{username}/{calendar_id}/",
                        "status": 404,
                    }
                ]
            )

        if method == "REPORT":
            return self._report(env, username, calendar)
        return self._propfind_collection(env, username, calendar)

    def _propfind_collection(self, env, username, calendar):
        base = f"/dav/calendars/{username}/{calendar.id}/"
        responses = [
            {
                "href": base,
                "props": {
                    f"{{{NS_DAV}}}resourcetype": _resourcetype_calendar(),
                    f"{{{NS_DAV}}}displayname": calendar.name,
                    f"{{{NS_CS}}}getctag": calendar.ctag,
                    f"{{{NS_DAV}}}sync-token": self._sync_token(env, calendar),
                    f"{{{NS_CALDAV}}}calendar-description": calendar.description or "",
                    f"{{{NS_CALDAV}}}supported-calendar-component-set": (
                        _supported_component_set()
                    ),
                    f"{{{NS_APPLE_ICAL}}}calendar-color": calendar.color or "",
                    f"{{{NS_DAV}}}supported-report-set": _supported_report_set(),
                },
            }
        ]
        depth = request.httprequest.headers.get("Depth", "0")
        if depth in ("1", "infinity"):
            responses.extend(
                {
                    "href": f"{base}{event.id}.ics",
                    "props": {
                        f"{{{NS_DAV}}}getetag": dav.prepare_etag(event.ical_etag),
                        f"{{{NS_DAV}}}getcontenttype": ICAL_CONTENT_TYPE,
                        f"{{{NS_DAV}}}resourcetype": None,
                    },
                }
                for event in self._events(env, calendar)
            )
        return dav.prepare_multistatus_response(responses)

    def _report(self, env, username, calendar):
        body = request.httprequest.data
        try:
            root = dav.safe_parse_xml(body) if body else None
        except etree.XMLSyntaxError:
            return Response("Bad Request", status=400)
        if root is None:
            return Response("Bad Request", status=400)

        tag = etree.QName(root).localname
        if tag == "calendar-multiget":
            return self._report_multiget(env, username, calendar, root)
        if tag == "sync-collection":
            return self._report_sync_collection(env, username, calendar, root)
        if tag == "free-busy-query":
            return Response("Not Implemented", status=501)
        return self._report_query(env, username, calendar, root)

    def _is_calendar_data_wanted(self, root) -> bool:
        return root.find(f".//{{{NS_CALDAV}}}calendar-data") is not None

    def _event_response(self, username, calendar, event, with_data):
        props = {f"{{{NS_DAV}}}getetag": dav.prepare_etag(event.ical_etag)}
        if with_data:
            props[f"{{{NS_CALDAV}}}calendar-data"] = event.to_icalendar()
        return {
            "href": f"/dav/calendars/{username}/{calendar.id}/{event.id}.ics",
            "props": props,
        }

    def _report_query(self, env, username, calendar, root):
        date_from = date_to = None
        time_range = root.find(f".//{{{NS_CALDAV}}}time-range")
        if time_range is not None:
            date_from = _parse_caldav_datetime(time_range.get("start"))
            date_to = _parse_caldav_datetime(time_range.get("end"))
        events = self._events(env, calendar, date_from, date_to)
        with_data = self._is_calendar_data_wanted(root)
        if with_data:
            env["dav.performance"].prefetch_for_serialization(events)
        responses = [
            self._event_response(username, calendar, e, with_data) for e in events
        ]
        self._record_states(env, events)
        return dav.prepare_multistatus_response(responses)

    def _report_multiget(self, env, username, calendar, root):
        with_data = self._is_calendar_data_wanted(root)
        scope = self._events(env, calendar)
        scope_ids = set(scope.ids)
        responses = []
        served = env["calendar.event"].browse()
        for href_el in root.findall(f".//{{{NS_DAV}}}href"):
            href = (href_el.text or "").strip()
            name = href.rstrip("/").rsplit("/", 1)[-1]
            event = self._resolve_event(env, name)
            if event and event.id in scope_ids:
                responses.append(
                    self._event_response(username, calendar, event, with_data)
                )
                served |= event
            else:
                responses.append({"href": href, "status": 404})
        self._record_states(env, served)
        return dav.prepare_multistatus_response(responses)

    def _report_sync_collection(self, env, username, calendar, root):
        token_el = root.find(f".//{{{NS_DAV}}}sync-token")
        since = self._token_epoch(token_el.text if token_el is not None else None)
        with_data = self._is_calendar_data_wanted(root)
        responses = []
        served = self._events(env, calendar)
        for event in served:
            if since and dav.get_sync_timestamp(event.write_date) <= since:
                continue
            responses.append(self._event_response(username, calendar, event, with_data))
        if since:
            archived = (
                env["calendar.event"]
                .with_context(active_test=False)
                .search(calendar._get_domain_event() + [("active", "=", False)])
            )
            responses.extend(
                {
                    "href": (f"/dav/calendars/{username}/{calendar.id}/{event.id}.ics"),
                    "status": 404,
                }
                for event in archived
                if dav.get_sync_timestamp(event.write_date) > since
            )
        self._record_states(env, served)
        sync_token = etree.Element(f"{{{NS_DAV}}}sync-token")
        sync_token.text = self._sync_token(env, calendar)
        return dav.prepare_multistatus_response(responses, extra_children=[sync_token])

    @http.route(
        "/dav/calendars/<string:username>/<int:calendar_id>/<string:ics_id>",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["GET", "HEAD", "PUT", "DELETE", "PROPFIND", "OPTIONS"],
        csrf=False,  # auth="receiver": the device's bearer token or its user's Basic login
        typed=True,
    )
    def calendar_resource(self, username: str, calendar_id: int, ics_id: str, **kw):  # pylint: disable=too-many-return-statements
        method = request.httprequest.method
        if method == "OPTIONS":
            return self._options()
        env = self._dav_env()
        if not self._authorize(env, username):
            return Response("Forbidden", status=403)
        disabled = self._resolve_disabled_response(env)
        if disabled:
            return disabled
        calendar = self._calendar(username, calendar_id)
        if not calendar:
            return Response("Not Found", status=404)

        if method in ("GET", "HEAD"):
            return self._get_event(env, calendar, ics_id, head=method == "HEAD")
        if method == "PUT":
            return self._put_event(env, username, calendar, ics_id)
        if method == "DELETE":
            return self._remove_event(env, calendar, ics_id)
        event = self._resolve_event(env, ics_id)
        if not event or not self._is_event_in_scope(calendar, event):
            return Response("Not Found", status=404)
        base = f"/dav/calendars/{username}/{calendar.id}/"
        return dav.prepare_multistatus_response(
            [
                {
                    "href": f"{base}{event.id}.ics",
                    "props": {
                        f"{{{NS_DAV}}}getetag": dav.prepare_etag(event.ical_etag),
                        f"{{{NS_DAV}}}getcontenttype": ICAL_CONTENT_TYPE,
                    },
                }
            ]
        )

    def _resolve_event(self, env, ics_id):
        name = ics_id.removesuffix(".ics")
        if name.isdecimal():
            event = env["calendar.event"].browse(int(name)).exists()
            if event:
                return event
        return env["calendar.event"].search([("ical_uid", "=", name)], limit=1)

    def _is_event_in_scope(self, calendar, event) -> bool:
        if not event:
            return False
        domain = calendar._get_domain_event() + [("id", "=", event.id)]
        return bool(event.env["calendar.event"].search_count(domain, limit=1))

    def _get_event(self, env, calendar, ics_id, head=False):
        event = self._resolve_event(env, ics_id)
        if not event or not self._is_event_in_scope(calendar, event):
            return Response("Not Found", status=404)
        headers = {
            "Content-Type": ICAL_CONTENT_TYPE,
            "ETag": dav.prepare_etag(event.ical_etag),
        }
        if head:
            return Response("", status=200, headers=headers)
        body = event.to_icalendar()
        self._record_states(env, event)
        return Response(body, status=200, headers=headers)

    def _put_event(self, env, username, calendar, ics_id):  # pylint: disable=too-many-return-statements
        ical_data = request.httprequest.data.decode("utf-8", errors="replace")
        if not ical_data.strip():
            return Response("Bad Request", status=400)

        event = self._resolve_event(env, ics_id)
        if_none_match = request.httprequest.headers.get("If-None-Match")
        if_match = request.httprequest.headers.get("If-Match")

        if event and event.exists():
            if if_none_match == "*":
                return Response("Precondition Failed", status=412)
            conflict = self._resolve_put_conflict(
                env, "event", "calendar.event", event, if_match, "ical_etag"
            )
            if conflict is not None:
                return conflict
            try:
                event.from_icalendar(ical_data)
            except ValueError:
                return Response("Bad Request", status=400)
            event.invalidate_recordset(["ical_etag"])
            self._record_states(env, event)
            return Response(
                "", status=204, headers={"ETag": dav.prepare_etag(event.ical_etag)}
            )

        try:
            event = env["calendar.event"].create_from_icalendar(
                ical_data, user_id=calendar.user_id.id
            )
        except ValueError:
            return Response("Bad Request", status=400)
        self._record_states(env, event)
        location = f"/dav/calendars/{username}/{calendar.id}/{event.id}.ics"
        return Response(
            "",
            status=201,
            headers={
                "ETag": dav.prepare_etag(event.ical_etag),
                "Location": location,
            },
        )

    def _remove_event(self, env, calendar, ics_id):
        event = self._resolve_event(env, ics_id)
        if not event or not self._is_event_in_scope(calendar, event):
            return Response("Not Found", status=404)
        event.action_archive()
        self._record_states(env, event.with_context(active_test=False))
        return Response("", status=204)
