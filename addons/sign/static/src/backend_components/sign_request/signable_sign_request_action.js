/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { SignRequest } from "@sign/backend_components/sign_request/sign_request_action";
import { SignableRequestControlPanel } from "@sign/backend_components/sign_request/signable_sign_request_control_panel";
import { Document } from "@sign/components/sign_request/document_signable";
import { SignablePDFIframe } from "@sign/components/sign_request/signable_PDF_iframe";
import { provideSignContext } from "@sign/sign_context";
import { registry } from "@web/core/registry";

export class SignableSignRequest extends SignRequest {
    static components = {
        ...SignableSignRequest.components,
        Document: Document,
        SignRequestControlPanel: SignableRequestControlPanel,
    };
    setup() {
        super.setup();
        this.signInfo.set({
            tokenList: this.tokenList,
            nameList: this.nameList,
        });
        provideSignContext({
            editWhileSigningBus: new EventBus(),
        });
    }

    get nameList() {
        return this.props.action.context.name_list;
    }

    get tokenList() {
        return this.props.action.context.token_list;
    }

    get documentProps() {
        return {
            ...super.documentProps,
            PDFIframeClass: SignablePDFIframe,
        };
    }
}

registry.category("actions").add("sign.SignableDocument", SignableSignRequest);
