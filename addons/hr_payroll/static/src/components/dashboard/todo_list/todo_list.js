/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { orderByToString } from "@web/core/utils/order_by";
import { Field } from "@web/fields/field";
import { Record } from "@web/model/record";
import { ConfirmationDialog } from "@web/ui/dialog";
import { handleBeforeUnload } from "@web/views/view_utils";

const log = makeLogger("hr_payroll.todo_list");

/**
 * This component is actually a dumbed down list view for our notes.
 */

export class PayrollDashboardTodo extends Component {
    static template = "hr_payroll.TodoList";
    static components = {
        Field,
        Record,
    };
    static props = { orderBy: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = proxy({
            activeNoteId: -1,
            isEditingNoteName: false,
            records: [],
        });
        this.recordInfo = {
            model: "hr.payroll.note",
            specification: { name: {} },
        };
        this.recordHooks = {
            lifecycle: {
                onRootLoaded: this.onRecordChanged.bind(this),
                onRecordChanged: this.onRecordChanged.bind(this),
            },
        };
        this.autofocusRef = elementRef();
        this.autofocusInput = useAutofocus({ ref: this.autofocusRef, selectAll: true });
        useSetupAction({
            beforeLeave: () => this.saveNote(),
            beforeUnload: (ev) => this.beforeUnload(ev),
        });

        onWillStart(async () => {
            this.state.records = (
                await this.orm.webSearchRead(this.recordInfo.model, [], {
                    specification: this.recordInfo.specification,
                    order: orderByToString(this.props.orderBy),
                })
            ).records;
            const record = this.state.records[0];
            this.state.activeNoteId = record && record.id;
        });
    }

    /**
     * Creates a note.
     */
    async createNoteForm() {
        const result = await this.orm.create("hr.payroll.note", [
            {
                name: "Untitled",
                company_id: user.activeCompany.id,
                note: "",
            },
        ]);
        const noteId = result[0];
        const specification = this.recordInfo.specification;
        const createdNote = (
            await this.orm.webRead(this.recordInfo.model, [noteId], { specification })
        )[0];
        this.state.records.push(createdNote);
        this.state.activeNoteId = noteId;
        this.startNameEdition(createdNote);
    }

    /**
     * Switches to the requested note.
     *
     * @param { Record } record
     */
    async onClickNoteTab(record) {
        if (record.id === this.state.activeNoteId) {
            return;
        }
        await this.saveNote();
        this.state.isEditingNoteName = false;
        this.state.activeNoteId = record.id;
    }

    /** @param {BeforeUnloadEvent} ev */
    beforeUnload(ev) {
        const record = this.editedNote;
        log.logic("note unload", () => ({
            noteId: record?.resId,
            activeNoteId: this.state.activeNoteId,
        }));
        return handleBeforeUnload(ev, {
            record,
            inDialog: false,
            useSendBeacon: Boolean(record?.model.useSendBeaconToSaveUrgently),
            urgentSave: () => record.urgentSave(),
        });
    }

    onRecordChanged(editedRecord) {
        this.editedNote = editedRecord;
    }

    /**
     * On double-click, the note name should become editable
     * @param { Object } record the note record
     */
    startNameEdition(record) {
        if (record.id === this.state.activeNoteId) {
            this.state.isEditingNoteName = true;
            this.bufferedText = record.name;
        }
    }

    /**
     * On input, update buffer
     * @param { Event } ev
     */
    onInputNoteNameInput(ev) {
        this.bufferedText = ev.target.value;
    }

    /**
     * When the input loses focus, save the changes
     */
    handleBlur() {
        this._applyNoteRename();
    }

    /**
     * If enter/escape is pressed either save changes or discard them
     * @param { Event } ev
     */
    onKeyDownNoteNameInput(ev) {
        switch (ev.key) {
            case "Enter":
                this._applyNoteRename();
                break;
            case "Escape":
                this.state.isEditingNoteName = false;
                break;
        }
    }

    /**
     * Renames the active note with the text saved in the buffer
     */
    async _applyNoteRename() {
        const value = this.bufferedText.trim();
        const record = this.state.records.find(
            (record) => record.id === this.state.activeNoteId,
        );
        if (value !== record.name) {
            const previousName = record.name;
            record.name = value;
            try {
                await this.orm.write(this.recordInfo.model, [record.id], {
                    name: value,
                });
            } catch (error) {
                record.name = previousName;
                throw error;
            }
        }
        this.state.isEditingNoteName = false;
    }

    /**
     * Handler when delete button is clicked
     */
    async onNoteDelete() {
        const message = _t(
            "Are you sure you want to delete this note? All content will be definitely lost.",
        );
        this.dialog.add(ConfirmationDialog, {
            body: message,
            confirm: () => this._deleteNote(this.state.activeNoteId),
        });
    }

    /**
     * Deletes the specified note
     * @param {Number} noteId
     */
    async _deleteNote(noteId) {
        await this.orm.unlink(this.recordInfo.model, [noteId]);
        this.state.records = this.state.records.filter(
            (record) => record.id !== noteId,
        );
        this.state.activeNoteId = this.state.records.length && this.state.records[0].id;
    }

    /**
     * Handles the click on the create note button
     */
    async onClickCreateNote() {
        await this.saveNote();
        this.createNoteForm();
    }

    /**
     * Save the current note, has to be trigger before switching note.
     */
    async saveNote() {
        if (this.editedNote) {
            await this.editedNote.save();
        }
    }
}
