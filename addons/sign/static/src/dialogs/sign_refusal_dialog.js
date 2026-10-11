/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { isEmail } from "@web/core/utils/format/strings";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog, Dialog } from "@web/ui/dialog";

import { ThankYouDialog } from "./thank_you_dialog.js";

export class SignRefusalDialog extends Component {
    static template = "sign.SignRefusalDialog";
    static components = {
        Dialog,
    };
    static props = { close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.refuseNameEl = elementRef();
        this.refuseEmailEl = elementRef();
        this.refuseReasonEl = elementRef();
        this.refuseButton = elementRef();
        this.dialog = useService("dialog");
        this.signInfo = useService("signInfo");
        this.user = user.userId;
        this.isPublicUser = !this.user;
    }

    get dialogProps() {
        return {
            size: "md",
            title: _t("Decline to sign"),
        };
    }

    checkForChanges() {
        const refusal = {
            reason: this.refuseReasonEl.el.value.trim(),
            name: this.isPublicUser && this.refuseNameEl.el.value.trim(),
            email: this.isPublicUser && this.refuseEmailEl.el.value.trim(),
        };
        const isRefusalReasonEmpty = refusal.reason.length === 0;
        const isPublicUserUnindentified =
            this.isPublicUser && (!refusal.name || !refusal.email);

        this.refuseButton.el.disabled =
            isRefusalReasonEmpty || isPublicUserUnindentified;
    }

    async refuse() {
        const reason = this.refuseReasonEl.el.value;
        const route = `/sign/refuse/${this.signInfo.get("documentId")}/${this.signInfo.get(
            "signRequestItemToken",
        )}`;
        let params = {
            refusal_reason: reason,
        };

        if (!this.user) {
            const name = this.refuseNameEl.el.value;
            const email = this.refuseEmailEl.el.value;

            if (!email || !isEmail(email)) {
                this.refuseEmailEl.el.classList.add("is-invalid");
                return;
            }

            params = {
                ...params,
                refusal_name: name,
                refusal_email: email,
            };
        }

        const response = await rpc(route, params);
        if (!response) {
            this.dialog.add(
                AlertDialog,
                {
                    body: _t("Sorry, you cannot refuse this document"),
                },
                {
                    onClose: () => window.location.reload(),
                },
            );
            this.props.close();
            return;
        }
        this.dialog.add(SignRefusalDialogTitle, { isRefused: true });

        this.props.close();
    }
}

export class SignRefusalDialogTitle extends ThankYouDialog {
    static template = "sign.SignRefusalDialogTitle";
    setup() {
        super.setup();
        this.message = this.props.message || _t("Document refusal submitted.");
        this.dialog = useService("dialog");
    }
}
