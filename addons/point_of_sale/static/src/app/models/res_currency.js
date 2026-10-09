/** @odoo-module native */
import * as numbers from "@point_of_sale/app/utils/numbers";
import { registry } from "@web/core/registry";
import { roundPrecision } from "@web/core/utils/format/numbers";
export class ResCurrency extends numbers.AbstractNumbers {
    static pythonModel = "res.currency";
    get precision() {
        return this.rounding;
    }

    toMinorUnits(amount) {
        return roundPrecision(amount * 10 ** this.decimal_places, 1);
    }
}

registry.category("pos_available_models").add(ResCurrency.pythonModel, ResCurrency);
