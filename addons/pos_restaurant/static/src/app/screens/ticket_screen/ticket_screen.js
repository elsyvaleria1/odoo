/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { logPosMessage } from "@point_of_sale/app/utils/pretty_console_log";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.utils = useService("contextual_utils_service");
    },

    _getScreenToStatusMap() {
        return Object.assign(super._getScreenToStatusMap(...arguments), {
            PaymentScreen: this.pos.config.set_tip_after_payment
                ? "OPEN"
                : super._getScreenToStatusMap(...arguments).PaymentScreen,
            TipScreen: "TIPPING",
        });
    },
    getTableTag(order) {
        return order.table_id?.table_number;
    },
    getTable(order) {
        const table = order.getTable();
        if (table) {
            let floorAndTable = "";

            if (this.pos.models["restaurant.floor"].length > 0) {
                floorAndTable = `${table.floor_id.name}/`;
            }

            floorAndTable += table.getName();
            return floorAndTable;
        }
    },
    _getSearchFields() {
        const res = super._getSearchFields(...arguments);
        if (this.pos.config.module_pos_restaurant) {
            res.REFERENCE.modelFields.push("table_id.table_number");
        }
        return res;
    },
    async setOrder(order) {
        const shouldBeOverridden =
            this.pos.config.module_pos_restaurant && order.table_id;
        if (shouldBeOverridden) {
            const orderTable = order.getTable();
            await this.pos.setTable(orderTable, order.uuid);
        }
        return await super.setOrder(order);
    },
    async settleTips() {
        const promises = [];
        for (const order of this.getFilteredOrderList()) {
            const amount = this.utils.parseValidFloat(
                order.uiState.TipScreen.inputTipAmount,
            );

            if (!order.isSynced) {
                logPosMessage(
                    "TicketScreen",
                    "settleTips",
                    `${order.name} is not yet sync. Sync it to server before setting a tip.`,
                );
                continue;
            }

            order.state = "draft";
            this.pos.selectedOrderUuid = order.uuid;
            await this.pos.setTip(amount);
            order.state = "paid";
            order.uiState.screen_data.value = { name: "", props: {} };

            const tipLine = order.getSelectedOrderline();
            const tipAmount = tipLine.price_unit;
            const serializedTipLine = tipLine.serializeForORM();
            tipLine.delete();

            promises.push(
                (async () => {
                    await this.pos.data.create("pos.order.line", [serializedTipLine]);
                    await this.pos.data.write("pos.order", [order.id], {
                        is_tipped: true,
                        tip_amount: tipAmount,
                    });
                })(),
            );
        }

        await Promise.all(promises);
    },
    _getOrderStates() {
        const result = super._getOrderStates(...arguments);
        if (this.pos.config.set_tip_after_payment) {
            result.delete("PAYMENT");
            result.set("OPEN", { text: _t("Open"), indented: true });
            result.set("TIPPING", { text: _t("Tipping"), indented: true });
        }
        return result;
    },
    isDefaultOrderEmpty(order) {
        if (this.pos.config.module_pos_restaurant) {
            return false;
        }
        return super.isDefaultOrderEmpty(...arguments);
    },
});

export class TipCell extends Component {
    static template = "pos_restaurant.TipCell";
    static props = { order: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.utils = useService("contextual_utils_service");
        this.state = proxy({ isEditing: false });
        this.orderUiState = this.props.order.uiState.TipScreen;
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
    }
    get tipAmountStr() {
        return this.utils.formatCurrency(
            this.utils.parseValidFloat(this.orderUiState.inputTipAmount),
        );
    }
    onBlur() {
        this.state.isEditing = false;
    }
    onKeydown(event) {
        if (event.key === "Enter") {
            this.state.isEditing = false;
        }
    }
    editTip() {
        this.state.isEditing = true;
    }
}

patch(TicketScreen, {
    components: { ...TicketScreen.components, TipCell },
});
