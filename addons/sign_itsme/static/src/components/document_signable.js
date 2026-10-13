/** @odoo-module native */
import { Document } from "@sign/components/sign_request/document_signable";
import { SignablePDFIframe } from "@sign/components/sign_request/signable_PDF_iframe";
import { ItsmeDialog } from "@sign_itsme/dialogs/itsme_dialog";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/ui/dialog";

patch(SignablePDFIframe.prototype, {
    postRender() {
        const res = super.postRender();
        const errorCode = this.props.errorCode;
        if (errorCode) {
            const [errorMessage, title] = processErrorMessage.call(this, errorCode);
            this.dialog.add(
                AlertDialog,
                {
                    title: title || _t("Error"),
                    body: errorMessage,
                },
                {
                    onClose: () => {
                        deleteQueryParamFromURL("error_message");
                    },
                },
            );
        }
        return res;
    },
});

patch(Document.prototype, {
    async getAuthDialog() {
        if (this.authMethod === "itsme") {
            const credits = await rpc("/itsme/has_itsme_credits");
            if (credits) {
                const [route, params] = await this._getRouteAndParams();
                return {
                    component: ItsmeDialog,
                    props: {
                        route,
                        params,
                        onSuccess: () => {
                            this.openThankYouDialog();
                        },
                    },
                };
            }
        }
        return super.getAuthDialog();
    },

    getDataFromHTML() {
        super.getDataFromHTML();
        const { el: parentEl } = this.props.parent;
        this.errorMessage = parentEl.querySelector("#o_sign_show_error_message")?.value;
    },

    getIframeProps(sign_document_id) {
        const props = super.getIframeProps(sign_document_id);
        return {
            ...props,
            errorMessage: this.errorMessage,
        };
    },
});

function deleteQueryParamFromURL(param) {
    const url = new URL(location.href);
    url.searchParams.delete(param);
    window.history.replaceState(null, "", url);
}

/**
 * @param { String } errorMessage
 * @returns { [String, Boolean] }
 */
function processErrorMessage(errorMessage) {
    const defaultTitle = false;
    const errorMap = {
        err_connection_odoo_instance: [
            _t(
                "The itsme® identification data could not be forwarded to Odoo, the signature could not be saved.",
            ),
            defaultTitle,
        ],
        access_denied: [
            _t(
                "You have rejected the identification request or took too long to process it. You can try again to finalize your signature.",
            ),
            _t("Identification refused"),
        ],
    };
    return errorMap[errorMessage]
        ? errorMap[errorMessage]
        : [errorMessage, defaultTitle];
}
