/** @odoo-module native */
import { Document } from "@sign/components/sign_request/document_signable";
import { ProofSignerDialog } from "@sign_proof/dialogs/proof_signer_dialog";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/ui/dialog";

patch(Document.prototype, {
    async getAuthDialog() {
        if (this.authMethod === "proof" && !this.signatureInfo.proof) {
            return {
                component: ProofSignerDialog,
                props: {
                    postValidation: (proof) => {
                        this.signatureInfo.proof = proof;
                        return this._signDocuments();
                    },
                },
            };
        }
        return super.getAuthDialog();
    },

    _getRouteAndParams() {
        const [route, params] = super._getRouteAndParams();
        if (this.signatureInfo.proof) {
            params.proof = this.signatureInfo.proof;
        }
        return [route, params];
    },

    onSignError(response) {
        if (!response.proof) {
            return super.onSignError(response);
        }
        this.signatureInfo.proof = undefined;
        this.dialog.add(AlertDialog, {
            title: _t("Error"),
            body:
                response.message ||
                _t("Your signature was not submitted: confirm it is you with a code."),
        });
    },
});
