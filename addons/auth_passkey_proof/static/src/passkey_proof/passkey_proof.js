// @ts-check
/** @odoo-module native */

import { passkeyLib } from "@auth_passkey/passkey_lib";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { proofMethodRegistry } from "@proof/proof_dialog/proof_dialog";

export class PasskeyProof extends Component {
    static template = "auth_passkey_proof.PasskeyProof";
    static props = {
        options: t.object(),
        busy: t.boolean(),
        prove: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ waiting: false, dismissed: false });
    }

    async onUsePasskey() {
        this.state.waiting = true;
        this.state.dismissed = false;
        let credential;
        try {
            credential = await passkeyLib.startAuthentication(this.props.options);
        } catch {
            // the user closed the prompt, or no authenticator answered
            this.state.dismissed = true;
            return;
        } finally {
            this.state.waiting = false;
        }
        await this.props.prove({ credential });
    }
}

proofMethodRegistry.add("passkey", { Component: PasskeyProof });
