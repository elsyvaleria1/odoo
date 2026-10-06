/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog, Dialog } from "@web/ui/dialog";

export class ItsmeDialog extends Component {
    static template = "sign_itsme.ItsmeDialog";
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

    async onItsmeClick() {
        const { success, authorization_url, message } = await rpc(
            this.props.route,
            this.props.params,
        );
        if (success) {
            if (authorization_url) {
                window.location.replace(authorization_url);
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
