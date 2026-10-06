/** @odoo-module native */
import { Base } from "@point_of_sale/app/models/related_models";
import { registry } from "@web/core/registry";
export class PosPrepStage extends Base {
    static pythonModel = "pos.prep.stage";

    setup(vals) {
        super.setup(vals);
        this.recallHistory = [];
    }
}

registry.category("pos_available_models").add(PosPrepStage.pythonModel, PosPrepStage);
