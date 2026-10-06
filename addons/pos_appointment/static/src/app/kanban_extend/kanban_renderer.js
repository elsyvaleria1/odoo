/** @odoo-module native */
import { compareDates } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer } from "@web/views/kanban";

import { PosKanbanHeader } from "./kanban_header.js";
import { PosKanbanRecord } from "./kanban_record.js";

export class PosKanbanRenderer extends KanbanRenderer {
    static template = "pos_restaurant_appointment.KanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        KanbanRecord: PosKanbanRecord,
        KanbanHeader: PosKanbanHeader,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    /** @param {{ list: { records: any[] } }} group */
    sortedRecords(group) {
        return [...group.list.records].sort((a, b) =>
            compareDates(a.data.start, b.data.start),
        );
    }
}
