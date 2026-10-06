/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { useService } from "@web/core/utils/hooks";

export class DeliveryButton extends Component {
    static template = "pos_urban_piper.DeliveryButton";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.pos = usePos();
        this.ui = useService("ui");
    }

    async handleToggle(providerCode) {
        const toggleStatus = !this.pos.enabledProviders[providerCode];
        this.pos.enabledProviders[providerCode] = toggleStatus;
        await this.pos.saveProviderState(this.pos.enabledProviders);
        await this.pos.updateStoreStatus(toggleStatus, providerCode);
    }

    goToOrders(deliveryProvider, upState, filter = "ONGOING") {
        const stateOverride = {
            search: {
                fieldName: "DELIVERYPROVIDER",
                searchTerm: deliveryProvider,
            },
            filter: filter,
        };
        if (this.pos.router.state.current === "TicketScreen") {
            this.ui.block();
            this.pos.ticket_screen_mobile_pane = "left";
            setTimeout(() => {
                this.pos.navigate("TicketScreen", {
                    stateOverride: stateOverride,
                    upState,
                });
                this.ui.unblock();
            }, 300);
            return;
        }
        this.pos.navigate("TicketScreen", { stateOverride: stateOverride, upState });
    }
}
