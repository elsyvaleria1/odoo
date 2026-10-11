/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class BackorderDialog extends Component {
    static components = { Dialog };
    static props = {
        displayUoM: t.boolean(),
        uncompletedLines: t.array(),
        onApply: t.function(),
        close: t.function(),
    };
    static template = "stock_barcode.BackorderDialog";
    props = useProps(this.constructor.props);
    state = proxy({ applying: false });

    async _onApply() {
        if (this.state.applying) {
            return;
        }
        this.state.applying = true;
        try {
            await this.props.onApply();
        } finally {
            this.state.applying = false;
        }
        this.props.close();
    }
}
