/** @odoo-module native */
import { registry } from "@web/core/registry";

import {
    SectionAndNoteFieldOne2Many,
    sectionAndNoteFieldOne2Many,
    SectionAndNoteListRenderer,
} from "../section_and_note_fields_backend/section_and_note_fields_backend.js";

export class AccountMergeWizardLinesRenderer extends SectionAndNoteListRenderer {
    setup() {
        super.setup();
        this.titleField = "info";
    }

    /** @override */
    isSectionColumnKept(column) {
        return column.type === "field" && column.name === "is_selected";
    }

    /** @override */
    isSortable(column) {
        return false;
    }
}

export class AccountMergeWizardLinesOne2Many extends SectionAndNoteFieldOne2Many {
    static components = {
        ...SectionAndNoteFieldOne2Many.components,
        ListRenderer: AccountMergeWizardLinesRenderer,
    };
}

export const accountMergeWizardLinesOne2Many = {
    ...sectionAndNoteFieldOne2Many,
    component: AccountMergeWizardLinesOne2Many,
};

registry
    .category("fields")
    .add("account_merge_wizard_lines_one2many", accountMergeWizardLinesOne2Many);
