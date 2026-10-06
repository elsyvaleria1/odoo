/** @odoo-module native */
import { RottingKanbanHeader } from "@mail/views/web/rotting/rotting_kanban_header";
import { RottingKanbanRecord } from "@mail/views/web/rotting/rotting_kanban_record";
import { RottingKanbanRenderer } from "@mail/views/web/rotting/rotting_kanban_renderer";

import { CrmColumnProgress } from "./crm_column_progress.js";

class CrmKanbanHeader extends RottingKanbanHeader {
    static components = {
        ...RottingKanbanHeader.components,
        ColumnProgress: CrmColumnProgress,
    };
}

export class CrmKanbanRenderer extends RottingKanbanRenderer {
    static components = {
        ...RottingKanbanRenderer.components,
        KanbanHeader: CrmKanbanHeader,
        KanbanRecord: RottingKanbanRecord,
    };
}
