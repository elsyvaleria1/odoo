from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import Controller, Response, request, route

from odoo.addons.digest.models.digest import PERIODICITIES


class DigestController(Controller):
    @route(
        [
            "/digest/<int:digest_id>/unsubscribe_oneclick",
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
        if one_click and int(one_click) and request.httprequest.method != "POST":
            raise Forbidden
        if request.httprequest.method != "POST":
            return request.render(
                "digest.portal_digest_unsubscribe_confirm",
                {
                    "digest": self._unsubscribe_target(digest_id, token, user_id)[0],
                    "token": token,
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
        digest_sudo, user_sudo = self._unsubscribe_target(digest_id, token, user_id)
        if user_sudo:
            digest_sudo._action_unsubscribe_users(user_sudo)
        else:
            digest_sudo.action_unsubscribe()
        return digest_sudo

    def _unsubscribe_target(self, digest_id, token, user_id):
        digest_sudo = request.env["digest.digest"].sudo().browse(digest_id).exists()
        if not digest_sudo:
            raise NotFound
        if token and user_id:
            if not digest_sudo._is_unsubscribe_token(int(user_id), token):
                raise NotFound
            return digest_sudo, request.env["res.users"].sudo().browse(int(user_id))
        if not token and not user_id and not request.env.user.share:
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
            raise NotFound
        digest.action_set_periodicity(periodicity)

        return request.redirect(f"/odoo/{digest._name}/{digest.id}")
