// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { provideDebugContext, useDebugMode } from "@web/core/debug/debug_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Dialog } from "@web/ui/dialog";
import { DebugMenu } from "@web/webclient/debug/debug_menu";

const log = makeLogger("web.action.dialog");

export class ActionDialog extends Dialog {
    static components = {
        .../** @type {any} */ (Dialog).components,
        DebugMenu,
    };
    static template = "web.ActionDialog";
    static props = {
        .../** @type {any} */ (Dialog).props,
        close: t.function(),
        slots: t.any().optional(),
        ActionComponent: t.any().optional(),
        actionProps: t.any().optional(),
        actionType: t.any().optional(),
        title: t.any().optional("Odoo"),
        withBodyPadding: Dialog.props.withBodyPadding.optional(false),
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        provideDebugContext();
        log.logic("header", () => ({
            fullscreen: this.isFullscreen,
            fullscreenProp: this.props.fullscreen,
            isSmall: this.ui.isSmall,
        }));
    }
}
