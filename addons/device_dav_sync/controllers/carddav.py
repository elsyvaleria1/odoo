import logging

from lxml import etree

from odoo import fields, http
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.http import Response, request

from ..lib import webdav_utils as dav
from ..lib.webdav_utils import NS_CALDAV, NS_CARDDAV, NS_CS, NS_DAV

_logger = logging.getLogger(__name__)

VCARD_CONTENT_TYPE = "text/vcard; charset=utf-8"
_ALLOW = "OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, REPORT"


def _resourcetype_addressbook():
    rt = etree.Element("rt")
    etree.SubElement(rt, f"{{{NS_DAV}}}collection")
    etree.SubElement(rt, f"{{{NS_CARDDAV}}}addressbook")
    return rt


def _supported_report_set():
    srs = etree.Element("srs")
    for ns, name in (
        (NS_CARDDAV, "addressbook-query"),
        (NS_CARDDAV, "addressbook-multiget"),
        (NS_DAV, "sync-collection"),
    ):
        supported = etree.SubElement(srs, f"{{{NS_DAV}}}supported-report")
        report = etree.SubElement(supported, f"{{{NS_DAV}}}report")
        etree.SubElement(report, f"{{{ns}}}{name}")
    return srs


class CardDAVController(http.Controller):
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
        if not dav.config_protocol_enabled(config, "addressbook"):
            return Response("Not Found", status=404)
        if not dav.device_protocol_enabled(device, "addressbook"):
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
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.warning("Failed to record CardDAV sync state", exc_info=True)

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

    def _requested_props(self):
        body = request.httprequest.data
        if not body:
            return None
        try:
            root = dav.safe_parse_xml(body)
        except etree.XMLSyntaxError:
            return None
        prop = root.find(f".//{{{NS_DAV}}}prop")
        if prop is None:
            return None
        return {child.tag for child in prop}

    def _book(self, username, book_id):
        book = request.env["dav.addressbook"].sudo().browse(book_id).exists()
        if not book or book.user_id.login != username:
            return None
        return book

    def _contacts(self, env, book):
        config = dav.config_for_device(env, self._device(env))
        limit = dav.get_max_items_per_sync(env, config) or None
        return env["res.partner"].search(
            book._get_domain_contact(), limit=limit, order="write_date desc"
        )

    def _sync_token(self, env, book):
        contacts = (
            env["res.partner"]
            .with_context(active_test=False)
            .search(book._get_domain_contact())
        )
        newest = max((c.write_date for c in contacts if c.write_date), default=None)
        return f"odoo-carddav-{book.id}-{dav.get_sync_timestamp(newest)}"

    @staticmethod
    def _token_epoch(token):
        try:
            return int((token or "").rsplit("-", 1)[-1])
        except ValueError, IndexError:
            return 0

    @http.route(
        [
            "/dav/principals",
            "/dav/principals/",
            "/dav/principals/users",
            "/dav/principals/users/",
            "/dav/principals/users/<string:username>",
            "/dav/principals/users/<string:username>/",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["PROPFIND", "REPORT", "OPTIONS"],
        csrf=False,
        typed=True,
    )
    def principal(self, username: str | None = None, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._options()
        env = self._dav_env()
        login = username or env.user.login
        home = f"/dav/addressbooks/{login}/"
        props = {
            f"{{{NS_DAV}}}current-user-principal": dav.prepare_href_property(
                f"/dav/principals/users/{login}/"
            ),
            f"{{{NS_DAV}}}principal-URL": dav.prepare_href_property(
                f"/dav/principals/users/{login}/"
            ),
            f"{{{NS_CARDDAV}}}addressbook-home-set": dav.prepare_href_property(home),
            f"{{{NS_CALDAV}}}calendar-home-set": dav.prepare_href_property(
                f"/dav/calendars/{login}/"
            ),
            f"{{{NS_DAV}}}displayname": env.user.name,
        }
        return dav.prepare_multistatus_response(
            [{"href": f"/dav/principals/users/{login}/", "props": props}]
        )

    @http.route(
        [
            "/dav/addressbooks",
            "/dav/addressbooks/",
            "/dav/addressbooks/<string:username>",
            "/dav/addressbooks/<string:username>/",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["PROPFIND", "REPORT", "OPTIONS"],
        csrf=False,
        typed=True,
    )
    def addressbook_home(self, username: str | None = None, **kw):
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
                [{"href": f"/dav/addressbooks/{username}/", "status": 404}]
            )

        env["dav.addressbook"].sudo()._provision_default_addressbooks(owner)
        books = env["dav.addressbook"].sudo().search([("user_id", "=", owner.id)])

        home_href = f"/dav/addressbooks/{username}/"
        responses = [
            {
                "href": home_href,
                "props": {
                    f"{{{NS_DAV}}}resourcetype": self._collection_element(),
                    f"{{{NS_DAV}}}displayname": "Address Books",
                    f"{{{NS_DAV}}}current-user-principal": dav.prepare_href_property(
                        f"/dav/principals/users/{username}/"
                    ),
                },
            }
        ]

        depth = request.httprequest.headers.get("Depth", "0")
        if depth in ("1", "infinity"):
            responses.extend(self._book_response(username, book, env) for book in books)

        return dav.prepare_multistatus_response(responses)

    @staticmethod
    def _collection_element():
        rt = etree.Element("rt")
        etree.SubElement(rt, f"{{{NS_DAV}}}collection")
        return rt

    def _book_response(self, username, book, env):
        return {
            "href": f"/dav/addressbooks/{username}/{book.id}/",
            "props": {
                f"{{{NS_DAV}}}resourcetype": _resourcetype_addressbook(),
                f"{{{NS_DAV}}}displayname": book.name,
                f"{{{NS_CS}}}getctag": book.ctag,
                f"{{{NS_DAV}}}sync-token": self._sync_token(env, book),
                f"{{{NS_CARDDAV}}}addressbook-description": book.description or "",
                f"{{{NS_DAV}}}supported-report-set": _supported_report_set(),
            },
        }

    @http.route(
        [
            "/dav/addressbooks/<string:username>/<int:book_id>",
            "/dav/addressbooks/<string:username>/<int:book_id>/",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["PROPFIND", "REPORT", "OPTIONS"],
        csrf=False,
        typed=True,
    )
    def addressbook_collection(self, username: str, book_id: int, **kw):
        method = request.httprequest.method
        if method == "OPTIONS":
            return self._options()
        env = self._dav_env()
        if not self._authorize(env, username):
            return Response("Forbidden", status=403)
        disabled = self._resolve_disabled_response(env)
        if disabled:
            return disabled
        book = self._book(username, book_id)
        if not book:
            return dav.prepare_multistatus_response(
                [
                    {
                        "href": f"/dav/addressbooks/{username}/{book_id}/",
                        "status": 404,
                    }
                ]
            )

        if method == "REPORT":
            return self._report(env, username, book)
        return self._propfind_collection(env, username, book)

    def _propfind_collection(self, env, username, book):
        base = f"/dav/addressbooks/{username}/{book.id}/"
        responses = [
            {
                "href": base,
                "props": {
                    f"{{{NS_DAV}}}resourcetype": _resourcetype_addressbook(),
                    f"{{{NS_DAV}}}displayname": book.name,
                    f"{{{NS_CS}}}getctag": book.ctag,
                    f"{{{NS_DAV}}}sync-token": self._sync_token(env, book),
                },
            }
        ]
        depth = request.httprequest.headers.get("Depth", "0")
        if depth in ("1", "infinity"):
            responses.extend(
                {
                    "href": f"{base}{partner.id}.vcf",
                    "props": {
                        f"{{{NS_DAV}}}getetag": dav.prepare_etag(partner.vcard_etag),
                        f"{{{NS_DAV}}}getcontenttype": VCARD_CONTENT_TYPE,
                        f"{{{NS_DAV}}}resourcetype": None,
                    },
                }
                for partner in self._contacts(env, book)
            )
        return dav.prepare_multistatus_response(responses)

    def _report(self, env, username, book):
        body = request.httprequest.data
        try:
            root = dav.safe_parse_xml(body) if body else None
        except etree.XMLSyntaxError:
            return Response("Bad Request", status=400)
        if root is None:
            return Response("Bad Request", status=400)

        tag = etree.QName(root).localname
        if tag == "addressbook-multiget":
            return self._report_multiget(env, username, book, root)
        if tag == "sync-collection":
            return self._report_sync_collection(env, username, book, root)
        return self._report_query(env, username, book, root)

    def _is_address_data_wanted(self, root) -> bool:
        return root.find(f".//{{{NS_CARDDAV}}}address-data") is not None

    def _card_response(self, username, book, partner, with_data):
        props = {f"{{{NS_DAV}}}getetag": dav.prepare_etag(partner.vcard_etag)}
        if with_data:
            props[f"{{{NS_CARDDAV}}}address-data"] = partner.to_vcard()
        return {
            "href": f"/dav/addressbooks/{username}/{book.id}/{partner.id}.vcf",
            "props": props,
        }

    def _report_query(self, env, username, book, root):
        contacts = self._contacts(env, book)
        text_match = root.find(f".//{{{NS_CARDDAV}}}text-match")
        prop_filter = root.find(f".//{{{NS_CARDDAV}}}prop-filter")
        if text_match is not None and text_match.text and prop_filter is not None:
            field = (prop_filter.get("name") or "").upper()
            needle = text_match.text.strip().lower()
            if field == "TEL":
                contacts = contacts.filtered(
                    lambda c, n=needle: any(
                        n in (phone.number or "").lower() for phone in c.phone_ids
                    )
                )
            elif fname := {"EMAIL": "email", "FN": "display_name"}.get(field):
                contacts = contacts.filtered(
                    lambda c, fn=fname, n=needle: n in (c[fn] or "").lower()
                )
        with_data = self._is_address_data_wanted(root)
        if with_data:
            env["dav.performance"].prefetch_for_serialization(contacts)
        responses = [
            self._card_response(username, book, c, with_data) for c in contacts
        ]
        self._record_states(env, contacts)
        return dav.prepare_multistatus_response(responses)

    def _report_multiget(self, env, username, book, root):
        with_data = self._is_address_data_wanted(root)
        scope = self._contacts(env, book)
        scope_ids = set(scope.ids)
        responses = []
        served = env["res.partner"].browse()
        for href_el in root.findall(f".//{{{NS_DAV}}}href"):
            href = (href_el.text or "").strip()
            name = href.rstrip("/").rsplit("/", 1)[-1]
            partner = self._resolve_partner(env, name)
            if partner and partner.id in scope_ids:
                responses.append(
                    self._card_response(username, book, partner, with_data)
                )
                served |= partner
            else:
                responses.append({"href": href, "status": 404})
        self._record_states(env, served)
        return dav.prepare_multistatus_response(responses)

    def _report_sync_collection(self, env, username, book, root):
        token_el = root.find(f".//{{{NS_DAV}}}sync-token")
        since = self._token_epoch(token_el.text if token_el is not None else None)
        with_data = self._is_address_data_wanted(root)
        responses = []
        served = self._contacts(env, book)
        for partner in served:
            if since and dav.get_sync_timestamp(partner.write_date) <= since:
                continue
            responses.append(self._card_response(username, book, partner, with_data))
        if since:
            archived = (
                env["res.partner"]
                .with_context(active_test=False)
                .search(book._get_domain_contact() + [("active", "=", False)])
            )
            responses.extend(
                {
                    "href": f"/dav/addressbooks/{username}/{book.id}/{partner.id}.vcf",
                    "status": 404,
                }
                for partner in archived
                if dav.get_sync_timestamp(partner.write_date) > since
            )
        self._record_states(env, served)
        sync_token = etree.Element(f"{{{NS_DAV}}}sync-token")
        sync_token.text = self._sync_token(env, book)
        return dav.prepare_multistatus_response(responses, extra_children=[sync_token])

    @http.route(
        "/dav/addressbooks/<string:username>/<int:book_id>/<string:card_id>",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["GET", "HEAD", "PUT", "DELETE", "PROPFIND", "OPTIONS"],
        csrf=False,
        typed=True,
    )
    def addressbook_resource(self, username: str, book_id: int, card_id: str, **kw):
        method = request.httprequest.method
        if method == "OPTIONS":
            return self._options()
        env = self._dav_env()
        if not self._authorize(env, username):
            return Response("Forbidden", status=403)
        disabled = self._resolve_disabled_response(env)
        if disabled:
            return disabled
        book = self._book(username, book_id)
        if not book:
            return Response("Not Found", status=404)

        if method in ("GET", "HEAD"):
            return self._get_card(env, book, card_id, head=method == "HEAD")
        if method == "PUT":
            return self._put_card(env, username, book, card_id)
        if method == "DELETE":
            return self._remove_card(env, book, card_id)
        partner = self._resolve_partner(env, card_id)
        if not partner or not self._is_partner_in_scope(book, partner):
            return Response("Not Found", status=404)
        base = f"/dav/addressbooks/{username}/{book.id}/"
        return dav.prepare_multistatus_response(
            [
                {
                    "href": f"{base}{partner.id}.vcf",
                    "props": {
                        f"{{{NS_DAV}}}getetag": dav.prepare_etag(partner.vcard_etag),
                        f"{{{NS_DAV}}}getcontenttype": VCARD_CONTENT_TYPE,
                    },
                }
            ]
        )

    def _resolve_partner(self, env, card_id):
        name = card_id.removesuffix(".vcf")
        if name.isdecimal():
            partner = env["res.partner"].browse(int(name)).exists()
            if partner:
                return partner
        return env["res.partner"].search([("vcard_uid", "=", name)], limit=1)

    def _is_partner_in_scope(self, book, partner) -> bool:
        if not partner:
            return False
        domain = book._get_domain_contact() + [("id", "=", partner.id)]
        return bool(partner.env["res.partner"].search_count(domain, limit=1))

    def _get_card(self, env, book, card_id, head=False):
        partner = self._resolve_partner(env, card_id)
        if not partner or not self._is_partner_in_scope(book, partner):
            return Response("Not Found", status=404)
        headers = {
            "Content-Type": VCARD_CONTENT_TYPE,
            "ETag": dav.prepare_etag(partner.vcard_etag),
        }
        if head:
            return Response("", status=200, headers=headers)
        body = partner.to_vcard()
        self._record_states(env, partner)
        return Response(body, status=200, headers=headers)

    def _put_card(self, env, username, book, card_id):
        vcard_data = request.httprequest.data.decode("utf-8", errors="replace")
        if not vcard_data.strip():
            return Response("Bad Request", status=400)

        partner = self._resolve_partner(env, card_id)
        if_none_match = request.httprequest.headers.get("If-None-Match")
        if_match = request.httprequest.headers.get("If-Match")

        if partner and partner.exists():
            if if_none_match == "*":
                return Response("Precondition Failed", status=412)
            conflict = self._resolve_put_conflict(
                env, "contact", "res.partner", partner, if_match, "vcard_etag"
            )
            if conflict is not None:
                return conflict
            try:
                partner.from_vcard(vcard_data)
            except ValueError:
                return Response("Bad Request", status=400)
            partner.invalidate_recordset(["vcard_etag"])
            self._record_states(env, partner)
            return Response(
                "", status=204, headers={"ETag": dav.prepare_etag(partner.vcard_etag)}
            )

        try:
            partner = env["res.partner"].create_from_vcard(
                vcard_data, user_id=book.user_id.id
            )
        except ValueError:
            return Response("Bad Request", status=400)
        self._record_states(env, partner)
        location = f"/dav/addressbooks/{username}/{book.id}/{partner.id}.vcf"
        return Response(
            "",
            status=201,
            headers={
                "ETag": dav.prepare_etag(partner.vcard_etag),
                "Location": location,
            },
        )

    def _remove_card(self, env, book, card_id):
        partner = self._resolve_partner(env, card_id)
        if not partner or not self._is_partner_in_scope(book, partner):
            return Response("Not Found", status=404)
        partner.action_archive()
        self._record_states(env, partner.with_context(active_test=False))
        return Response("", status=204)
