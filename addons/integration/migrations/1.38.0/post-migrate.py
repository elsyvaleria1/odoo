from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    # a service authorized before this version is registered with its provider
    # under the old callback and was never asked for PKCE: it keeps both until
    # an administrator registers the standard path and switches
    cr.execute(
        SQL(
            """
            UPDATE integration_service
               SET oauth_redirect_path = %s,
                   oauth_use_pkce = FALSE
             WHERE auth_type = 'oauth2'
            """,
            "/api_gateway/oauth/callback",
        )
    )
