/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { KanbanHeader } from "@web/views/kanban";

export class PosKanbanHeader extends KanbanHeader {
    static template = "pos_restaurant_appointment.KanbanHeader";

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    get totalCapacityReserved() {
        return this.props.group.list.records.reduce(
            (sum, record) => sum + record.data.waiting_list_capacity,
            0,
        );
    }
}
