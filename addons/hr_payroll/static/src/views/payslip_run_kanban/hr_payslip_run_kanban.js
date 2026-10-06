/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    KanbanController,
    KanbanHeader,
    KanbanRecord,
    KanbanRenderer,
    kanbanView,
} from "@web/views/kanban";

import { PayRunButtonBox } from "../../components/payrun_card/button_box/payrun_button_box.js";
import { useOpenPayRun } from "../payslip_run_hook.js";
import { PayRunKanbanCompiler } from "./hr_payslip_run_kanban_compiler.js";

class PayrunKanbanController extends KanbanController {
    static components = {
        ...KanbanController.components,
    };

    /**
     * @override
     */
    setup() {
        super.setup();
        this.openPayRun = useOpenPayRun();
    }

    async openRecord(record) {
        this.openPayRun({ id: record.resId });
    }

    async createRecord() {
        this.openPayRun({});
    }
}

export class PayrunKanbanHeader extends KanbanHeader {
    static template = "hr_payroll.PayrunKanbanHeader";

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}

export class PayrunKanbanRecord extends KanbanRecord {
    static menuTemplate = "hr_payroll.PayrunKanbanRecordMenu";
    static components = {
        ...KanbanRecord.components,
        PayRunButtonBox,
    };
}

export class PayrunKanbanRenderer extends KanbanRenderer {
    static template = "hr_payroll.PayrunKanbanRenderer";

    static components = {
        ...KanbanRenderer.components,
        KanbanHeader: PayrunKanbanHeader,
        KanbanRecord: PayrunKanbanRecord,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}

const PayrunKanbanView = {
    ...kanbanView,
    Controller: PayrunKanbanController,
    Compiler: PayRunKanbanCompiler,
    Renderer: PayrunKanbanRenderer,
};

registry.category("views").add("payslip_run_kanban", PayrunKanbanView);
