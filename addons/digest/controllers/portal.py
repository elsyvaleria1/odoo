from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import Controller, Response, request, route

#: Periodicities `set_periodicity` accepts, read off the model so the route and
#: the field cannot drift apart.
from odoo.addons.digest.models.digest import PERIODICITIES


class DigestController(Controller):
    # csrf=False: a mail client posts the one-click unsubscribe; auth="receiver" admits it
    @route(
        [
            "/digest/<int:digest_id>/unsubscribe_oneclick",
            # Spelled without the second "c" until 2026-08. The route stays because
            # the misspelling is baked into the List-Unsubscribe header of every
            # digest already sitting in a mailbox, and those keep arriving for as
            # long as recipients keep them.
            "/digest/<int:digest_id>/unsubscribe_oneclik",
        ],
        type="http",
        website=True,
        auth="receiver",
        receiver="digest.digest:_receiver_for_unsubscribe",
        receiver_event="digest_unsubscribe",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def digest_unsubscribe_oneclick(
        self, digest_id: int, token: str | None = None, user_id: int | None = None
    ):
        """Propose a one click button to the user to unsubscribe as defined in
        rfc8058. Only POST method is allowed preventing the risk that anti-spam
        trigger unwanted unsubscribe (scenario explained in the same rfc). Note:
        this method must support encoding method 'multipart/form-data' and
        'application/x-www-form-urlencoded'.
        """
        # not `self.digest_unsubscribe(...)`: that renders a full portal page
        # for a caller -- an MUA's unsubscribe robot -- that reads the status
        # code and discards the body.
        self._unsubscribe(digest_id, token=token, user_id=user_id)
        return Response(status=200)

    @route(
        "/digest/<int:digest_id>/unsubscribe",
        type="http",
        website=True,
        auth="public",
        methods=["GET", "POST"],
    )
    def digest_unsubscribe(self, digest_id, token=None, user_id=None, one_click=None):
        """Unsubscribe a given user from a given digest

        :param int digest_id: id of digest to unsubscribe from
        :param str token: token preventing URL forgery
        :param user_id: id of user to unsubscribe

        :param str one_click: set it to 1 when using the URL in the header of
          the email to allow mail user agent to propose a one click button to the
          user to unsubscribe as defined in rfc8058. When set to True, only POST
          method is allowed preventing the risk that anti-spam trigger unwanted
          unsubscribe (scenario explained in the same rfc). Note: this method
          must support encoding method 'multipart/form-data' and 'application/x-www-form-urlencoded'.
          NOTE: DEPRECATED PARAMETER
        """
        if one_click and int(one_click) and request.httprequest.method != "POST":
            raise Forbidden
        if request.httprequest.method != "POST":
            # the link in the mail body: a scanner or a preview opening it
            # must not unsubscribe anyone, so the page asks first
            return request.render(
                "digest.portal_digest_unsubscribe_confirm",
                {
                    "digest": self._unsubscribe_target(digest_id, token, user_id)[0],
                    "token": token,
                    # not "user_id": portal_layout reads that name as the
                    # visitor's res.users
                    "unsubscribe_user_id": user_id,
                },
            )

        digest_sudo = self._unsubscribe(digest_id, token=token, user_id=user_id)
        return request.render(
            "digest.portal_digest_unsubscribed",
            {
                "digest": digest_sudo,
            },
        )

    def _unsubscribe(self, digest_id, token=None, user_id=None):
        """Drop one user from one digest, or raise NotFound.

        :return: the digest, as sudo, for the caller to render
        """
        digest_sudo, user_sudo = self._unsubscribe_target(digest_id, token, user_id)
        if user_sudo:
            digest_sudo._action_unsubscribe_users(user_sudo)
        else:
            digest_sudo.action_unsubscribe()
        return digest_sudo

    def _unsubscribe_target(self, digest_id, token, user_id):
        """(digest, the user its token names) as sudo, the user empty for the
        signed-in internal user's own unsubscription, or raise NotFound."""
        digest_sudo = request.env["digest.digest"].sudo().browse(digest_id).exists()
        if not digest_sudo:
            raise NotFound
        if token and user_id:
            if not digest_sudo._is_unsubscribe_token(int(user_id), token):
                raise NotFound
            return digest_sudo, request.env["res.users"].sudo().browse(int(user_id))
        if not token and not user_id and not request.env.user.share:
            # old route was given without any token or user_id but only for auth users
            return digest_sudo, request.env["res.users"]
        raise NotFound

    @route(
        "/digest/<int:digest_id>/set_periodicity",
        type="http",
        website=True,
        auth="user",
    )
    def digest_set_periodicity(self, digest_id, periodicity="weekly"):
        if not request.env.user.has_group("base.group_erp_manager"):
            raise Forbidden
        if periodicity not in PERIODICITIES:
            raise NotFound

        digest = request.env["digest.digest"].browse(digest_id).exists()
        if not digest:
            # `.exists()` on a deleted id used to fall through to a redirect at
            # /odoo/digest.digest/False
            raise NotFound
        digest.action_set_periodicity(periodicity)

        return request.redirect(f"/odoo/{digest._name}/{digest.id}")
