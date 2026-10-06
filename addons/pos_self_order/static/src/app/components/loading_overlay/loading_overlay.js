/** @odoo-module native */
import { Component, onMounted, proxy, useProps } from "@odoo/owl";

export class LoadingOverlay extends Component {
    static template = "pos_self_order.LoadingOverlay";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            loading: false,
        });

        onMounted(() => {
            setTimeout(() => {
                this.state.loading = true;
            }, 200);
        });
    }
}
