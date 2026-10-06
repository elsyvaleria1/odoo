/** @odoo-module native */

// The codabox literal is a layering concession inherited from upstream: this
// module does not depend on l10n_be_codabox, but the upload button must stay
// hidden for journals whose statements arrive through a synchronized source.
const synchronizedModes = ["online_sync", "l10n_be_codabox"];

export function showUploadButton(context) {
    return !synchronizedModes.includes(context?.bank_statements_source);
}
