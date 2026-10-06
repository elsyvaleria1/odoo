// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog/dialog";

import { NameAndSignature } from "./name_and_signature.js";
export class SignatureDialog extends Component {
    static template = "web.SignatureDialog";
    static components = { Dialog, NameAndSignature };
    static props = {
        defaultName: t.string().optional(""),
        nameAndSignatureProps: t.object(),
        uploadSignature: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    /** @type {{ name: any; isSignatureEmpty: boolean }} */
    signature;

    setup() {
        this.signature = proxy({
            name: this.props.defaultName,
            isSignatureEmpty: true,
        });
    }

    async onClickConfirm() {
        await this.props.uploadSignature({
            name: this.signature.name,
            signatureImage: /** @type {any} */ (this.signature).getSignatureImage(),
        });
        this.props.close();
    }

    get nameAndSignatureProps() {
        return {
            ...this.props.nameAndSignatureProps,
            signature: this.signature,
        };
    }
}
