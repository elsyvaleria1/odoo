import logging
from datetime import UTC, datetime
from typing import Literal

import psycopg
from lxml import etree

from odoo.exceptions import ValidationError
from odoo.http import Response

_logger = logging.getLogger(__name__)


def store_dav_record(env, store):
    try:
        with env.cr.savepoint():
            return store()
    except (ValidationError, psycopg.errors.IntegrityError) as exc:
        raise ValueError(str(exc)) from exc


NS_DAV = "DAV:"
NS_CARDDAV = "urn:ietf:params:xml:ns:carddav"
NS_CALDAV = "urn:ietf:params:xml:ns:caldav"
NS_CS = "http://calendarserver.org/ns/"

DAV_COMPLIANCE = "1, 2, 3, addressbook, calendar-access"

HTTP_STATUS_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    207: "Multi-Status",
    301: "Moved Permanently",
    304: "Not Modified",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    412: "Precondition Failed",
    415: "Unsupported Media Type",
    500: "Internal Server Error",
    501: "Not Implemented",
}


def get_sync_timestamp(value: datetime | Literal[False] | None) -> int:
    if not value:
        return 0
    return int(value.replace(tzinfo=UTC).timestamp())


def prepare_etag(etag: str | Literal[False] | None) -> str:
    if not etag:
        return '""'
    return etag if etag.startswith('"') else f'"{etag}"'


def prepare_href_property(url: str | None) -> etree._Element:
    wrapper = etree.Element("wrapper")
    child = etree.SubElement(wrapper, f"{{{NS_DAV}}}href")
    child.text = url
    return wrapper


def http_status_line(status_code):
    reason = HTTP_STATUS_REASONS.get(status_code, "Unknown")
    return f"HTTP/1.1 {status_code} {reason}"


def prepare_multistatus_response(responses, extra_children=None):
    nsmap = {"D": NS_DAV, "C": NS_CARDDAV, "CAL": NS_CALDAV, "CS": NS_CS}
    multistatus = etree.Element(f"{{{NS_DAV}}}multistatus", nsmap=nsmap)

    for resp_data in responses:
        response = etree.SubElement(multistatus, f"{{{NS_DAV}}}response")
        href = etree.SubElement(response, f"{{{NS_DAV}}}href")
        href.text = resp_data["href"]

        status_code = resp_data.get("status", 200)
        props = resp_data.get("props")
        not_found = resp_data.get("not_found")

        if props:
            propstat = etree.SubElement(response, f"{{{NS_DAV}}}propstat")
            prop = etree.SubElement(propstat, f"{{{NS_DAV}}}prop")
            for prop_name, prop_value in props.items():
                if isinstance(prop_value, etree._Element):
                    prop_value.tag = prop_name
                    prop.append(prop_value)
                elif prop_value is None:
                    etree.SubElement(prop, prop_name)
                else:
                    prop_elem = etree.SubElement(prop, prop_name)
                    prop_elem.text = str(prop_value)
            status_elem = etree.SubElement(propstat, f"{{{NS_DAV}}}status")
            status_elem.text = http_status_line(200)

            if not_found:
                ps404 = etree.SubElement(response, f"{{{NS_DAV}}}propstat")
                p404 = etree.SubElement(ps404, f"{{{NS_DAV}}}prop")
                for prop_name in not_found:
                    etree.SubElement(p404, prop_name)
                s404 = etree.SubElement(ps404, f"{{{NS_DAV}}}status")
                s404.text = http_status_line(404)
        else:
            status_elem = etree.SubElement(response, f"{{{NS_DAV}}}status")
            status_elem.text = http_status_line(status_code)

    for child in extra_children or []:
        multistatus.append(child)

    xml_body = etree.tostring(
        multistatus, xml_declaration=True, encoding="utf-8", pretty_print=True
    )
    return Response(
        xml_body,
        status=207,
        headers={
            "Content-Type": "application/xml; charset=utf-8",
            "DAV": DAV_COMPLIANCE,
        },
    )


_SAFE_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def safe_parse_xml(data):
    return etree.fromstring(data, parser=_SAFE_XML_PARSER)


def get_active_dav_config(env):
    return (
        env["device.profile"]
        .sudo()
        .search([("active", "=", True), ("dav_enabled", "=", True)], limit=1)
    )


def config_for_device(env, device):
    if device and device.config_id:
        return device.config_id.sudo()
    return get_active_dav_config(env)


def config_protocol_enabled(config, kind):
    if not config:
        return False
    return bool(config.dav_enabled and config[f"dav_{kind}_enabled"])


def get_max_items_per_sync(env, config=None):
    config = config if config is not None else get_active_dav_config(env)
    return max(0, config.dav_max_items_per_sync or 0) if config else 0


def get_or_create_dav_device(env, user):
    device_model = env["device.device"].sudo()
    device = device_model.search(
        [("dav_user_id", "=", user.id)],
        order="dav_sync_enabled desc, id",
        limit=1,
    )
    if device:
        return device

    category = env.ref(
        "device_dav_sync.device_category_dav_client", raise_if_not_found=False
    )
    config = get_active_dav_config(env)
    return device_model.create(
        {
            "name": f"DAV Sync - {user.name}",
            "identifier": f"dav-{user.login}",
            "comm_protocol": "https",
            "endpoint": "davx5-client",
            "dav_sync_enabled": True,
            "dav_user_id": user.id,
            "company_id": user.company_id.id,
            "device_category_id": category.id if category else False,
            "config_id": config.id if config else False,
        }
    )


def device_protocol_enabled(device, kind):
    if not device:
        return True
    return bool(device[f"dav_{kind}_enabled"])


def resolve_put_conflict(
    env, device, resource_type, model, record_id, if_match, server_etag
):
    client_match = (if_match or "").strip()
    if not client_match or not client_match.strip("*"):
        return None
    provided = [token.strip() for token in client_match.split(",")]
    if server_etag in provided:
        return None

    state = (
        env["dav.sync.state"]
        .sudo()
        .get_or_create_sync_state(device, resource_type, model, record_id)
    )
    strategy = state.conflict_resolution_strategy
    if strategy in ("client_wins", "merge"):
        return None
    if strategy == "manual":
        state.write(
            {
                "sync_status": "conflict",
                "error_message": "Manual conflict resolution required (DAV PUT)",
            }
        )
        return Response("Conflict", status=409)
    state.update_sync_state(status="synced")
    return Response("Precondition Failed", status=412)
