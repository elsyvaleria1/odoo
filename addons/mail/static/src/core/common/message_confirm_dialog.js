// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";

import { discussComponentRegistry } from "./discuss_component_registry.js";

const log = makeLogger("mail.message.ui");

export class MessageConfirmDialog extends Component {
    static components = { Dialog };
    static props = {
        close: t.any(),
        confirmColor: t.any().optional("btn-primary"),
        confirmText: t.any().optional(_t("Delete")),
        message: t.any(),
        prompt: t.any(),
        size: t.any().optional("xl"),
        title: t
            .any()
            .optional(_t("Send this message to the great trash can in the sky?")),
        onConfirm: t.any(),
    };
    static template = "mail.MessageConfirmDialog";
    props = useProps(this.constructor.props);

    get messageComponent() {
        return discussComponentRegistry.get("Message");
    }

    onClickConfirm() {
        log.logic("confirm", () => ({ messageId: this.props.message?.id }));
        this.props.onConfirm();
        this.props.close();
    }
}

discussComponentRegistry.add("MessageConfirmDialog", MessageConfirmDialog);
