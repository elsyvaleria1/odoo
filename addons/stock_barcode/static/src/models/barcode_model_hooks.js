/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("stock_barcode/models/barcode_model_hooks");

/** @param {import("./barcode_model").default} model */
export function provideBarcodeModel(model) {
    envScope.provide({ model });
}

/** @returns {import("./barcode_model").default} */
export function useBarcodeModel() {
    return envScope.use().model;
}
