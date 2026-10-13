/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions";

export const IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY = "odoo-iot-linked_reports";

export function removeIoTReportIdFromBrowserLocalStorage(report_id) {
    const links = JSON.parse(
        browser.localStorage.getItem(IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY),
    );
    delete links[report_id];
    if (Object.keys(links).length === 0) {
        browser.localStorage.removeItem(IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY);
    } else {
        browser.localStorage.setItem(
            IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY,
            JSON.stringify(links),
        );
    }
}

/**
 * @param report_id
 * @param value
 */
export function setReportIdInBrowserLocalStorage(report_id, value) {
    let links = JSON.parse(
        browser.localStorage.getItem(IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY),
    );
    if (links === null || typeof links !== "object") {
        links = {};
    }
    links[report_id] = value;
    browser.localStorage.setItem(
        IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY,
        JSON.stringify(links),
    );
}

class IoTReportLocalStorage extends Component {
    static template = "iot.delete_printer";
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);

    setup() {
        const links = JSON.parse(
            browser.localStorage.getItem(IOT_REPORT_PREFERENCE_LOCAL_STORAGE_KEY),
        );
        this.state = proxy({ reportList: links ? Object.keys(links) : [] });
        this.orm = useService("orm");
        onWillStart(async () => {
            this.state.reportList = await this.orm.searchRead("ir.actions.report", [
                ["id", "in", this.state.reportList],
            ]);
        });
    }
    removeFromLocal(event, id) {
        removeIoTReportIdFromBrowserLocalStorage(id);
        this.state.reportList = this.state.reportList.filter(
            (report) => report.id !== id,
        );
    }
}

registry
    .category("actions")
    .add("iot_delete_linked_devices_action", IoTReportLocalStorage);
