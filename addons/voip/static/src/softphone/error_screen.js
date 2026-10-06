/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class ErrorScreen extends Component {
    static props = {
        title: t.string().optional(_t("Something went wrong 😵‍💫")),
        isNonBlocking: t.boolean().optional(false),
        message: t.string(),
        button: t.object({ callback: t.function(), text: t.string() }).optional(),
    };
    static template = "voip.ErrorScreen";
    props = useProps(this.constructor.props);

    setup() {
        this.voip = useService("voip");
    }

    onClick() {
        if (this.props.isNonBlocking) {
            this.voip.resolveError();
        }
    }
}
