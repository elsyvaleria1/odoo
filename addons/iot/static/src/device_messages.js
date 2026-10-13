/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export const deviceMessages = registry.category("iot_device_messages");

export const PRINTER_MESSAGES = {
    ERROR_FAILED: _t("Failed to initiate print"),
    ERROR_OFFLINE: _t("Printer is not ready"),
    ERROR_TIMEOUT: _t("Printing timed out"),
    ERROR_NO_PAPER: _t("Out of paper"),
    ERROR_UNREACHABLE: _t("Printer is unreachable"),
    ERROR_UNKNOWN: _t("Unknown printer error occurred"),
    WARNING_LOW_PAPER: _t("Paper is low"),
};

deviceMessages.add("printer", {
    messages: PRINTER_MESSAGES,
    defaultMessage: _t("Test page printed"),
});

/**
 * @param {string} type
 * @param {{status?: string, message?: string}} event
 * @returns {{message: string, defaultMessage: string}}
 */
export function readDeviceEvent(type, event) {
    const spec = deviceMessages.get(type, {});
    spec.normalize?.(event);
    return {
        message: spec.messages?.[event.message] ?? event.message,
        defaultMessage: spec.defaultMessage ?? _t("Device is operational"),
    };
}
