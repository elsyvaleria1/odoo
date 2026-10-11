import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        WITH undeclared AS (
            UPDATE res_users_apikeys_scope scope
            SET active = false
            WHERE NOT EXISTS (
                SELECT FROM ir_model_data imd
                WHERE imd.model = 'res.users.apikeys.scope'
                  AND imd.res_id = scope.id
                  AND left(imd.module, 2) != '__'
            )
            RETURNING scope.id, scope.key
        )
        SELECT undeclared.key, count(apikey.id)
        FROM undeclared
        LEFT JOIN res_users_apikeys apikey ON apikey.scope_id = undeclared.id
        GROUP BY undeclared.key
        ORDER BY undeclared.key
        """
    )
    if undeclared := cr.fetchall():
        _logger.warning(
            "Archived %d API key scope(s) no module declares; the %d key(s) "
            "bound to them are refused at every door: %s",
            len(undeclared),
            sum(count for _key, count in undeclared),
            ", ".join(f"{key} ({count})" for key, count in undeclared),
        )
    cr.execute(
        """
        SELECT scope.key, count(*)
        FROM res_users_apikeys apikey
        JOIN res_users_apikeys_scope scope ON scope.id = apikey.scope_id
        WHERE scope.key != 'rpc' AND scope.active
        GROUP BY scope.key
        ORDER BY scope.key
        """
    )
    if bound := cr.fetchall():
        _logger.info(
            "API keys bound to a door other than `rpc` no longer open the "
            "XML-RPC doors: %s",
            ", ".join(f"{key} ({count})" for key, count in bound),
        )
    cr.execute(
        """
        SELECT string_agg(scope.key, ', ' ORDER BY scope.key)
        FROM res_users_apikeys_scope scope
        WHERE scope.active AND scope.key != 'rpc'
        """
    )
    [doors] = cr.fetchone()
    cr.execute(
        """
        SELECT users.login, users.id, count(*)
        FROM res_users_apikeys apikey
        JOIN res_users users ON users.id = apikey.user_id
        WHERE apikey.scope_id IS NULL
        GROUP BY users.id, users.login
        ORDER BY users.login
        """
    )
    for login, uid, count in cr.fetchall():
        _logger.info(
            "User %s (#%d) holds %d API key(s) bound to no door: they now open "
            "the RPC doors (XML-RPC, JSON-2) alone; an integration using one "
            "at another door (%s) needs a key bound to that door.",
            login,
            uid,
            count,
            doors or "none installed",
        )
