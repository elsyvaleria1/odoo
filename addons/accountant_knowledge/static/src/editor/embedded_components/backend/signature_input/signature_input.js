/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { Component, t, useProps } from "@odoo/owl";
import { SignNameAndSignatureDialog } from "@sign/dialogs/dialogs";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class SignatureInputComponent extends Component {
    static template = "accountant_knowledge.EmbeddedSignatureInput";
    static props = { host: t.object(), replaceSignatureInputWithImage: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.dialog = useService("dialog");
    }

    openSignatureDialog() {
        const signature = { name: user.name };
        const close = this.dialog.add(SignNameAndSignatureDialog, {
            signature,
            activeFrame: true,
            frame: {},
            hash: "",
            displaySignatureRatio: 3,
            onConfirm: () => {
                this.props.replaceSignatureInputWithImage(
                    this.props.host,
                    signature.getSignatureImage(),
                );
                close();
            },
        });
    }
}

export const signatureInputEmbedding = {
    name: "signatureInput",
    Component: SignatureInputComponent,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
};
