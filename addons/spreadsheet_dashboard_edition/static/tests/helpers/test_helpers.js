import { animationFrame } from "@odoo/hoot-mock";
import { onMounted } from "@odoo/owl";
import { makeSpreadsheetMockEnv } from "@spreadsheet/../tests/helpers/model";
import { DashboardEditAction } from "@spreadsheet_dashboard_edition/bundle/action/dashboard_edit_action";
import {
    getSpreadsheetActionEnv,
    getSpreadsheetActionModel,
    prepareWebClientForSpreadsheet,
} from "@spreadsheet_edition/../tests/helpers/webclient_helpers";
import {
    getService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { Deferred } from "@web/core/utils/concurrency";
import { WebClient } from "@web/webclient/webclient";

import { getDashboardBasicServerData } from "./test_data.js";

/**
 * @typedef {import("@spreadsheet/../tests/helpers/data").ServerData} ServerData

 * @typedef {object} SpreadsheetTestParams
 * @property {number} [spreadsheetId]
 * @property {ServerData} [serverData] Data to be injected in the mock server
 * @property {Function} [mockRPC] Mock rpc function
 */

/**
 * @param {SpreadsheetTestParams} [params]
 */
export async function createDashboardEditAction(params) {
    /** @type {any} */
    let spreadsheetAction;
    const actionMountedDef = new Deferred();
    patchWithCleanup(DashboardEditAction.prototype, {
        setup() {
            super.setup();
            onMounted(() => actionMountedDef.resolve());
            spreadsheetAction = this;
        },
    });
    const serverData = params?.serverData || getDashboardBasicServerData();
    let spreadsheetId = params?.spreadsheetId;
    if (!spreadsheetId) {
        spreadsheetId = createNewDashboard(serverData);
    }
    await prepareWebClientForSpreadsheet();
    await makeSpreadsheetMockEnv({
        serverData,
        mockRPC: params?.mockRPC,
    });
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "action_edit_dashboard",
        params: {
            spreadsheet_id: spreadsheetId,
        },
    });
    await actionMountedDef;
    await animationFrame();
    return {
        model: getSpreadsheetActionModel(spreadsheetAction),
        env: getSpreadsheetActionEnv(spreadsheetAction),
    };
}

/**
 *
 * @param {ServerData} serverData
 * @param {object} [data] spreadsheet data
 * @returns {number}
 */
export function createNewDashboard(serverData, data) {
    if (!serverData.models["spreadsheet.dashboard"].records) {
        serverData.models["spreadsheet.dashboard"].records = [];
    }
    const dashboards = serverData.models["spreadsheet.dashboard"].records;
    const maxId = dashboards.length ? Math.max(...dashboards.map((d) => d.id)) : 0;
    const spreadsheetId = maxId + 1;
    dashboards.push({
        id: spreadsheetId,
        name: "Untitled Dashboard",
        spreadsheet_data: data ? JSON.stringify(data) : "{}",
    });
    return spreadsheetId;
}
