/** @odoo-module native */
import * as spreadsheet from "@odoo/o-spreadsheet";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    proxy,
    useProps,
} from "@odoo/owl";
import { SpreadsheetComponent } from "@spreadsheet/actions/spreadsheet_component";
import { createDefaultCurrency } from "@spreadsheet/currency/helpers";
import { OdooDataProvider } from "@spreadsheet/data_sources/odoo_data_provider";
import {
    DEFAULT_LINES_NUMBER,
    UNTITLED_SPREADSHEET_NAME,
} from "@spreadsheet/helpers/constants";
import { waitForDataLoaded } from "@spreadsheet/helpers/model";
import { provideSpreadsheetEnv, useSpreadsheetPrint } from "@spreadsheet/hooks";
import { initCallbackRegistry } from "@spreadsheet/o_spreadsheet/init_callbacks";
import { SpreadsheetNavbar } from "@spreadsheet_edition/bundle/components/spreadsheet_navbar/spreadsheet_navbar";
import { useControllerLifetime, useSetupAction } from "@web/core/action_hook";
import { useAppContext } from "@web/core/app_context";
import { browser } from "@web/core/browser/browser";
import { useDebugMode } from "@web/core/debug/debug_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { downloadFile } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { standardActionServiceProps } from "@web/webclient/actions";

import { CommentsStore } from "../comments/comments_store.js";
import {
    useSpreadsheetCurrencies,
    useSpreadsheetLocales,
    useSpreadsheetThumbnail,
} from "../hooks.js";
import { RecordFileStore } from "../image/record_file_store.js";
import { InputDialog } from "./input_dialog/input_dialog.js";

const log = makeLogger("spreadsheet_edition.action");

const uuidGenerator = new spreadsheet.helpers.UuidGenerator();

const { Model } = spreadsheet;
const { useStoreProvider, ModelStore, SidePanelStore } = spreadsheet.stores;

/**
 * @typedef SpreadsheetData
 * @property {number} id
 * @property {string} name
 * @property {string} data
 * @property {Object[]} revisions
 * @property {boolean} snapshot_requested
 * @property {Boolean} isReadonly
 * @property {string} [writable_rec_name_field]
 */

export class AbstractSpreadsheetAction extends Component {
    static template = "";
    static props = { ...standardActionServiceProps };
    static components = {
        SpreadsheetComponent,
        SpreadsheetNavbar,
    };
    static target = "fullscreen";
    props = useProps(this.constructor.props);

    setup() {
        this.appContext = useAppContext();
        this.debug = useDebugMode();
        this.config = useViewConfig();
        useLifecycleLog(log);
        if (!this.props.action.params) {
            // the action is coming from a this.trigger("do-action", ... ) of owl (not wowl and not legacy)
            this.params = this.props.action.context;
        } else {
            // the action is coming from wowl
            this.params = this.props.action.params;
        }
        this.isEmptySpreadsheet = this.params.is_new_spreadsheet || false;
        this.resId =
            this.params.resId ||
            this.params.spreadsheet_id || // backward compatibility. res_id used to be spreadsheet_id
            this.params.active_id || // backward compatibility. spreadsheet_id used to be active_id
            (this.props.state && this.props.state.resId); // used when going back to a spreadsheet via breadcrumb
        this.accessToken = this.params.access_token || this.props.state?.accessToken;
        this.actionService = useService("action");
        this.notifications = useService("notification");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.http = useService("http");
        this.ui = useService("ui");
        this.loadLocales = useSpreadsheetLocales();
        this.loadCurrencies = useSpreadsheetCurrencies();
        this.getThumbnail = useSpreadsheetThumbnail();
        this.geoJsonService = useService("geo_json_service");
        this.fileStore = new RecordFileStore(
            this.resModel,
            this.resId,
            this.http,
            this.orm,
        );
        this.spreadsheetService = useService("spreadsheet_collaborative");
        this.stores = useStoreProvider();
        this.threadId = this.params?.thread_id;
        this.dataFetched = false;
        this.originalMetaViewportContent = document.querySelector(
            'head meta[name="viewport"]',
        ).content;

        useSetupAction({
            beforeLeave: this._leaveSpreadsheet.bind(this),
            beforeUnload: this._leaveSpreadsheet.bind(this),
            getLocalState: () => ({
                resId: this.resId,
                accessToken: this.accessToken,
                data: this.data,
                model: this.model,
            }),
        });
        this.controllerLifetime = useControllerLifetime();

        const print = useSpreadsheetPrint(() => this.model);
        provideSpreadsheetEnv({
            download: this.download.bind(this),
            downloadAsJson: this.downloadAsJson.bind(this),
            showHistory: this.showHistory.bind(this),
            insertThreadInSheet: this.insertThreadInSheet.bind(this),
            print,
            getLinesNumber: this._getLinesNumber.bind(this),
            getUserLocale: () => this.data && this.data.user_locale,
        });
        this.state = proxy({
            spreadsheetName: UNTITLED_SPREADSHEET_NAME,
        });

        onWillStart(async () => {
            log.lifecycle("start", () => ({
                resModel: this.resModel,
                resId: this.resId,
                viaToken: Boolean(this.accessToken),
                restored: Boolean(this.props.state?.model && this.props.state?.data),
                preProcessingAction: this.params.preProcessingAction,
                preProcessingAsyncAction: this.params.preProcessingAsyncAction,
            }));
            if (this.props.state?.model && this.props.state?.data) {
                this.dataFetched = true;
                this._initializeWith(this.props.state.data);
                this.model = this.props.state.model;
                this.model.joinSession();
                this.stores.inject(ModelStore, this.model);
            } else {
                await this.fetchData();
                this.createModel();
                this.stores.inject(ModelStore, this.model);
            }
        });
        onMounted(() => {
            document
                .querySelector('head meta[name="viewport"]')
                .setAttribute(
                    "content",
                    this.originalMetaViewportContent +
                        ", interactive-widget=resizes-content",
                );
            this.execInitCallbacks();
            const commentsStore = this.stores.get(CommentsStore);
            this.props.updateActionState({
                resId: this.resId,
                access_token: this.accessToken,
            });
            this.config.setDisplayName(this.state.spreadsheetName);
            this.model.on(
                "unexpected-revision-id",
                this,
                this.onUnexpectedRevisionId.bind(this),
            );
            if (this.threadId) {
                // necessary atm - we need at least one frame to have the right viewport height/width
                setTimeout(() => commentsStore.openCommentThread(this.threadId), 0);
                const sidePanel = this.stores.get(SidePanelStore);
                sidePanel.open("Comments");
            }
        });
        onWillUnmount(() => {
            // the meximum scale does not work, need to find another approach
            document
                .querySelector('head meta[name="viewport"]')
                .setAttribute("content", this.originalMetaViewportContent);
            this.model.off("unexpected-revision-id", this);
        });
    }

    get navbarProps() {
        return {
            isReadonly: this.isReadonly,
            onSpreadsheetNameChanged: this._onSpreadSheetNameChanged.bind(this),
            spreadsheetName: this.state.spreadsheetName,
        };
    }

    async fetchData() {
        // if we are returning to the spreadsheet via the breadcrumb, we don't want
        // to do all the "creation" options of the actions
        if (!this.props.state) {
            await this._setupPreProcessingCallbacks();
        }
        const data = await this._fetchData();
        if (!data) {
            log.logic("fetchData:unavailable", () => ({
                resModel: this.resModel,
                resId: this.resId,
            }));
            this.actionService.doAction("menu");
            this.notifications.add(
                "The spreadsheet you’re trying to access doesn’t exist, has been deleted, or you don’t have the necessary permissions to view it.",
                {
                    type: "info",
                    sticky: true,
                },
            );
            return;
        }
        this.dataFetched = true;
        this._initializeWith(data);
    }

    createModel() {
        log.lifecycle("createModel", () => ({
            resId: this.resId,
            revisions: this.stateUpdateMessages?.length ?? 0,
            readonly: Boolean(this.isReadonly),
            snapshotRequested: Boolean(this.snapshotRequested),
        }));
        const endModel = log.perf("createModel");
        this.model = new Model(
            this.spreadsheetData,
            this.getModelConfig(),
            this.stateUpdateMessages,
        );
        endModel({ resId: this.resId });
        if (this.debug) {
            const debugObj = spreadsheet.__DEBUG__ || {};
            debugObj.model = this.model;
            globalThis.__SPREADSHEET_DEBUG__ = debugObj;
        }
    }

    getModelConfig() {
        if (!this.dataFetched) {
            return {};
        }
        const transportService = this.spreadsheetService.makeCollaborativeChannel(
            this.resModel,
            this.resId,
            this.accessToken,
            this.data?.revisionSequence,
        );
        this.controllerLifetime.onEnd(() => transportService.release());
        const odooDataProvider = new OdooDataProvider(this.appContext);
        odooDataProvider.addEventListener("data-source-updated", () => {
            this.model.dispatch("EVALUATE_CELLS");
        });
        return {
            custom: { env: this.appContext, orm: this.orm, odooDataProvider },
            external: {
                fileStore: this.fileStore,
                loadCurrencies: this.loadCurrencies,
                loadLocales: this.loadLocales,
                geoJsonService: this.geoJsonService,
            },
            defaultCurrency: createDefaultCurrency(this.data.default_currency),
            transportService,
            client: {
                id: uuidGenerator.smallUuid(),
                name: user.name,
                userId: user.userId,
            },
            mode: this.isReadonly ? "readonly" : "normal",
            snapshotRequested: this.snapshotRequested,
            customColors: this.data.company_colors,
        };
    }

    async execInitCallbacks() {
        if (!this.props.state?.model || !this.props.state?.data) {
            if (this.asyncInitCallback) {
                const endInit = log.perf("asyncInitCallback");
                try {
                    this.ui.block();
                    await this.asyncInitCallback(this.model, this.stores);
                } finally {
                    this.ui.unblock();
                    endInit({ action: this.params.preProcessingAsyncAction });
                }
            }
            if (this.initCallback) {
                this.initCallback(this.model, this.stores);
            }
        }
    }

    async _setupPreProcessingCallbacks() {
        if (this.params.preProcessingAction) {
            const initCallbackGenerator = initCallbackRegistry
                .get(this.params.preProcessingAction)
                .bind(this);
            this.initCallback = await initCallbackGenerator(
                this.params.preProcessingActionData,
            );
        }
        if (this.params.preProcessingAsyncAction) {
            const initCallbackGenerator = initCallbackRegistry
                .get(this.params.preProcessingAsyncAction)
                .bind(this);
            this.asyncInitCallback = await initCallbackGenerator(
                this.params.preProcessingAsyncActionData,
            );
        }
    }

    /**
     * @protected
     * @abstract
     * @param {SpreadsheetData} data
     */
    _initializeWith(data) {
        this.state.spreadsheetName = data.name;
        this.spreadsheetData = data.data;
        this.stateUpdateMessages = data.revisions;
        this.snapshotRequested = data.snapshot_requested;
        this.isReadonly = data.isReadonly;
        this.data = data;
    }

    /**
     * Make a copy of the current document
     * @protected
     */
    async makeCopy() {
        const display_thumbnail = this.getThumbnail();
        const data = this.model.exportData();
        const defaultValues = {
            spreadsheet_data: JSON.stringify(data),
            spreadsheet_snapshot: false,
            spreadsheet_revision_ids: [],
            display_thumbnail,
        };
        const ids = await this.orm.call(this.resModel, "copy", [[this.resId]], {
            default: defaultValues,
        });
        const id = ids[0];
        log.logic("makeCopy", { resModel: this.resModel, from: this.resId, to: id });
        this._openSpreadsheet(id);
    }

    /**
     * @private
     */
    async _leaveSpreadsheet() {
        log.lifecycle("leave", () => ({
            resId: this.resId,
            readonly: Boolean(this.isReadonly),
        }));
        await this.model.leaveSession();
        this.model.off("update", this);
        if (!this.isReadonly) {
            return this.onSpreadsheetLeft();
        }
    }

    async _onSpreadSheetNameChanged(detail) {
        const { name } = detail;
        if (name && name !== this.state.spreadsheetName) {
            this.state.spreadsheetName = name;
            this.data.name = name;
            this.config.setDisplayName(this.state.spreadsheetName);
            if (this.data.writable_rec_name_field) {
                await this.orm.write(this.resModel, [this.resId], {
                    [this.data.writable_rec_name_field]: name,
                });
            }
        }
    }

    async createNewSpreadsheet() {
        throw new Error("not implemented by children");
    }

    async onSpreadsheetLeft() {
        if (this.accessToken) {
            return;
        }
        await this.orm.write(
            this.resModel,
            [this.resId],
            this.onSpreadsheetLeftUpdateVals(),
        );
    }

    onSpreadsheetLeftUpdateVals() {
        return { display_thumbnail: this.getThumbnail() };
    }

    /**
     * @returns {Promise<SpreadsheetData>}
     */
    async _fetchData() {
        const endFetch = log.perf("fetchData");
        const tokenSegment = this.accessToken
            ? `/${encodeURIComponent(this.accessToken)}`
            : "";
        const response = await browser.fetch(
            `/spreadsheet/data/${this.resModel}/${this.resId}${tokenSegment}`,
            {
                method: "GET",
            },
        );
        endFetch({
            resModel: this.resModel,
            resId: this.resId,
            status: response.status,
        });
        if ([403, 404].includes(response.status)) {
            return;
        }
        return response.json();
    }

    /**
     * Open a spreadsheet
     * @private
     */
    _openSpreadsheet(spreadsheetId) {
        this.actionService.doAction(
            {
                type: "ir.actions.client",
                tag: this.props.action.tag,
                params: { spreadsheet_id: spreadsheetId },
            },
            { stackPosition: "replaceCurrentAction" },
        );
    }

    showHistory() {
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "action_open_spreadsheet_history",
            params: {
                spreadsheet_id: this.resId,
                res_model: this.resModel,
            },
        });
    }

    /**
     * Reload the spreadsheet if an unexpected revision id is triggered.
     */
    async onUnexpectedRevisionId() {
        if (this.catchingUp) {
            this.catchUpAgain = true;
            return;
        }
        this.catchingUp = true;
        try {
            do {
                this.catchUpAgain = false;
                if (!(await this._catchUp())) {
                    log.logic("unexpectedRevisionId:reload", () => ({
                        resId: this.resId,
                    }));
                    this.actionService.doAction("reload_context");
                    return;
                }
            } while (this.catchUpAgain);
        } finally {
            this.catchingUp = false;
        }
    }

    /**
     * Replays the revisions this session missed, in order, as the bus would
     * have delivered them.
     * @returns {Promise<boolean>} false when the server no longer has this
     * session's revision, or replaying did not move the session past it
     */
    async _catchUp() {
        const { session } = this.model;
        const head = session.getRevisionId();
        let missed;
        try {
            missed = await this.orm.silent.call(
                this.resModel,
                "get_spreadsheet_revisions_after",
                [this.resId, head, this.accessToken],
            );
        } catch (error) {
            // what cannot be caught up on is reloaded, as before catching up
            log.logic("unexpectedRevisionId:catchUpFailed", () => ({
                resId: this.resId,
                error: error?.name,
            }));
            return false;
        }
        log.logic("unexpectedRevisionId:catchUp", () => ({
            resId: this.resId,
            missed: missed?.length,
        }));
        if (!missed) {
            return false;
        }
        for (const message of missed) {
            session.onMessageReceived(message);
        }
        return !missed.length || session.getRevisionId() !== head;
    }

    /**
     * Downloads the spreadsheet in xlsx format
     */
    async download() {
        this.ui.block();
        const endDownload = log.perf("downloadXlsx");
        try {
            await waitForDataLoaded(this.model);
            await this.actionService.doAction({
                type: "ir.actions.client",
                tag: "action_download_spreadsheet",
                params: {
                    name: this.state.spreadsheetName,
                    xlsxData: this.model.exportXLSX(),
                },
            });
        } finally {
            endDownload({ resId: this.resId });
            this.ui.unblock();
        }
    }

    /**
     * Downloads the spreadsheet in json format
     */
    async downloadAsJson() {
        this.ui.block();
        try {
            const data = JSON.stringify(this.model.exportData());
            await downloadFile(
                data,
                `${this.state.spreadsheetName}.osheet.json`,
                "application/json",
            );
        } finally {
            this.ui.unblock();
        }
    }

    _getLinesNumber(callback) {
        this.dialog.add(InputDialog, {
            body: _t("Select the number of records to insert"),
            confirm: callback,
            title: _t("Re-insert list"),
            inputValue: DEFAULT_LINES_NUMBER,
            inputType: "number",
        });
    }

    async insertThreadInSheet({ sheetId, col, row }) {
        const [threadId] = await this.orm.create("spreadsheet.cell.thread", [
            { [this.threadField]: this.resId },
        ]);
        this.model.dispatch("ADD_COMMENT_THREAD", {
            sheetId,
            col,
            row,
            threadId,
        });
        return threadId;
    }
}
