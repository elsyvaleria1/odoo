/** @odoo-module native */
import {
    BarcodeScanner,
    scanBarcodeOrWarn,
} from "@barcodes/components/barcode_scanner";
import { BARCODE_ERROR_SOUND, loadScanSounds } from "@barcodes/scan_sounds";
import { Component, onWillStart, useProps } from "@odoo/owl";
import { scanBarcode } from "@web/components/barcode";
import { useAppContext } from "@web/core/app_context";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useBus, useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions";

import { EventRegistrationSummaryDialog } from "./event_registration_summary_dialog.js";

export class EventScanView extends Component {
    static template = "event.EventScanView";
    static components = { BarcodeScanner };
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);

    setup() {
        this.appContext = useAppContext();
        this.actionService = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.orm = useService("orm");

        const { default_event_id, active_model, active_id } = this.props.action.context;
        this.eventId =
            default_event_id || (active_model === "event.event" && active_id);
        this.isMultiEvent = !this.eventId;
        this.isDisplayStandalone = isDisplayStandalone();

        const barcode = useService("barcode");
        useBus(barcode.bus, "barcode_scanned", (ev) =>
            this.onBarcodeScanned(ev.detail.barcode),
        );

        onWillStart(this.onWillStart);
    }

    /**
     * @override
     * Fetch barcode init information. Notably eventId triggers mono- or multi-
     * event mode (Registration Desk in multi event allow to manage attendees
     * from several events and tickets without reloading / changing event in UX.
     */
    async onWillStart() {
        this.data = await rpc("/event/init_barcode_interface", {
            event_id: this.eventId,
        });
        this.sounds = loadScanSounds({
            error: BARCODE_ERROR_SOUND,
            notify: "/mail/static/src/audio/ting",
        });
    }

    playSound(type = "notify") {
        this.sounds.play(type);
    }

    /**
     * When scanning a barcode, call Registration.register_attendee() to get
     * formatted registration information, notably its status or event-related
     * information. Open a confirmation / choice Dialog to confirm attendee.
     * @param {Object} barcode
     * @param {function} onNextScanTriggered
     */
    async onBarcodeScanned(barcode, onNextScanTriggered = () => {}) {
        const result = await this.orm.call(
            "event.registration",
            "register_attendee",
            [],
            {
                barcode: barcode,
                event_id: this.eventId,
            },
        );

        if (result.error && result.error === "invalid_ticket") {
            this.playSound("error");
            this.notification.add(_t("Invalid ticket"), {
                type: "danger",
            });
        } else {
            this.registrationId = result.id;
            this.closeLastDialog?.();
            this.closeLastDialog = this.dialog.add(EventRegistrationSummaryDialog, {
                playSound: (type) => this.playSound(type),
                doNextScan: onNextScanTriggered,
                registration: result,
            });
        }
    }

    /**
     * Scan from the dialog rather than through the BarcodeScanner component,
     * which the template here does not mount. The scan itself is the
     * component's, so the two cannot disagree about what a cancelled scan
     * means -- this was a verbatim copy of `openMobileScanner`, and carried
     * its bug of warning the user when they had simply closed the scanner.
     */
    async doNextScan() {
        const barcode = await scanBarcodeOrWarn(
            () => scanBarcode(this.appContext, this.facingMode),
            this.notification,
        );
        if (barcode) {
            await this.onBarcodeScanned(barcode, this.doNextScan.bind(this));
        }
    }

    onClickSelectAttendee() {
        if (this.isMultiEvent) {
            this.actionService.doAction("event.event_registration_action");
        } else {
            this.actionService.doAction("event.event_registration_action_kanban", {
                additionalContext: {
                    active_id: this.eventId,
                    search_default_unconfirmed: true,
                    search_default_confirmed: true,
                },
            });
        }
    }

    onClickBackToEvents() {
        if (this.isMultiEvent) {
            this.actionService.doAction("event.action_event_view", {
                clearBreadcrumbs: true,
            });
        } else {
            this.actionService.restore();
        }
    }
}

registry.category("actions").add("event.event_barcode_scan_view", EventScanView);
