/** @odoo-module native */
import { whenReady } from "@odoo/owl";
import { initDocumentToSign } from "@sign/components/sign_request/document_signable";

// Boot entry of the ``sign.assets_public_sign`` bundle: evaluated when the
// public doc_sign page loads its bundle, it mounts the signable-document app.
//
// Gate on the page's own root element so importing this module's namespace in
// another context (e.g. the hoot unit-test runner pulling in ``@sign/*``)
// does not start real services against the test page.
whenReady(() => {
    if (document.querySelector(".o_sign_document")) {
        initDocumentToSign(document);
    }
});
