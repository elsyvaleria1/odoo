/** @odoo-module native */
import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/fields/basic/float/float_field";

export class MrpPlmUpdateQty extends FloatField {
    static template = "mrp_plm.UpdateQty";
}

export const mrpPlmUpdateQty = {
    ...floatField,
    component: MrpPlmUpdateQty,
    displayName: "MRP PLM Update Quantity",
};

registry.category("fields").add("plm_upd_qty", mrpPlmUpdateQty);
