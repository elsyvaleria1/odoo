/** @odoo-module native */
import { BarcodeReader } from "@point_of_sale/app/services/barcode_reader_service";
import { patch } from "@web/core/utils/patch";

patch(BarcodeReader.prototype, {
    connectToProxy() {
        this.scanners = this.hardwareProxy.deviceControllers.scanners;
        for (const scanner of Object.values(this.scanners)) {
            scanner.addListener((barcode) => this.scan(barcode.value));
        }
    },

    disconnectFromProxy() {
        if (this.scanners) {
            for (const scanner of Object.values(this.scanners)) {
                scanner.removeListener();
            }
        }
    },
});
