/** @odoo-module native */
import { provideMailContext } from "@mail/utils/common/mail_context";
import { EventBus, t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";

export class SignSendRequestController extends formView.Controller {
    static props = {
        ...formView.Controller.props,
        fullComposerBus: t.instanceOf(EventBus).optional(new EventBus()),
    };
    setup() {
        super.setup();
        provideMailContext({
            fullComposerBus: this.props.fullComposerBus,
        });
    }
}

registry.category("views").add("sign_send_request_form", {
    ...formView,
    Controller: SignSendRequestController,
});
