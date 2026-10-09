/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

/**
 * The signer proves it is them with a code sent to their own email or
 * Telegram, before their signature is submitted.
 */
export class ProofSignerDialog extends Component {
    static template = "sign_proof.ProofSignerDialog";
    static components = { Dialog };
    static props = {
        postValidation: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.signInfo = useService("signInfo");
        this.codeInput = elementRef();
        this.state = proxy({ sending: false, sentTo: "", error: "", challenge: null });
    }

    async sendCode() {
        this.state.sending = true;
        this.state.error = "";
        const route = `/sign/proof/${encodeURIComponent(
            this.signInfo.get("documentId"),
        )}/${encodeURIComponent(this.signInfo.get("signRequestItemToken"))}`;
        try {
            const result = await rpc(route);
            if (result.error) {
                this.state.error = result.error;
            } else {
                this.state.challenge = result;
                this.state.sentTo = result.sent_to;
            }
        } finally {
            this.state.sending = false;
        }
    }

    async validate() {
        const code = this.codeInput.el?.value.trim();
        if (!code || !this.state.challenge) {
            this.codeInput.el?.classList.add("is-invalid");
            return;
        }
        await this.props.postValidation({
            token: this.state.challenge.token,
            method: this.state.challenge.method,
            code,
        });
        this.props.close();
    }

    get dialogProps() {
        return {
            size: "md",
            title: _t("Confirm it is you"),
            fullscreen: this.ui.isSmall,
        };
    }
}
