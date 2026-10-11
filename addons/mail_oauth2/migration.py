"""What a mail vendor's upgrade does with servers authorized before their
connections existed; its migrations call these."""

import logging
from datetime import UTC, datetime

from odoo.db import schema
from odoo.exceptions import UserError
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

SERVER_TABLES = (
    ("ir_mail_server", "ir.mail_server", "smtp_authentication"),
    ("fetchmail_server", "fetchmail.server", "server_type"),
)


def servers_holding_tokens(cr, server_type):
    rows = []
    for table, model, type_field in SERVER_TABLES:
        if not schema.column_exists(cr, table, "oauth2_credential_id"):
            continue
        cr.execute(
            SQL(
                "SELECT id, name, oauth2_credential_id FROM %s"
                " WHERE %s = %s AND oauth2_credential_id IS NOT NULL",
                SQL.identifier(table),
                SQL.identifier(type_field),
                server_type,
            )
        )
        rows += [(model, *row) for row in cr.fetchall()]
    return rows


def refuse_without_client(env, server_type, label, has_client) -> None:
    if has_client:
        return
    if servers := servers_holding_tokens(env.cr, server_type):
        raise UserError(
            env._(
                "%(label)s mail servers are authorized but no %(label)s OAuth client "
                "is configured, and the relay that refreshed their tokens is "
                "removed: %(servers)s. Set the %(label)s OAuth client (Settings, "
                "Discuss) on the current version, then upgrade.",
                label=label,
                servers=", ".join(
                    f"{model} {name!r} (#{record_id})"
                    for model, record_id, name, _credential in servers
                ),
            )
        )


def adopt_servers(
    env, server_type, service, scope_of, legacy_path, expiry_column, client
):
    cr = env.cr
    Credential = env["credential.credential"].with_context(active_test=False)
    adopted = 0
    for table, model, type_field in SERVER_TABLES:
        if not schema.column_exists(cr, table, "oauth2_credential_id"):
            continue
        expiry = (
            SQL.identifier(expiry_column)
            if schema.column_exists(cr, table, expiry_column)
            else SQL("NULL")
        )
        cr.execute(
            SQL(
                "SELECT id, oauth2_credential_id, %s FROM %s"
                " WHERE %s = %s AND oauth2_credential_id IS NOT NULL",
                expiry,
                SQL.identifier(table),
                SQL.identifier(type_field),
                server_type,
            )
        )
        for record_id, credential_id, expires_at in cr.fetchall():
            record = env[model].with_context(active_test=False).browse(record_id)
            env["integration.connection"]._bound(
                record, service, scope_of(record)
            )._adopt_credential(
                Credential.browse(credential_id),
                expires=datetime.fromtimestamp(expires_at, UTC).replace(tzinfo=None)
                if expires_at
                else None,
                client=client,
                redirect_path=legacy_path,
            )
            adopted += 1
        cr.execute(
            SQL(
                "UPDATE %s SET oauth2_credential_id = NULL WHERE %s = %s",
                SQL.identifier(table),
                SQL.identifier(type_field),
                server_type,
            )
        )
        schema.drop_columns(cr, table, [expiry_column])
    _logger.info(
        "%s %s mail servers moved onto their connections", adopted, server_type
    )


def move_client(env, service, client_id_key, client_secret_key, label):
    ICP = env["ir.config_parameter"]
    Credential = env["credential.credential"]
    client_id = ICP.get_param(client_id_key)
    client_secret = Credential._get_system_secret(client_secret_key)
    ICP.search([("key", "=", client_id_key)]).unlink()
    Credential._set_system_secret(client_secret_key, False)
    if not (client_id and client_secret):
        return None
    if not service._has_oauth_client(False):
        service._set_oauth_client(client_id, client_secret, company=False)
        return None
    if service._oauth_client_id(False) == client_id:
        return None
    _logger.warning(
        "%s mail servers keep their own OAuth client %r beside their tokens: the "
        "company's %s client is %r",
        label,
        client_id,
        label,
        service._oauth_client_id(False),
    )
    return {"oauth_client_id": client_id, "oauth_client_secret": client_secret}
