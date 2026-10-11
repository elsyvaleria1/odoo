from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
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
