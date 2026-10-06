/** @odoo-module native */
import { COMMANDS } from "@barcodes/barcode_handlers";
import { BarcodeInput } from "@barcodes/components/manual_barcode";
import { BARCODE_ERROR_SOUND, loadScanSounds } from "@barcodes/scan_sounds";
import { WebChatter } from "@mail/chatter/web/web_chatter";
import {
    Component,
    EventBus,
    onPatched,
    onWillStart,
    onWillUnmount,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { useBarcodeScreen } from "@stock_barcode/barcode_screen_hook";
import GroupedLineComponent from "@stock_barcode/components/grouped_line";
import LineComponent from "@stock_barcode/components/line";
import PackageLineComponent from "@stock_barcode/components/package_line";
import { provideBarcodeModel } from "@stock_barcode/models/barcode_model_hooks";
import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import BarcodeQuantModel from "@stock_barcode/models/barcode_quant_model";
import {
    BarcodeVideoScanner,
    isBarcodeScannerSupported,
} from "@web/components/barcode";
import { useSetupAction } from "@web/core/action_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Mutex } from "@web/core/utils/concurrency";
import { useBus, useService } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { View } from "@web/views/view";
import { standardWidgetProps } from "@web/views/widgets";
import { standardActionServiceProps } from "@web/webclient/actions";

import { CountScreenRFID } from "./count_screen_rfid.js";

// Lets `barcodeGenericHandlers` knows those commands exist so it doesn't warn when scanned.
COMMANDS["OCDMENU"] = () => {};
COMMANDS["OCDCANC"] = () => {};

const bus = new EventBus();

class StockBarcodeUnlinkButton extends Component {
    static template = "stock_barcode.UnlinkButton";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);
    setup() {
        this.orm = useService("orm");
    }
    async onClick() {
        const { resModel, resId, context } = this.props.record;
        await this.orm.unlink(resModel, [resId], { context });
        bus.trigger("refresh");
    }
}
registry.category("view_widgets").add("stock_barcode_unlink_button", {
    component: StockBarcodeUnlinkButton,
});

const log = makeLogger("stock_barcode.main");

export class BarcodeBlockUI extends Component {
    static props = {
        message: t.string().optional(),
    };
    static template = "stock_barcode.BlockUI";
    props = useProps(this.constructor.props);
}

/**
 * Main Component
 * Gather the line information.
 * Manage the scan and save process.
 */

class MainComponent extends Component {
    static props = { ...standardActionServiceProps };
    static template = "stock_barcode.MainComponent";
    static components = {
        BarcodeInput,
        BarcodeVideoScanner,
        Chatter: WebChatter,
        CountScreenRFID,
        GroupedLineComponent,
        BarcodeBlockUI,
        LineComponent,
        PackageLineComponent,
        View,
    };
    props = useProps(this.constructor.props);
    render = useRender();

    //--------------------------------------------------------------------------
    // Lifecycle
    //--------------------------------------------------------------------------

    setup() {
        useBarcodeScreen("native");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.actionMutex = new Mutex();
        this.resModel = this.props.action.res_model;
        this.resId = this.props.action.context.active_id || false;
        const model = this._getModel();
        model.draft = (!this.resId && this.props.action.context.barcode_draft) || null;
        model.newScrapProduct = this.newScrapProduct.bind(this);
        // Bound here rather than inline in `lineFormViewProps` / `scrapViewProps`:
        // the template reads those getters as bare `t-props="…"`, so they run
        // against OWL's per-render context and an arrow created inside them
        // captures that context as `this`. `toggleBarcodeLines` then wrote its
        // `this._editedLineParams = undefined` reset to a throwaway object, so
        // the component never actually cleared the edited line. `setup` runs on
        // the component, so these callbacks do.
        this._returnToBarcodeLines = () => this.toggleBarcodeLines();
        this._saveLineFormView = (record) => this.saveFormView(record);
        this.model = model;
        this.viewConfig = useViewConfig();
        provideBarcodeModel(model);
        this._scrollBehavior = "smooth";
        this.state = proxy({
            cameraScannedEnabled: false,
            view: "barcodeLines", // Could be also 'infoFormView', 'packagePage', 'scrapProductPage' or 'productPage'.
            displayNote: false,
            displayCountRFID: false,
            uiBlocked: false,
            barcodesProcessed: 0,
            barcodesToProcess: 0,
            blockUIMessage: "",
            // Reassigned, not pushed into: a new array is what re-renders the count
            // screen, and what its read rate is measured from.
            receivedRFIDs: [],
            totalRFIDs: [],
            readyToToggleCamera: true,
        });
        this.bufferedBarcodes = [];
        this.bufferingTimeout = null;
        this.barcodeService = useService("barcode");
        useBus(this.barcodeService.bus, "barcode_scanned", (ev) =>
            this.onBarcodeScanned(ev.detail.barcode),
        );
        this.mobileService = useService("mobile");
        useBus(this.mobileService.bus, "mobile_reader_scanned", (ev) =>
            this.onMobileReaderScanned(ev.detail.data),
        );

        useBus(this.model, "flash", this.flashScreen.bind(this));
        useBus(this.model, "playSound", this.playSound.bind(this));
        useBus(this.model, "addBarcodesCountToProcess", (ev) =>
            this.addBarcodesCountToProcess(ev.detail),
        );
        useBus(
            this.model,
            "updateBarcodesCountProcessed",
            this.updateBarcodesCountProcessed.bind(this),
        );
        useBus(
            this.model,
            "clearBarcodesCountProcessed",
            this.clearBarcodesCountProcessed.bind(this),
        );
        useBus(bus, "refresh", (ev) => this._onRefreshState(ev.detail));

        onWillStart(() => this.onWillStart());

        // Scans only live in `linesToSave` until an explicit save point; leaving through the
        // browser's back button or the menu used to drop them.
        useSetupAction({
            beforeLeave: () => {
                log.lifecycle("beforeLeave", {
                    pendingLines: this.model.linesToSave.length,
                });
                return this.actionMutex.exec(() => this.model.save());
            },
        });

        onWillUnmount(() => {
            log.lifecycle("unmount", { pendingLines: this.model.linesToSave.length });
            clearTimeout(this.bufferingTimeout);
            clearTimeout(this.RFIDCountTimeout);
            this.model._onExit();
        });

        onPatched(() => {
            this._scrollToSelectedLine();
        });
    }

    // UI Methods --------------------------------------------------------------
    addBarcodesCountToProcess(count) {
        this.state.barcodesToProcess += count;
        if (this.state.barcodesToProcess > this.state.barcodesProcessed) {
            this.updateBarcodesCountMessage();
            this.blockUI();
        }
    }

    updateBarcodesCountProcessed() {
        this.state.barcodesProcessed++;
        this.updateBarcodesCountMessage();
        if (this.state.barcodesProcessed >= this.state.barcodesToProcess) {
            this.clearBarcodesCountProcessed();
        }
    }

    clearBarcodesCountProcessed() {
        this.state.barcodesProcessed = 0;
        this.state.barcodesToProcess = 0;
        this.unblockUI();
    }

    updateBarcodesCountMessage() {
        this.state.blockUIMessage = _t(
            "Processing %(processed)s/%(toProcess)s barcodes",
            {
                processed: this.state.barcodesProcessed,
                toProcess: this.state.barcodesToProcess,
            },
        );
    }

    blockUI() {
        this.state.uiBlocked = true;
    }

    unblockUI() {
        this.state.uiBlocked = false;
        this.render(true);
    }

    async playSound(ev) {
        if (!this.config.play_sound || this.state.uiBlocked) {
            return;
        }
        const name = ev.detail || "notify";
        if (!(await this.sounds.play(name))) {
            log.logic("soundRefused", { name });
            this.config.play_sound = false;
        }
    }

    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------

    get highlightValidateButton() {
        return this.model.highlightValidateButton;
    }

    async onWillStart() {
        const barcodeData = await rpc("/stock_barcode/get_barcode_data", {
            model: this.resModel,
            res_id: this.resId,
            draft: this.model.draft || undefined,
        });
        barcodeData.actionId = this.props.actionId;
        this.config = { play_sound: true, ...barcodeData.data.config };
        if (this.config.play_sound) {
            this.sounds = loadScanSounds({
                error: BARCODE_ERROR_SOUND,
                notify: "/mail/static/src/audio/ting",
                success: "/stock_barcode/static/src/audio/success",
            });
        }
        this.setupCameraScanner();
        this.groups = barcodeData.groups;
        this.model.setData(barcodeData);
        this.state.displayNote = Boolean(this.model.record.note);
        this.model.addEventListener("process-action", this._onDoAction.bind(this));
        this.model.addEventListener("refresh", (ev) => this._onRefreshState(ev.detail));
        this.model.addEventListener("update", () => {
            if (!this.state.uiBlocked) {
                this.render(true);
            }
        });
        this.model.addEventListener("history-back", () => this._exit());
        this.model.addEventListener("record-created", (ev) =>
            this._onRecordCreated(ev.detail),
        );
    }

    /** The URL follows the record, so a reload reopens it rather than a new draft. */
    _onRecordCreated(resId) {
        this.resId = resId;
        this.props.updateActionState?.({ active_id: resId });
    }

    get lineFormViewProps() {
        return {
            resId: this._editedLineParams && this._editedLineParams.currentId,
            resModel: this.model.lineModel,
            context: this.model._getNewLineDefaultContext(),
            viewId: this.model.lineFormViewId,
            display: { controlPanel: false },
            type: "form",
            onSave: this._saveLineFormView,
            onDiscard: this._returnToBarcodeLines,
        };
    }

    get addLineBtnName() {
        return _t("Add Product");
    }

    get displayActionButtons() {
        return this.state.view === "barcodeLines" && this.model.canBeProcessed;
    }

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    _getBarcodeModel() {
        if (this.resModel === "stock.picking") {
            return BarcodePickingModel;
        } else if (this.resModel === "stock.quant") {
            return BarcodeQuantModel;
        }
        throw new Error("No JS model define");
    }

    _getModel() {
        const services = {
            rpc: rpc,
            orm: this.orm,
            notification: this.notification,
            action: this.action,
        };
        const BarcodeModel = this._getBarcodeModel();
        return new BarcodeModel(this.resModel, this.resId, services);
    }

    //--------------------------------------------------------------------------
    // Camera scanner
    //--------------------------------------------------------------------------

    toggleCameraScanner() {
        if (!this.state.cameraScannedEnabled) {
            this.state.cameraScannedEnabled = true;
            this.state.readyToToggleCamera = false;
        } else if (this.state.readyToToggleCamera) {
            this.state.cameraScannedEnabled = false;
        }
    }

    setupCameraScanner() {
        this.cameraScannerSupported = isBarcodeScannerSupported();
        this.barcodeVideoScannerProps = {
            delayBetweenScan: this.config.delay_between_scan || 2000,
            facingMode: "environment",
            onResult: (barcode) => this.onBarcodeScanned(barcode),
            onError: (error) => {
                this._stopCamera();
                const message = error.message;
                this.notification.add(message, { type: "warning" });
            },
            onReady: () => {
                this.state.readyToToggleCamera = true;
            },
            cssClass: "o_stock_barcode_camera_video",
        };
    }

    get cameraScannerClassState() {
        if (!this.state.readyToToggleCamera) {
            return "bg-secondary";
        }
        return this.state.cameraScannedEnabled
            ? "bg-success text-white"
            : "text-primary";
    }

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    async cancel() {
        await this.model.save();
        if (this.model.isDraft) {
            this.model._cancelNotification();
            return this._exit();
        }
        const action = await this.orm.call(
            this.resModel,
            "action_cancel_from_barcode",
            [[this.resId]],
        );
        this.action.doAction(action, {
            onClose: (res) => {
                if (res?.cancelled) {
                    this.model._cancelNotification();
                    this._exit();
                }
            },
        });
    }

    onBarcodeScanned(barcode) {
        if (this.state.view !== "barcodeLines") {
            return;
        }
        if (barcode) {
            this.actionMutex.exec(async () => this.model.processBarcode(barcode));
            if ("vibrate" in window.navigator) {
                window.navigator.vibrate(100);
            }
        } else {
            const message = _t("Please, Scan again!");
            this.notification.add(message, { type: "warning" });
        }
    }

    onMobileReaderScanned(data) {
        this.state.receivedRFIDs = [...this.state.receivedRFIDs, ...data];
        this.state.totalRFIDs = [...this.state.totalRFIDs, ...data];
        this.state.displayCountRFID = true;
        if (this.RFIDCountTimeout) {
            clearTimeout(this.RFIDCountTimeout);
        }
        this.RFIDCountTimeout = setTimeout(() => this.closeRFIDCount(), 5000);
        if (!this.bufferingTimeout) {
            this.bufferingTimeout = setTimeout(
                this._onMobileReaderScanned.bind(this),
                this.config.barcode_rfid_batch_time,
            );
        }
        this.bufferedBarcodes = this.bufferedBarcodes.concat(data);
    }

    async _onMobileReaderScanned() {
        // Take the batch before awaiting: reads that arrive while it is processed start
        // the next batch instead of being wiped with this one.
        const barcodes = this.bufferedBarcodes;
        this.bufferedBarcodes = [];
        this.bufferingTimeout = null;
        await this.actionMutex.exec(() =>
            this.model.processBarcode(barcodes.join(","), { readingRFID: true }),
        );
    }

    closeRFIDCount() {
        if (this.RFIDCountTimeout) {
            clearTimeout(this.RFIDCountTimeout);
        }
        this.state.displayCountRFID = false;
        this.state.receivedRFIDs = [];
    }

    onBarcodeSubmitted(barcode) {
        this.changeView("barcodeLines");
        barcode = this.model.cleanBarcode(barcode);
        this.onBarcodeScanned(barcode);
    }

    async exit() {
        this._stopCamera();
        if (this.state.view === "barcodeLines") {
            await this.model.beforeQuit();
            this._exit();
        } else {
            this.toggleBarcodeLines();
        }
    }

    _exit() {
        const { breadcrumbs } = this.viewConfig;
        if (breadcrumbs.length === 1) {
            // Bring back to the Barcode App home menu when there is no breadcrumb.
            this.action.doAction("stock_barcode.stock_barcode_action_main_menu");
        } else {
            const previousPath = breadcrumbs[breadcrumbs.length - 2].url.split("/");

            if (isNaN(previousPath[previousPath.length - 1])) {
                this.viewConfig.historyBack();
            } else {
                // If previous controller path's last part is a number, it will
                // open the current record form view (happens after a refresh of
                // the web browser.) Avoid that by calling browser's history back.
                history.back();
            }
        }
    }

    flashScreen() {
        if (this.state.uiBlocked) {
            return;
        }
        const clientAction = document.querySelector(".o_barcode_client_action");
        // Resets the animation (in case it still going).
        clientAction.style.animation = "none";
        clientAction.offsetHeight; // Trigger reflow.
        clientAction.style.animation = null;
        // Adds the CSS class linked to the keyframes animation `white-flash`.
        clientAction.classList.add("o_white_flash");
    }

    putInPack(ev) {
        ev.stopPropagation();
        this.model._putInPack();
    }

    returnProducts(ev) {
        ev.stopPropagation();
        this.model._returnProducts();
    }

    saveFormView(lineRecord) {
        const lineId = lineRecord.resId || this._editedLineParams?.currentId;
        const recordId = lineRecord.resModel === this.resModel ? lineId : undefined;
        this._onRefreshState({ recordId, lineId });
    }

    changeView(view) {
        this._stopCamera();
        this.state.view = view;
    }

    /**
     * A stopped camera is ready to be started again: leaving `readyToToggleCamera` false
     * (a camera stopped before it reported ready) kept the button styled as disabled.
     */
    _stopCamera() {
        this.state.cameraScannedEnabled = false;
        this.state.readyToToggleCamera = true;
    }

    async toggleBarcodeLines(lineId) {
        await this.model.displayBarcodeLines(lineId);
        this._editedLineParams = undefined;
        this.changeView("barcodeLines");
    }

    get isEditingInForm() {
        return ["productPage", "scrapProductPage"].includes(this.state.view);
    }

    async toggleInformation() {
        // Leaving the line or scrap form this way dropped its unsaved edits.
        if (this.model.formViewId && !this.isEditingInForm) {
            if (this.state.view === "infoFormView") {
                this.changeView("barcodeLines");
            } else {
                await this.model.ensureRecord();
                this.changeView("infoFormView");
            }
        }
    }

    /**
     * Stops event propagation and delegates validation to the model.
     *
     * @param {OdooEvent} ev
     */
    async validate(ev) {
        ev.stopPropagation();
        await this.model.validate();
    }

    _getHeaderHeight() {
        const header = document.querySelector(".o_barcode_header");
        const navbar = document.querySelector(".o_main_navbar");
        // Computes the real header's height (the navbar is present if the page was refreshed).
        return navbar ? navbar.offsetHeight + header.offsetHeight : header.offsetHeight;
    }

    _scrollToSelectedLine() {
        if (this.state.view !== "barcodeLines") {
            this._scrollBehavior = "auto";
            return;
        }
        // Tries to scroll to selected subline.
        let selectedLine = document.querySelector(
            ".o_sublines .o_barcode_line.o_highlight",
        );
        const isSubline = Boolean(selectedLine);
        // If no selected subline, tries to scroll to selected line.
        if (!selectedLine) {
            selectedLine = document.querySelector(".o_barcode_line.o_highlight");
        }

        let locationLine = false;
        if (this.model.lastScanned.sourceLocation) {
            const locId = this.model.lastScanned.sourceLocation.id;
            locationLine = document.querySelector(
                `.o_barcode_location_line[data-location-id="${locId}"]`,
            );
        } else if (selectedLine) {
            locationLine = selectedLine
                .closest(".o_barcode_location_group")
                .querySelector(".o_barcode_location_line");
        }
        // Scrolls either to the selected line, either to the location line.
        const targetElement =
            selectedLine || (locationLine && locationLine.parentElement);

        if (targetElement) {
            // If a line is selected, checks if this line is on the top of the
            // page, and if it's not, scrolls until the line is on top.
            const elRect = targetElement.getBoundingClientRect();
            const page = document.querySelector(".o_barcode_lines");
            const headerHeight = this._getHeaderHeight();
            if (
                elRect.top < headerHeight ||
                elRect.bottom > headerHeight + elRect.height
            ) {
                let top = elRect.top - headerHeight + page.scrollTop;
                if (isSubline) {
                    const parentLine = targetElement
                        .closest(".o_sublines")
                        .closest(".o_barcode_line");
                    const parentSummary = parentLine.querySelector(
                        ".o_barcode_line_summary",
                    );
                    top -= parentSummary.getBoundingClientRect().height;
                } else if (selectedLine && locationLine) {
                    top -= locationLine.getBoundingClientRect().height;
                }
                page.scroll({ left: 0, top, behavior: this._scrollBehavior });
                this._scrollBehavior = "smooth";
            }
        }
    }

    async _onDoAction(ev) {
        this.action.doAction(ev.detail, {
            onClose: this._onRefreshState.bind(this),
        });
    }

    onOpenPackage(packageIds) {
        this._inspectedPackageIds = packageIds;
        this.changeView("packagePage");
    }

    async newScrapProduct() {
        await this.model.ensureRecord();
        this.changeView("scrapProductPage");
    }

    get displayOperationButtons() {
        const { model } = this;
        return (
            model.canScrap ||
            model.displayCancelButton ||
            model.displaySignatureButton ||
            model.displayReturnButton
        );
    }

    get scrapViewProps() {
        const context = this.model.scrapContext;
        return {
            resModel: "stock.scrap",
            context: context,
            viewId: this.model.scrapViewId,
            display: { controlPanel: false },
            type: "form",
            onSave: this._returnToBarcodeLines,
            onDiscard: this._returnToBarcodeLines,
        };
    }

    async onOpenProductPage(line) {
        await this.model.ensureRecord();
        if (line) {
            const virtualId = line.virtual_id;
            // Updates the line id if it's missing, in order to open the line form view.
            if (!line.id && virtualId) {
                line = this.model.pageLines.find((l) => l.dummy_id === virtualId);
            }
            this._editedLineParams = this.model.getEditedLineParams(line);
        }
        this.changeView("productPage");
    }

    async _onRefreshState(paramsRefresh) {
        const { recordId, lineId } = paramsRefresh || {};
        const { route, params } = this.model.getActionRefresh(recordId);

        await this.actionMutex.exec(async () => {
            const result = await rpc(route, params);
            await this.model.resetState(result.data.records);
            await this.toggleBarcodeLines(lineId);
            this.render();
        });
    }
}

registry.category("actions").add("stock_barcode_client_action", MainComponent);

export default MainComponent;
