/** @odoo-module native */
import { onMounted, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { RadioField, radioField } from "@web/fields/selection/radio/radio_field";

class OnlineAccountRadio extends RadioField {
    static template = "account_online_synchronization.OnlineAccountRadio";
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = proxy({ balances: {} });

        onMounted(async () => {
            this.state.balances = await this.loadData();
            this.onChange(this.items[0]);
        });
    }

    async loadData() {
        const ids = this.items.map((i) => i[0]);
        return await this.orm.call("account.online.account", "get_formatted_balances", [
            ids,
        ]);
    }

    getBalanceName(itemID) {
        return this.state.balances?.[itemID]?.[0] ?? "Loading ...";
    }

    isNegativeAmount(itemID) {
        return this.state.balances?.[itemID]?.[1] < 0;
    }
}

registry.category("fields").add("online_account_radio", {
    ...radioField,
    component: OnlineAccountRadio,
});
