/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { SpreadsheetSelectorGrid } from "@spreadsheet_edition/assets/components/spreadsheet_selector_grid/spreadsheet_selector_grid";
import { Pager } from "@web/components/pager";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/translation";
import { KeepLast } from "@web/core/utils/concurrency";
import { useBus, useService } from "@web/core/utils/hooks";
import { provideViewConfig } from "@web/core/view_config_hooks";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { provideChildSearchModel, SearchModel } from "@web/search/search_model";
import { Dialog } from "@web/ui/dialog";
import { getDefaultConfig } from "@web/views/view";

export class TemplateDialog extends Component {
    static components = { Dialog, SearchBar, Pager, SpreadsheetSelectorGrid };
    static template = "document_spreadsheet.TemplateDialog";
    static props = {
        context: t.object(),
        folderId: t.or([t.string(), t.number()]).optional(),
        close: t.function(),
        folders: t.array(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.dialogContext = useDialogContext();
        this.orm = useService("orm");
        this.viewService = useService("view");
        this.actionService = useService("action");

        this.data = this.dialogContext.dialogData;
        useHotkey("escape", () => this.data.close());
        useHotkey("Enter", async () => {
            await this._createSpreadsheet();
        });

        this.dialogTitle = _t("Create a Spreadsheet or select a Template");
        this.limit = 9;
        this.state = proxy({
            isOpen: true,
            templates: [],
            templatesCount: 0,
            selectedTemplateId: null,
            offset: 0,
            isCreating: false,
        });
        provideViewConfig({ ...getDefaultConfig(), disableSearchBarAutofocus: true });
        this.model = new SearchModel(SearchModel.useSearchScope(), {
            orm: this.orm,
            view: useService("view"),
        });
        provideChildSearchModel(this.model);
        useBus(this.model, "update", () => {
            this.state.offset = 0;
            this._fetchTemplates();
        });
        this.keepLast = new KeepLast();
        this.folderOptions = [
            { id: 0, display_name: _t("My Drive") },
            ...this.props.folders.map((folder) => ({
                id: folder.id,
                display_name: folder.display_name,
            })),
        ];
        onWillStart(async () => {
            this.folderId = this.folderOptions[0].id;
            const views = await this.viewService.loadViews({
                resModel: "spreadsheet.template",
                context: this.props.context,
                views: [[false, "search"]],
            });
            await this.model.load({
                resModel: "spreadsheet.template",
                context: this.props.context,
                orderBy: "id",
                searchMenuTypes: [],
                searchViewIR: views.views.search.ir,
                searchViewId: views.views.search.id,
                searchViewFields: views.fields,
            });
            await this._fetchTemplates();
        });
    }

    /**
     * Fetch templates according to the search domain and the pager
     * offset given as parameter.
     * @private
     * @param {number} offset
     * @returns {Promise<void>}
     */
    async _fetchTemplates(offset = 0) {
        const { domain, context } = this.model;
        const { records, length } = await this.keepLast.add(
            this.orm.webSearchRead("spreadsheet.template", domain, {
                specification: { display_name: {} },
                domain,
                context,
                offset,
                limit: this.limit,
                order: "sequence, id",
            }),
        );
        this.state.templates = records;
        this.state.templatesCount = length;
    }

    /**
     * Will create a spreadsheet based on the currently selected template
     * and the current folder we are in. The user will be notified and
     * the newly created spreadsheet will be opened.
     * @private
     * @returns {Promise<void>}
     */
    async _createSpreadsheet() {
        if (!this._hasSelection()) {
            return;
        }
        this.state.isCreating = true;

        this.actionService.doAction(await this._getOpenSpreadsheetAction(), {
            additionalContext: this.props.context,
        });
        this.data.close();
    }

    async _getOpenSpreadsheetAction() {
        const context = this.props.context;
        const templateId = this.state.selectedTemplateId;
        const folder_id = this.props.folderId
            ? typeof this.props.folderId === "number"
                ? this.props.folderId
                : false
            : this.folderId || false;
        if (templateId) {
            return this.orm.call(
                "spreadsheet.template",
                "action_create_spreadsheet",
                [templateId, { folder_id }],
                { context },
            );
        }
        return this.orm.call(
            "document.document",
            "action_view_new_spreadsheet",
            [{ folder_id }],
            {
                context,
            },
        );
    }

    /**
     * Changes the currently selected template in the state.
     * @private
     * @param {number | null} templateId
     */
    _selectTemplate(templateId) {
        this.state.selectedTemplateId = templateId;
    }

    /**
     * Returns whether templateId is currently selected or not.
     * @private
     * @param {number | null} templateId
     * @returns {boolean}
     */
    _isSelected(templateId) {
        return this.state.selectedTemplateId === templateId;
    }

    /**
     * Check if any template or the Blank template is selected.
     * @private
     * @returns {boolean}
     */
    _hasSelection() {
        return (
            this.state.templates.find(
                (template) => template.id === this.state.selectedTemplateId,
            ) || this.state.selectedTemplateId === null
        );
    }

    /**
     * This function will be called when the user uses the pager. Based on the
     * pager state, new templates will be fetched.
     * @private
     * @param {CustomEvent} ev
     * @returns {Promise<void>}
     */
    _onPagerChanged({ offset }) {
        this.state.offset = offset;
        return this._fetchTemplates(this.state.offset);
    }

    /**
     * Check if the create button should be disabled.
     * @private
     * @returns {boolean}
     */
    _buttonDisabled() {
        return this.state.isCreating || !this._hasSelection();
    }

    /**
     * Get the URL of the template's thumbnail.
     * @param {Object} template
     * @returns {string} - URL for the template thumbnail
     */
    getThumbnailURL(template) {
        return `/web/image?model=spreadsheet.template&id=${template.id}&field=display_thumbnail`;
    }
}
