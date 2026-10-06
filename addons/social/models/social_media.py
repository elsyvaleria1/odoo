from odoo import fields, models
from odoo.http import request
from odoo.tools import issue_session_state, register_signed_scope

OAUTH_STATE_MAX_AGE_SECONDS = 1800

OAUTH_STATE_SCOPE = register_signed_scope(
    "social.oauth_state",
    purpose="the OAuth state that returns a social account authorization to "
    "the media it was started from, in the session and for the user that "
    "started it",
    lifetime=f"its expiry: the callback refuses a state older than "
    f"{OAUTH_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)

# a flow whose provider or IAP proxy cannot carry a state back keeps it here
UNCARRIED_STATE_SESSION_KEY = "social_oauth_uncarried_state"


class SocialMedia(models.Model):
    """A social.media represents the actual Media, ex: Facebook, Twitter, etc...
    As opposed to social.account that represents an existing account on this media.
    Ex: Odoo Social Facebook Page, Mitchell Admin Twitter Account, ...

    The social.media is used to store global media configuration (API keys, ...).
    It's also used to install the modules related to that social media (social_facebook, social_twitter, ...)."""

    _name = "social.media"
    _description = "Social Media"
    _inherit = ["mixin.mail.thread"]

    _DEFAULT_SOCIAL_IAP_ENDPOINT = "https://social.api.odoo.com"

    name = fields.Char(
        translate=True,
        readonly=True,
        required=True,
    )
    media_description = fields.Char(
        string="Description",
        readonly=True,
    )
    image = fields.Binary(readonly=True)
    media_type = fields.Selection(
        selection=[],
        readonly=True,
        help="Used to make comparisons when we need to restrict some features to a specific media ('facebook', 'x', ...).",
    )
    account_ids = fields.One2many(
        comodel_name="social.account",
        inverse_name="media_id",
        string="Social Accounts",
    )
    accounts_count = fields.Count(
        count_of="account_ids",
        string="# Accounts",
    )
    has_streams = fields.Boolean(
        string="Streams Enabled",
        default=True,
        readonly=True,
        required=True,
        help="Controls if social streams are handled on this social media.",
    )
    can_link_accounts = fields.Boolean(
        string="Can link accounts?",
        default=True,
        readonly=True,
        required=True,
        help="Controls if we can link accounts or not.",
    )
    stream_type_ids = fields.One2many(
        comodel_name="social.stream.type",
        inverse_name="media_id",
        string="Stream Types",
    )
    max_post_length = fields.Integer(
        help="Set a maximum number of characters can be posted in post. 0 for no limit."
    )


    def action_add_account(self, company_id=None):
        # Set the company of the futures new accounts (see <social.account>::_default_company_id)
        if company_id is None:
            company_id = self.env.company.id
        request.session["social_company_id"] = company_id
        return self._action_add_account()

    def _issue_oauth_state(self, carried=True, **claims):
        """The signed state an account authorization of this media carries.

        :param bool carried: Whether the provider brings the state back to the callback;
                             when it cannot, the session keeps it for the callback instead.
        :param claims: What else the callback must find bound to the state.
        :return: The state, which the session that asked for it consumes once.
        :rtype: str
        """
        self.check_singleton()
        state = issue_session_state(
            self.env,
            OAUTH_STATE_SCOPE,
            request.session,
            {"media_id": self.id, **claims},
            max_age_seconds=OAUTH_STATE_MAX_AGE_SECONDS,
        )
        if carried:
            request.session.pop(UNCARRIED_STATE_SESSION_KEY, None)
        else:
            request.session[UNCARRIED_STATE_SESSION_KEY] = state
        return state

    def _action_add_account(self):
        """Every social module should override this method.
        Usually redirects to the social media links that allows accounts to be read by our app."""
        pass
