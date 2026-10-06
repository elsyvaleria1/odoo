/** @odoo-module native */
import { ListRenderer } from "@web/views/list";

export class EsgCarbonEmissionListRenderer extends ListRenderer {
    get canCreate() {
        return false;
    }
}
