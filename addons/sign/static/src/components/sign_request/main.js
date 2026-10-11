/** @odoo-module native */
import { whenReady } from "@odoo/owl";
import { initDocumentToSign } from "@sign/components/sign_request/document_signable";

whenReady(() => {
    if (document.querySelector(".o_sign_document")) {
        initDocumentToSign(document);
    }
});
