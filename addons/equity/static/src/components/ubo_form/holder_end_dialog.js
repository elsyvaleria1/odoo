/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";

export class HolderEndDialog extends Component {
    static template = "equity.HolderEndDialog";
    static components = { Dialog };
    static props = { ubo: t.object(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            ubo: this.props.ubo,
            endDate: this.props.ubo["end_date"],
        });
    }

    confirm() {
        this.state.ubo["end_date"] = this.state.endDate;
        this.props.close();
    }

    get title() {
        return _t("Function end: %s", this.state.ubo["holder_id"]["name"]);
    }
}
