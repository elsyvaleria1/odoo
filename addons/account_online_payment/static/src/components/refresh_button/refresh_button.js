/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class RefreshButton extends Component {
    static template = "account_online_payment.RefreshButton";
    static props = { name: t.any(), id: t.any(), record: t.any(), readonly: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            status: this.props.record.data.payment_online_status,
            isFetching: false,
        });
        this.orm = useService("orm");
    }

    async onClickFetchStatus() {
        this.state.isFetching = true;

        const response = await this.orm.call(
            "account.batch.payment",
            "check_online_payment_status",
            [this.props.record.data.id],
        );

        this.state.status = response[this.props.record.data.id];
        this.state.isFetching = false;
    }
}

export const refreshButtonComp = {
    component: RefreshButton,
};

registry
    .category("fields")
    .add("account_online_payment_refresh_button", refreshButtonComp);
