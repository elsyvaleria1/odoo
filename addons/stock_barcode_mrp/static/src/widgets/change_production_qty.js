/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class ChangeProductionQty extends Component {
    static template = "stock_barcode_mrp.ChangeProductionQty";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
    }

    openChangeQtyWizard() {
        this.actionService.doAction("mrp.action_change_production_qty", {
            additionalContext: {
                default_product_qty: this.props.value,
                default_mo_id: this.props.record.resId,
            },
            onClose: async () => await this.props.record.model.load(),
        });
    }
}

export const ChangeProductionQtyButton = {
    component: ChangeProductionQty,
};
registry.category("fields").add("change_production_qty", ChangeProductionQtyButton);
