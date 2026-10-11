import logging
import re

from odoo import SUPERUSER_ID, api
from odoo.db import schema
from odoo.libs.json import dumps as json_dumps

_logger = logging.getLogger(__name__)

OLD_KEY = "google_address_autocomplete.google_places_api_key"
NEW_KEY = "address_autocomplete_google.api_key"


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Credential = env["credential.credential"]
    if key := Credential._get_system_secret(OLD_KEY):
        Credential._set_system_secret(NEW_KEY, key)
        Credential._set_system_secret(OLD_KEY, False)

    icp = env["ir.config_parameter"]
    if not icp.get_param("address_autocomplete.provider"):
        icp.set_param("address_autocomplete.provider", "google")

    rewrite_views(cr)


RULES = (
    (
        re.compile(r"""(widget=["'])google_address_autocomplete(["'])"""),
        r"\1address_autocomplete\2",
    ),
    (
        re.compile(
            r"""(<attribute\s+name=["']widget["']\s*>)\s*google_address_autocomplete\s*(</attribute>)"""
        ),
        r"\1address_autocomplete\2",
    ),
    (
        re.compile(r"""(id=["'])google_address_autocomplete(_warning)?(["'])"""),
        r"\1address_autocomplete_google\2\3",
    ),
    (
        re.compile(r"\bmodule_google_address_autocomplete\b"),
        "module_address_autocomplete_google",
    ),
)


def _rewritten(arch: str) -> str:
    for pattern, replacement in RULES:
        arch = pattern.sub(replacement, arch)
    return arch


def rewrite_views(cr) -> None:
    rewritten = 0
    cr.execute(
        "SELECT id, arch_db, arch_prev FROM ir_ui_view"
        " WHERE arch_db::text LIKE %s OR arch_prev LIKE %s",
        ["%google_address_autocomplete%"] * 2,
    )
    for view_id, arch_db, arch_prev in cr.fetchall():
        new_db = {lang: _rewritten(arch) for lang, arch in (arch_db or {}).items()}
        new_prev = arch_prev and _rewritten(arch_prev)
        if new_db != arch_db or new_prev != arch_prev:
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s::jsonb, arch_prev = %s"
                " WHERE id = %s",
                [
                    json_dumps(new_db) if arch_db is not None else None,
                    new_prev,
                    view_id,
                ],
            )
            rewritten += 1
    if schema.table_exists(cr, "ir_ui_view_custom"):
        cr.execute(
            "SELECT id, arch FROM ir_ui_view_custom WHERE arch LIKE %s",
            ["%google_address_autocomplete%"],
        )
        for custom_id, arch in cr.fetchall():
            if (new := _rewritten(arch)) != arch:
                cr.execute(
                    "UPDATE ir_ui_view_custom SET arch = %s WHERE id = %s",
                    [new, custom_id],
                )
                rewritten += 1
    if rewritten:
        _logger.info("%d views now use the address_autocomplete widget", rewritten)
