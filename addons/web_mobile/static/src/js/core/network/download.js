/** @odoo-module native */
import { download } from "@web/core/network";
import mobile from "@web_mobile/js/services/core";

const _download = download._download;

download._download = async function (options) {
    if (mobile.methods.downloadFile) {
        if (odoo.csrf_token) {
            options.csrf_token = odoo.csrf_token;
        }
        mobile.methods.downloadFile(options);
        return Promise.resolve();
    } else {
        return _download.apply(this, arguments);
    }
};
