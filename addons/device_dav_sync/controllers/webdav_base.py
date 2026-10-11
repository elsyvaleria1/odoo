import logging

from lxml import etree

from odoo import http
from odoo.http import Response, request

from ..lib import webdav_utils as dav
from ..lib.webdav_utils import NS_CALDAV, NS_CARDDAV, NS_DAV

_logger = logging.getLogger(__name__)


class WebDAVBaseController(http.Controller):
    @http.route(
        "/dav/<path:resource_path>",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["OPTIONS"],
        typed=True,
    )
    def options(self, resource_path: str):
        return Response(
            "",
            status=200,
            headers={
                "DAV": dav.DAV_COMPLIANCE,
                "Allow": "OPTIONS, GET, HEAD, POST, PUT, DELETE, PROPFIND, REPORT",
                "Content-Length": "0",
            },
        )

    @http.route(
        "/dav/<path:resource_path>",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_dav",
        receiver_event="dav",
        receiver_refusal="device.device:_prepare_dav_refusal_response",
        methods=["PROPFIND"],
        csrf=False,
        typed=True,
    )
    def propfind(self, resource_path: str):
        request.update_env(user=request.admission.extra["user"].id)
        if resource_path.startswith(("addressbooks/", "calendars/")):
            return Response("Not Implemented", status=501)

        depth = request.httprequest.headers.get("Depth", "0")
        requested_props = self._parse_propfind_request()
        responses = self._propfind_root(resource_path, depth, requested_props)
        return dav.prepare_multistatus_response(responses)

    def _parse_propfind_request(self):
        xml_data = request.httprequest.data
        if not xml_data:
            return None
        try:
            root = dav.safe_parse_xml(xml_data)
        except etree.XMLSyntaxError as exc:
            _logger.debug("Failed to parse PROPFIND XML: %s", exc)
            return None
        if root.find(f".//{{{NS_DAV}}}allprop") is not None:
            return None
        prop = root.find(f".//{{{NS_DAV}}}prop")
        if prop is not None:
            return {child.tag for child in prop}
        return None

    def _propfind_root(self, resource_path, depth, requested_props):
        responses = [
            {
                "href": f"/dav/{resource_path}",
                "props": self._filter(
                    {
                        f"{{{NS_DAV}}}resourcetype": self._collection_element(),
                        f"{{{NS_DAV}}}displayname": "DAV Root",
                        f"{{{NS_DAV}}}current-user-principal": self._principal_element(),
                    },
                    requested_props,
                ),
            }
        ]
        if depth in ("1", "infinity"):
            responses.append(
                {
                    "href": "/dav/addressbooks/",
                    "props": self._filter(
                        self._home_props(
                            NS_CARDDAV, "addressbook-home-set", "Address Books"
                        ),
                        requested_props,
                    ),
                }
            )
            responses.append(
                {
                    "href": "/dav/calendars/",
                    "props": self._filter(
                        self._home_props(NS_CALDAV, "calendar-home-set", "Calendars"),
                        requested_props,
                    ),
                }
            )
        return responses

    @staticmethod
    def _filter(props, requested_props):
        if not requested_props:
            return props
        return {k: v for k, v in props.items() if k in requested_props}

    def _home_props(self, home_ns, home_tag, displayname):
        resourcetype = etree.Element(f"{{{NS_DAV}}}resourcetype")
        etree.SubElement(resourcetype, f"{{{NS_DAV}}}collection")
        etree.SubElement(resourcetype, f"{{{home_ns}}}{home_tag}")
        return {
            f"{{{NS_DAV}}}resourcetype": resourcetype,
            f"{{{NS_DAV}}}displayname": displayname,
        }

    @staticmethod
    def _collection_element():
        resourcetype = etree.Element(f"{{{NS_DAV}}}resourcetype")
        etree.SubElement(resourcetype, f"{{{NS_DAV}}}collection")
        return resourcetype

    @staticmethod
    def _principal_element():
        principal = etree.Element(f"{{{NS_DAV}}}current-user-principal")
        href = etree.SubElement(principal, f"{{{NS_DAV}}}href")
        href.text = "/dav/principals/users/"
        return principal
