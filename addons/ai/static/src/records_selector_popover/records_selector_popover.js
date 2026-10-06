/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { MultiRecordSelector } from "@web/components/record_selectors";

export class RecordsSelectorPopover extends Component {
    static components = { MultiRecordSelector };
    static template = "ai.RecordsSelectorPopover";
    static props = {
        resModel: t.string(),
        close: t.function(),
        domain: t.array().optional(),
        validate: t.function(),
        resIds: t.array().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            resIds: this.props.resIds || [],
        });
    }

    update(resIds) {
        this.state.resIds = resIds;
    }

    validate() {
        this.props.validate(this.state.resIds);
        this.props.close();
    }
}
