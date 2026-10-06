import hmac
from hashlib import sha256

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    emsigner_status = fields.Char(
        string="emSigner Status",
        copy=False,
        readonly=True,
    )
    emsigner_return_value = fields.Char(
        string="emSigner Values",
        copy=False,
        readonly=True,
    )
    emsigner_transaction_number = fields.Char(
        string="emSigner Transaction Number",
        copy=False,
        readonly=True,
    )
    emsigner_reference_number = fields.Char(
        string="emSigner Reference Number",
        copy=False,
        readonly=True,
    )
    emsigner_signer_name = fields.Char(
        string="emSigner Certified Signer",
        copy=False,
        readonly=True,
    )
    emsigner_document_sha256 = fields.Char(
        copy=False,
        readonly=True,
    )
    emsigner_document_size = fields.Integer(
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        if not items:
            return items

        for related_records in items.grouped("sign_request_id").values():
            emsigner_roles = related_records.filtered(
                lambda r: r.role_id and r.role_id.auth_method == "emsigner"
            ).role_id

            # If there are multiple emsigner roles or user is doing sign now, we do not set auth_method
            if emsigner_roles:
                if len(emsigner_roles) > 1:
                    emsigner_roles.auth_method = False
                else:
                    emsigner_record = related_records.filtered_domain(
                        [("role_id", "in", emsigner_roles.ids)]
                    )
                    # must have signature items & only one document
                    if emsigner_record and (
                        not emsigner_record._get_current_signature_sign_items()
                        or len(emsigner_record.sign_request_id.template_id.document_ids)
                        > 1
                    ):
                        emsigner_record.role_id.auth_method = False
                    else:
                        # when we have multiple signers, we always keep the emsigner role last in the order
                        # and set the normal signers first
                        normal_signers = related_records - emsigner_record

                        normal_signers = normal_signers.sorted(
                            key=lambda r: r.mail_sent_order or 1
                        )
                        # normal signers first
                        for idx, signer in enumerate(normal_signers, start=1):
                            signer.mail_sent_order = idx

                        # Then emsigners get the last order(s)
                        last_order = len(normal_signers) + 1
                        emsigner_record.mail_sent_order = last_order
        return items

    def _get_current_signature_sign_items(self):
        """Get the sign items that are of type signature and are assigned to the current role."""
        return self.sign_request_id.template_id.sign_item_ids.filtered(
            lambda item: (
                item.responsible_id.id == self.role_id.id
                and item.type_id.item_type == "signature"
            )
        )

    def _write_emsigner_data(
        self, reference_number, transaction_number, return_status, signer_name
    ) -> None:
        self.check_singleton()
        if (
            self.emsigner_status
            or self.emsigner_transaction_number
            or self.emsigner_reference_number
        ):
            return
        self.write(
            {
                "emsigner_status": return_status,
                "emsigner_transaction_number": transaction_number,
                "emsigner_reference_number": reference_number,
                "emsigner_signer_name": signer_name,
                "emsigner_document_sha256": False,
                "emsigner_document_size": 0,
            }
        )

    def _emsigner_sent_document_matches(self, signed_pdf, contents_offset) -> bool:
        self.check_singleton()
        size = self.emsigner_document_size
        return bool(
            self.emsigner_document_sha256
            and 0 < size < contents_offset
            and hmac.compare_digest(
                sha256(signed_pdf[:size]).hexdigest(), self.emsigner_document_sha256
            )
        )

    def _post_fill_request_item(self):
        for sri in self:
            if (
                sri.role_id.auth_method == "emsigner"
                and not sri.emsigner_status
                and not sri.signed_without_extra_auth
            ):
                raise ValidationError(
                    self.env._("Sign request item is not validated yet.")
                )
        return super()._post_fill_request_item()

    def sign(self, signature, **kwargs):
        if self.role_id.auth_method == "emsigner":
            return self._sign(
                signature,
                validation_required=not self.signed_without_extra_auth,
                **kwargs,
            )
        return super().sign(signature, **kwargs)
