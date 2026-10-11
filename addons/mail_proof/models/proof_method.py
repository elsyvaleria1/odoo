from urllib.parse import urlencode

from odoo import fields, models

from odoo.addons.proof.models.proof_challenge import LINK_GRACE


class ProofMethod(models.Model):
    _inherit = "proof.method"

    code = fields.Selection(
        selection_add=[
            ("email_code", "Email Code"),
            ("email_confirm", "Email Confirmation"),
        ],
        ondelete={"email_code": "cascade", "email_confirm": "cascade"},
    )

    def _is_enrolled(self, user: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code == "email_code":
            return bool(user.email_normalized)
        return super()._is_enrolled(user)

    def _is_enrolled_contact(self, partner: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code in ("email_code", "email_confirm"):
            return bool(partner.email_normalized)
        return super()._is_enrolled_contact(partner)

    def _deliver_confirmation(
        self, challenge: models.BaseModel, reminder: bool = False
    ) -> models.BaseModel:
        self.check_singleton()
        if self.code != "email_confirm":
            return super()._deliver_confirmation(challenge, reminder=reminder)
        signer = challenge.partner_id
        delivery = self.env["proof.delivery"].create(
            {
                "challenge_id": challenge.id,
                "method_id": self.id,
                "sent_to": self._mask_email(signer.email_normalized),
                "address": signer.email_normalized,
            }
        )
        _link, token = self.env["access.link"]._issue(
            delivery,
            partner=signer,
            role="comment",
            cause="request",
            date_to=challenge.date_expire + LINK_GRACE,
        )
        url = (
            f"{challenge.get_base_url()}/proof/answer/{delivery.id}"
            f"?{urlencode({'access_token': token})}"
        )
        lang = signer.lang or self.env.lang
        body = (
            self.env["ir.qweb"]
            .with_context(lang=lang)
            ._render(
                "mail_proof.email_confirm_body",
                {
                    "url": url,
                    "signer": signer,
                    "company": challenge.company_id or challenge.user_id.company_id,
                    "summary": challenge.summary or [],
                    "reminder": reminder,
                    "date_expire": challenge.date_expire,
                    "links": challenge._get_record_links(),
                },
            )
        )
        env = self.with_context(lang=lang).env
        self._send_mail(
            challenge,
            signer,
            env._("Reminder: please confirm") if reminder else env._("Please confirm"),
            body,
            queued=True,
        )
        return delivery

    def _uses_code(self) -> bool:
        self.check_singleton()
        return self.code == "email_code" or super()._uses_code()

    def _send_code(
        self, challenge: models.BaseModel, signer: models.BaseModel, code: str
    ) -> str:
        self.check_singleton()
        if self.code != "email_code":
            return super()._send_code(challenge, signer, code)
        lang = signer.lang or self.env.lang
        body = (
            self.env["ir.qweb"]
            .with_context(lang=lang)
            ._render(
                "mail_proof.email_code_body",
                {
                    "code": code,
                    "signer": signer,
                    "asker": challenge.user_id,
                    "summary": challenge.summary or [],
                },
            )
        )
        self._send_mail(
            challenge,
            signer,
            self.with_context(lang=lang).env._("Your confirmation code"),
            body,
        )
        return self._mask_email(signer.email_normalized)

    def _send_mail(
        self,
        challenge: models.BaseModel,
        signer: models.BaseModel,
        subject: str,
        body: str,
        queued: bool = False,
    ) -> None:
        mail = (
            self.env["mail.mail"]
            .with_privilege(
                "mail_proof.privilege_send_proof_code",
                reason="a proof request mails the signer what it asks them",
            )
            .create(
                {
                    "subject": subject,
                    "email_from": (
                        challenge.company_id
                        or challenge.user_id.company_id
                        or self.env.company
                    ).email_formatted
                    or challenge.user_id.email_formatted,
                    "email_to": signer.email_formatted,
                    "body_html": body,
                    "auto_delete": True,
                }
            )
        )
        if not queued:
            mail.send(raise_exception=False)

    def _mask_email(self, email: str) -> str:
        local, _at, domain = (email or "").partition("@")
        return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{domain}"
