from typing import Any

from odoo import fields, models

SIGNER_PURPOSE = "sign.request.item.sign"


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    proof_evidence_id = fields.Many2one(
        comodel_name="proof.evidence",
        string="Signer's Proof",
        copy=False,
        readonly=True,
        classification="sign.signing_trace",
        groups="sign.group_sign_manager",
        help="The code the signer received on their own email or Telegram and "
        "typed in to sign: it covers this signer and the documents as sent.",
    )

    def _get_signer_evidence(self) -> str | bool:
        return self.proof_evidence_id.hash or super()._get_signer_evidence()

    def _get_signer_proof_facts(self) -> dict[str, Any]:
        self.check_singleton()
        sign_request = self.sign_request_id
        return {
            "request": sign_request.id,
            "item": self.id,
            "signer": self.partner_id.id,
            "documents": self.env["sign.log"]._get_file_digests(
                {"sign_request_id": sign_request.id, "action": "create"}
            ),
        }

    def _get_signer_proof_summary(self) -> list[list[str]]:
        self.check_singleton()
        sign_request = self.sign_request_id
        env = self.with_context(lang=self.partner_id.lang or self.env.lang).env
        return [
            [env._("Document"), sign_request.reference],
            [env._("Requested by"), sign_request.create_uid.name],
        ]

    def _with_requester(self) -> SignRequestItem:
        requester = self.sign_request_id.create_uid
        if not requester._is_internal():
            requester = self.env.ref("base.user_root")
        return self.with_env(self.env(user=requester.id, su=False))

    def _issue_signer_proof(self) -> dict[str, Any]:
        self.check_singleton()
        item = self._with_requester()
        challenges = item.env["proof.challenge"]
        return challenges._issue(
            item,
            SIGNER_PURPOSE,
            self._get_signer_proof_facts(),
            item.env["proof.method"].search([("mode", "=", "submit")]),
            summary=self._get_signer_proof_summary(),
            partner=self.partner_id,
        )

    def _redeem_signer_proof(self, proof: dict[str, Any]) -> None:
        self.check_singleton()
        item = self._with_requester()
        evidence = item.env["proof.challenge"]._redeem(
            proof.get("token"),
            proof.get("method"),
            {"code": proof.get("code")},
            item,
            SIGNER_PURPOSE,
            self._get_signer_proof_facts(),
        )
        self.proof_evidence_id = evidence.id
        self.sign_request_id._message_log(
            body=self.env._(
                "%(signer)s proved it is them with the code sent to %(sent_to)s.",
                signer=self.partner_id.display_name,
                sent_to=evidence.payload.get("sent_to") or "-",
            )
        )
