// @ts-check
/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { FormController } from "@web/views/form";

const log = makeLogger("web.view.form");

export class FormControllerWithHTMLExpander extends FormController {
    static template = "web.FormViewWithHtmlExpander";

    /** @type {{ reload: boolean }} */
    htmlExpanderState;

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.htmlExpanderState = proxy({ reload: true });
        const oldOnNotebookPageChange = this.onNotebookPageChange;
        /**
         * @param {string} notebookId
         * @param {string} page
         */
        this.onNotebookPageChange = (notebookId, page) => {
            oldOnNotebookPageChange(notebookId, page);
            if (page && !this.htmlExpanderState.reload) {
                this.htmlExpanderState.reload = true;
            }
        };
    }

    get modelParams() {
        const modelParams = super.modelParams;

        const lifecycle = /** @type {Record<string, any>} */ (
            modelParams.hooks.lifecycle
        );
        const onRootLoaded = lifecycle.onRootLoaded;
        lifecycle.onRootLoaded = async () => {
            await onRootLoaded?.();
            this.htmlExpanderState.reload = true;
        };
        return modelParams;
    }

    notifyHTMLFieldExpanded() {
        this.htmlExpanderState.reload = false;
    }

    /**
     * @param {any} record
     * @param {any} changes
     */
    async onRecordSaved(record, changes) {
        await super.onRecordSaved(record, changes);
        log.logic("htmlExpander.onRecordSaved", () => ({ resId: record.resId }));
        this.htmlExpanderState.reload = true;
    }
}
