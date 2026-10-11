from odoo.addons.calendar_google.utils.calendar_google import CALENDAR_SCOPE


def authorize_google_calendar(
    user, access_token="an-access", refresh_token="a-refresh"
):
    env = user.env
    connection = env["integration.connection"]._personal(
        env.ref("integration_google.service_google"), user, scope=CALENDAR_SCOPE
    )
    connection._oauth_store_tokens(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
        },
        "https://odoo.example/integration/oauth/callback",
    )
    return connection
