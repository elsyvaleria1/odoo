/** @odoo-module native */
import { Model, registries } from "@odoo/o-spreadsheet";
import { proxy } from "@odoo/owl";
import { UNTITLED_SPREADSHEET_NAME } from "@spreadsheet/helpers/constants";
import { provideSpreadsheetEnv } from "@spreadsheet/hooks";
import { AbstractSpreadsheetAction } from "@spreadsheet_edition/bundle/actions/abstract_spreadsheet_action";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
const { topbarMenuRegistry } = registries;

export class SpreadsheetAction extends AbstractSpreadsheetAction {
    static template = "document_spreadsheet.SpreadsheetAction";
    static path = "spreadsheet";
    static displayName = _t("Spreadsheet");

    resModel = "document.document";
    threadField = "document_id";

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.state = proxy({
            isFavorited: false,
            spreadsheetName: UNTITLED_SPREADSHEET_NAME,
        });
        this.threadId = this.params?.thread_id;
        this.notification = useService("notification");
        this.dialogService = useService("dialog");
        this.documentService = useService("document.document");
        provideSpreadsheetEnv({
            newSpreadsheet: this.createNewSpreadsheet.bind(this),
            makeCopy: this.makeCopy.bind(this),
            saveAsTemplate: this.saveAsTemplate.bind(this),
            onShareSpreadsheet: this.shareSpreadsheet.bind(this),
            onFreezeAndShareSpreadsheet: this.freezeAndShareSpreadsheet.bind(this),
            moveToTrash: this.moveToTrash.bind(this),
            isFrozenSpreadsheet: () => this.data.handler === "frozen_spreadsheet",
            isArchived: () => Boolean(this.data?.is_archived),
        });
    }

    /**
     * @override
     */
    _initializeWith(data) {
        super._initializeWith(data);
        this.state.isFavorited = data.is_user_favorite;
    }

    /**
     * @returns {Promise}
     */
    async _onSpreadSheetFavoriteToggled() {
        this.state.isFavorited = !this.state.isFavorited;
        return await this.orm.call("document.document", "action_toggle_user_favorite", [
            [this.resId],
        ]);
    }

    async createNewSpreadsheet() {
        const action = await this.orm.call(
            "document.document",
            "action_view_new_spreadsheet",
        );
        this.actionService.doAction(action, { stackPosition: "replaceCurrentAction" });
    }

    onSpreadsheetLeftUpdateVals() {
        return {
            ...super.onSpreadsheetLeftUpdateVals(),
            is_multipage: this.model.getters.getSheetIds().length > 1,
        };
    }

    /**
     * @private
     * @returns {Promise}
     */
    async saveAsTemplate() {
        const model = new Model(this.model.exportData(), {
            custom: {
                env: this.appContext,
                odooDataProvider: this.model.config.custom.odooDataProvider,
            },
        });
        const data = model.exportData();
        const name = this.state.spreadsheetName;

        this.actionService.doAction(
            "document_spreadsheet.save_spreadsheet_template_action",
            {
                additionalContext: {
                    default_template_name: _t("%s - Template", name),
                    default_spreadsheet_data: JSON.stringify(data),
                    default_thumbnail: this.getThumbnail(),
                },
            },
        );
    }

    shareSpreadsheet() {
        this.documentService.openSharingDialog([this.resId]);
    }

    async freezeAndShareSpreadsheet() {
        if (this.data.handler === "frozen_spreadsheet") {
            this.notification.add(_t("You can not freeze a frozen spreadsheet"));
            return;
        }

        const { freezeOdooData } = await import("@spreadsheet/helpers/model");
        const data = await freezeOdooData(this.model);

        const record = await this.orm.call(
            "document.document",
            "action_freeze_and_copy",
            [this.resId, JSON.stringify(data), this.model.exportXLSX().files],
        );
        this.documentService.openSharingDialog([record.id]);
    }

    async moveToTrash() {
        const wasArchived = await this.documentService.moveToTrash([this.resId]);
        if (!wasArchived) {
            return;
        }
        if (this.config.breadcrumbs.length > 1) {
            await this.actionService.restore();
        } else {
            await this.actionService.doAction("document.document_action");
        }
        this.notification.add(_t("Spreadsheet moved to trash"), { type: "success" });
    }
}

registry
    .category("actions")
    .add("action_view_spreadsheet", SpreadsheetAction, { force: true });

topbarMenuRegistry.addChild("move_to_trash", ["file"], {
    name: _t("Move to trash"),
    sequence: 80,
    isVisible: (env) => env.isArchived && !env.isArchived() && !!env.moveToTrash,
    execute: (env) => env.moveToTrash(),
    icon: "o-spreadsheet-Icon.TRASH_FILLED",
});
