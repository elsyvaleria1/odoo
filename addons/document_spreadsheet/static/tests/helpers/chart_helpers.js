import { makeDocumentsSpreadsheetMockEnv } from "@document_spreadsheet/../tests/helpers/model";
import { SpreadsheetAction } from "@document_spreadsheet/bundle/actions/spreadsheet_action";
import { getFixture } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { onMounted } from "@odoo/owl";
import { waitForDataLoaded } from "@spreadsheet/helpers/model";
import {
    getSpreadsheetActionEnv,
    getSpreadsheetActionModel,
    prepareWebClientForSpreadsheet,
} from "@spreadsheet_edition/../tests/helpers/webclient_helpers";
import {
    contains,
    getService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { Deferred } from "@web/core/utils/concurrency";
import { WebClient } from "@web/webclient/webclient";

/** @typedef {import("@spreadsheet/o_spreadsheet/o_spreadsheet").Model} Model */

/**
 * @param {object} params
 * @param {string} [params.model]
 * @param {object} [params.serverData]
 * @param {function} [params.mockRPC]
 * @param {any[]} [params.domain]
 * @param {object} [params.additionalContext]
 * @param {string} [params.actionXmlId]
 * @returns {Promise<object>}
 */
export async function spawnGraphViewForSpreadsheet(params = {}) {
    await prepareWebClientForSpreadsheet();
    await makeDocumentsSpreadsheetMockEnv(params);
    const webClient = await mountWithCleanup(WebClient);

    await getService("action").doAction(
        params.actionXmlId || {
            name: "graph view",
            res_model: params.model || "partner",
            type: "ir.actions.act_window",
            views: [[false, "graph"]],
            domain: params.domain,
        },
        {
            viewType: "graph",
            additionalContext: params.additionalContext || {},
        },
    );
    return webClient;
}

/**
 * @typedef {object} CreateGraphTestParams
 * @property {Array} [domain]
 * @property {string} [model]
 * @property {number} [documentId]
 * @property {function} [actions]
 * @property {function} [mockRPC]
 * @property {object} [serverData]
 * @property {object} [additionalContext]
 */

/**
 * @param {CreateGraphTestParams & import("@document_spreadsheet/../tests/helpers/spreadsheet_test_utils").SpreadsheetTestParams} params
 * @returns {Promise<object>}
 */
export async function createSpreadsheetFromGraphView(params = {}) {
    let spreadsheetAction = {};
    const def = new Deferred();
    patchWithCleanup(SpreadsheetAction.prototype, {
        setup() {
            super.setup();
            spreadsheetAction = this;
            onMounted(() => {
                def.resolve();
            });
        },
    });
    const webClient = await spawnGraphViewForSpreadsheet({
        model: params.model,
        serverData: params.serverData,
        mockRPC: params.mockRPC,
        domain: params.domain,
        additionalContext: params.additionalContext || {},
        actionXmlId: params.actionXmlId,
    });
    const target = getFixture();
    if (params.actions) {
        await params.actions(target);
    }
    await contains(target.querySelector(".o_graph_insert_spreadsheet")).click();
    if (params.documentId) {
        await contains(
            `.o-spreadsheet-grid div[data-id='${params.documentId}']`,
        ).focus();
    }
    await contains(
        document.querySelector(".modal-content > .modal-footer > .btn-primary"),
    ).click();
    await def;
    await animationFrame();
    const model = getSpreadsheetActionModel(spreadsheetAction);
    await waitForDataLoaded(model);
    return {
        webClient,
        env: getSpreadsheetActionEnv(spreadsheetAction),
        model,
    };
}

export async function openChartSidePanel(model, env) {
    const sheetId = model.getters.getActiveSheetId();
    const figureId = model.getters.getFigures(sheetId)[0].id;
    model.dispatch("SELECT_FIGURE", { figureId });
    env.openSidePanel("ChartPanel", {});
    await animationFrame();
}
