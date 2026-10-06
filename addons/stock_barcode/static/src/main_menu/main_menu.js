/** @odoo-module native */
import { ManualBarcodeScanner } from "@barcodes/components/manual_barcode";
import { loadScanSounds } from "@barcodes/scan_sounds";
import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { useBarcodeScreen } from "@stock_barcode/barcode_screen_hook";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useBus, useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
import { standardActionServiceProps } from "@web/webclient/actions";

export class MainMenu extends Component {
    static props = { ...standardActionServiceProps };
    static template = "stock_barcode.MainMenu";
    props = useProps(this.constructor.props);

    setup() {
        useBarcodeScreen("native");
        const displayDemoMessage = this.props.action.params.message_demo_barcodes;
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.pwaService = useService("pwa");
        this.home = useService("home_menu");
        this.notificationService = useService("notification");
        this.state = proxy({ displayDemoMessage });
        this.barcodeService = useService("barcode");
        useBus(this.barcodeService.bus, "barcode_scanned", (ev) =>
            this._onBarcodeScanned(ev.detail.barcode),
        );

        onWillStart(async () => {
            const data = await rpc("/stock_barcode/get_main_menu_data");
            this.locationsEnabled = data.groups.locations;
            this.packagesEnabled = data.groups.package;
            this.trackingEnabled = data.groups.tracking;
            this.quantCount = data.quant_count;
            this.soundEnable = data.play_sound;
            if (this.soundEnable) {
                this.sounds = loadScanSounds({
                    success: "/stock_barcode/static/src/audio/success",
                });
            }
        });
    }

    logout() {
        const path = `/web/session/logout${
            this.pwaService.isScopedApp ? "?redirect=scoped_app/barcode" : ""
        }`;
        window.open(path, "_self");
    }

    openManualBarcodeDialog() {
        this.dialogService.add(ManualBarcodeScanner, {
            facingMode: "environment",
            onResult: (barcode) => this._onBarcodeScanned(barcode),
            onError: () => {},
        });
    }

    removeDemoMessage() {
        const params = {
            title: _t("Don't show this message again"),
            body: _t(
                "Do you want to permanently remove this message ? " +
                    "It won't appear anymore, so make sure you don't need the barcodes sheet or you have a copy.",
            ),
            confirm: async () => {
                await rpc("/stock_barcode/rid_of_message_demo_barcodes"); // Sets action message param false on server
                this.state.displayDemoMessage = false; // Remove message from current view
                this.props.action.params.message_demo_barcodes = false; // Remove message if using breadcrumbs
            },
            cancel: () => {},
            confirmLabel: _t("Remove it"),
            cancelLabel: _t("Leave it"),
        };
        this.dialogService.add(ConfirmationDialog, params);
    }

    async playSound(name) {
        if (this.soundEnable && !(await this.sounds.play(name))) {
            this.soundEnable = false;
        }
    }

    async _onBarcodeScanned(barcode) {
        const res = await rpc("/stock_barcode/scan_from_main_menu", { barcode });
        if (res.action) {
            this.playSound("success");
            return this.actionService.doAction(res.action);
        }
        this.notificationService.add(res.warning, { type: "danger" });
    }

    /** Builds the barcode landing page bullet points, decribing features available depending on settings */
    get barcodeHomeHelper() {
        const tags = {
            bold_s: markup`<b>`,
            bold_e: markup`</b>`,
        };

        const bullets = [
            _t(
                "Scan a %(bold_s)sproduct%(bold_e)s or its %(bold_s)spackaging%(bold_e)s to locate it",
                tags,
            ),
        ];
        // 2nd bullet point depends on which setting is activated
        if (this.packagesEnabled && this.trackingEnabled) {
            bullets.push(
                _t(
                    "Scan a %(bold_s)stracking number%(bold_e)s or a %(bold_s)spackage%(bold_e)s to find a transfer",
                    tags,
                ),
            );
        } else if (this.packagesEnabled) {
            bullets.push(
                _t("Scan a %(bold_s)spackage%(bold_e)s to find a transfer", tags),
            );
        } else if (this.trackingEnabled) {
            bullets.push(
                _t(
                    "Scan a %(bold_s)stracking number%(bold_e)s to find a transfer",
                    tags,
                ),
            );
        }
        bullets.push(_t("Scan a %(bold_s)spicking%(bold_e)s to open it", tags));
        if (this.locationsEnabled) {
            bullets.push(
                _t("Scan a %(bold_s)slocation%(bold_e)s to initiate a transfer", tags),
            );
        }
        bullets.push(
            _t("Scan an %(bold_s)soperation type%(bold_e)s to start it", tags),
        );
        return bullets;
    }

    get demoMessage() {
        const demo_link = _t("Download demo data sheet");
        const barcode_link = _t("Download operation barcodes");

        const sheet_s = markup`<a href="/stock_barcode/static/img/barcodes_demo.pdf" target="_blank" aria-label="${demo_link}" title="${demo_link}">`;
        const ops_s = markup`<a href="/stock_barcode/print_inventory_commands?barcode_type=barcode_commands_and_operation_types" target="_blank" aria-label="${barcode_link}" title="${barcode_link}">`;
        const sheet_e = markup`</a>`;
        const ops_e = markup`</a>`;

        return _t(
            "Print the %(sheet_s)sdemo data sheet%(sheet_e)s to test, or %(ops_s)sbarcodes%(ops_e)s for operations.",
            { sheet_s, sheet_e, ops_s, ops_e },
        );
    }
}

registry.category("actions").add("stock_barcode_main_menu", MainMenu);
