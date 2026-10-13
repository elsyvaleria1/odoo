/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { BarcodeDialog } from "@web/components/barcode";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";

export class BarcodeInput extends Component {
    static template = "barcodes.BarcodeInput";
    static props = {
        onSubmit: t.function(),
        placeholder: t.string().optional(_t("Enter a barcode...")),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.state = proxy({
            barcode: "",
        });
        this.barcodeManual = elementRef();
        onMounted(() => {
            this.barcodeManual.el?.focus();
        });
    }

    submit() {
        const barcode = this.state.barcode.trim();
        if (barcode) {
            this.props.onSubmit(barcode);
        }
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        if (getActiveHotkey(ev) === "enter") {
            this.submit();
        }
    }
}

export class ManualBarcodeScanner extends BarcodeDialog {
    static template = "barcodes.ManualBarcodeScanner";
    static components = {
        ...BarcodeDialog.components,
        BarcodeInput,
    };
    static props = { ...BarcodeDialog.props, placeholder: t.string().optional() };
}
