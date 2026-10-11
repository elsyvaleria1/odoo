/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { isBarcodeScannerSupported } from "@web/components/barcode";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class EventRegistrationSummaryDialog extends Component {
    static template = "event.EventRegistrationSummaryDialog";
    static components = { Dialog };
    static props = {
        close: t.function(),
        doNextScan: t.function().optional(),
        model: t.object().optional(),
        playSound: t.function().optional(),
        registration: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
        this.isBarcodeScannerSupported = isBarcodeScannerSupported();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.continueButtonRef = elementRef();
        this.button = proxy({ enabled: true });

        this.registrationStatus = proxy({ value: this.registration.status });

        onMounted(() => {
            if (
                ["already_registered", "need_manual_confirmation"].includes(
                    this.props.registration.status,
                ) &&
                this.props.playSound
            ) {
                this.props.playSound("notify");
            } else if (
                ["not_ongoing_event", "canceled_registration"].includes(
                    this.props.registration.status,
                ) &&
                this.props.playSound
            ) {
                this.props.playSound("error");
            }
            this.continueButtonRef.el?.focus();
        });
    }

    get registration() {
        return this.props.registration;
    }

    get needManualConfirmation() {
        return this.registrationStatus.value === "need_manual_confirmation";
    }

    async onRegistrationConfirm() {
        if (this.registrationStatus.value !== "confirmed_registration") {
            this.button.enabled = false;
            await this.orm
                .call("event.registration", "action_set_done", [this.registration.id])
                .catch(() => (this.button.enabled = true));
            this.registrationStatus.value = "confirmed_registration";
        }
        this.props.close();
        if (this.props.model) {
            this.props.model.load();
        }
        if (this.props.doNextScan) {
            this.onScanNext();
        }
    }

    async undoRegistration() {
        if (
            ["confirmed_registration", "already_registered"].includes(
                this.registrationStatus.value,
            )
        ) {
            await this.orm.call("event.registration", "action_confirm", [
                this.registration.id,
            ]);
        } else if (this.registrationStatus.value === "unconfirmed_registration") {
            await this.orm.call("event.registration", "action_set_draft", [
                this.registration.id,
            ]);
        }
        this.props.close();
        if (this.props.model) {
            this.props.model.load();
        }
    }

    async onRegistrationPrintPdf() {
        await this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: `event.event_registration_report_template_badge/${this.registration.id}`,
        });
        if (this.props.doNextScan) {
            this.onScanNext();
        }
    }

    async onRegistrationView() {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "event.registration",
            res_id: this.registration.id,
            views: [[false, "form"]],
            target: "current",
        });
        this.props.close();
    }

    async onScanNext() {
        this.props.close();
        if (this.isBarcodeScannerSupported) {
            this.props.doNextScan();
        }
    }
}
