/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { addLoadingEffect } from "@web/core/utils/dom/ui";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog, Dialog } from "@web/ui/dialog";

export class EmsignerDialog extends Component {
    static template = "sign_emsigner.EmsignerDialog";
    static components = {
        Dialog,
    };
    static props = {
        route: t.string(),
        params: t.object(),
        onSuccess: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.dialog = useService("dialog");
    }

    async onEmsignerClick() {
        const submitEl = document.querySelector(".o_emsigner_submit");
        addLoadingEffect(submitEl);
        const { success, authorization_url, params, message } = await rpc(
            this.props.route,
            this.props.params,
        );
        if (success) {
            if (authorization_url) {
                const form = document.createElement("form");
                form.method = "POST";
                form.action = authorization_url;

                let index = 1;
                for (const key in params) {
                    if (Object.hasOwn(params, key)) {
                        const hiddenField = document.createElement("input");
                        hiddenField.type = "hidden";
                        hiddenField.name = "Parameter" + index;
                        hiddenField.value = params[key];
                        form.appendChild(hiddenField);
                        index++;
                    }
                }
                document.body.appendChild(form);
                form.submit();
            } else {
                this.props.onSuccess();
            }
        } else {
            this.dialog.add(
                AlertDialog,
                {
                    body: message,
                },
                {
                    onClose: () => window.location.reload(),
                },
            );
        }
    }
}
