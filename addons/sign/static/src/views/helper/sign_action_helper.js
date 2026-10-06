/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useSignViewButtons } from "@sign/views/hooks";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

export class SignActionHelper extends Component {
    static template = "sign.SignActionHelper";
    static props = { resModel: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");
        this.fileInput = elementRef();
        const functions = useSignViewButtons(this, this.fileInput);
        Object.assign(this, functions);
    }

    onClickUpload(context) {
        return this.requestFile(context);
    }

    onClickSampleSign() {
        return this.actionService.doAction("sign.sign_template_tour_trigger_action");
    }
}
