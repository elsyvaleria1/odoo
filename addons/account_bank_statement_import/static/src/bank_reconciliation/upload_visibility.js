/** @odoo-module native */

const synchronizedModes = ["online_sync", "l10n_be_codabox"];

export function showUploadButton(context) {
    return !synchronizedModes.includes(context?.bank_statements_source);
}
