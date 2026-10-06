/** @odoo-module native */
import { Base } from "@point_of_sale/app/models/related_models";
import { computeDurationSinceDate } from "@pos_enterprise/app/utils/utils";
import { registry } from "@web/core/registry";
export class PosPrepOrder extends Base {
    static pythonModel = "pos.prep.order";

    getDurationSinceFireDate() {
        return computeDurationSinceDate(this.pos_course_id.fired_date);
    }
}

registry.category("pos_available_models").add(PosPrepOrder.pythonModel, PosPrepOrder);
