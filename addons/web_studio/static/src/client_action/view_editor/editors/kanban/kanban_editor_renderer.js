/** @odoo-module native */

import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { KanbanHeader, kanbanView } from "@web/views/kanban";
import { KanbanEditorRecord } from "@web_studio/client_action/view_editor/editors/kanban/kanban_editor_record";

import { SelectionHeaderButtons } from "../../interactive_editor/action_button/action_button.js";

class KanbanEditorHeader extends KanbanHeader {
    static template = "web_studio.KanbanEditorHeader";

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}

export class KanbanEditorRenderer extends kanbanView.Renderer {
    static template = "web_studio.KanbanEditorRenderer";
    static components = {
        ...kanbanView.Renderer.components,
        KanbanRecord: KanbanEditorRecord,
        KanbanHeader: KanbanEditorHeader,
        SelectionHeaderButtons,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
        const rootRef = this.rootRef;
        useLayoutEffect(
            (el) => {
                if (!el) {
                    return;
                }
                el.classList.add("o_web_studio_kanban_view_editor");
            },
            () => [rootRef.el],
        );
    }

    get canUseSortable() {
        return false;
    }

    get showNoContentHelper() {
        return false;
    }

    getGroupsOrRecords() {
        const { list } = this.props;
        const groupsOrRec = super.getGroupsOrRecords(...arguments);
        if (list.isGrouped) {
            return groupsOrRec.filter((el) => el.group.list.records.length).slice(0, 1);
        } else {
            return groupsOrRec.slice(0, 1);
        }
    }

    canCreateGroup() {
        return false;
    }

    getGroupUnloadedCount() {
        return 0;
    }
}
