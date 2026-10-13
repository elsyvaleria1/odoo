import { getBasicServerData } from "@document_spreadsheet/../tests/helpers/data";
import { makeDocumentsSpreadsheetMockEnv } from "@document_spreadsheet/../tests/helpers/model";
import { SpreadsheetAction } from "@document_spreadsheet/bundle/actions/spreadsheet_action";
import { waitFor } from "@odoo/hoot-dom";
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
    getDropdownMenu,
    getMockEnv,
    getService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { Deferred } from "@web/core/utils/concurrency";
import { WebClient } from "@web/webclient/webclient";

/** @typedef {import("@spreadsheet/o_spreadsheet/o_spreadsheet").Model} Model */

/**
 * @param {Object} params
 * @param {string} [params.model]
 * @param {Object} [params.serverData]
 * @param {Function} [params.mockRPC]
 * @param {object} [params.additionalContext]
 * @param {object[]} [params.orderBy]
 * @param {string} [params.actionXmlId]
 * @param {Object} [params.groupBy]
 * @returns {Promise<object>}
 */
export async function spawnListViewForSpreadsheet(params = {}) {
    const { model, serverData, mockRPC } = params;
    await prepareWebClientForSpreadsheet();
    await makeDocumentsSpreadsheetMockEnv({
        serverData: serverData || getBasicServerData(),
        mockRPC,
    });
    const webClient = await mountWithCleanup(WebClient);

    await getService("action").doAction(
        params.actionXmlId || {
            name: "Partners",
            res_model: model || "partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
            context: {
                group_by: params.groupBy || [],
            },
        },
        {
            viewType: "list",
            additionalContext: params.additionalContext || {},
        },
    );

    for (const order of params.orderBy || []) {
        const selector = `thead th.o_column_sortable[data-name='${order.name}']`;
        await contains(selector).click();
        if (order.asc === false) {
            await contains(selector).click();
        }
    }
    return webClient;
}

/**
 * @param {object} params
 * @param {string} [params.model]
 * @param {object} [params.serverData]
 * @param {function} [params.mockRPC]
 * @param {object[]} [params.orderBy]
 * @param {() => Promise<void>} [params.actions]
 * @param {object} [params.additionalContext]
 * @param {number} [params.linesNumber]
 * @param {string} [params.actionXmlId]
 * @returns {Promise<{ model: Model, webClient: object, env: object }>}
 */
export async function createSpreadsheetFromListView(params = {}) {
    const def = new Deferred();
    let spreadsheetAction = {};
    patchWithCleanup(SpreadsheetAction.prototype, {
        setup() {
            super.setup();
            onMounted(() => {
                spreadsheetAction = this;
                def.resolve();
            });
        },
    });
    const webClient = await spawnListViewForSpreadsheet({
        model: params.model,
        serverData: params.serverData,
        mockRPC: params.mockRPC,
        orderBy: params.orderBy,
        additionalContext: params.additionalContext,
        actionXmlId: params.actionXmlId,
    });
    if (params.actions) {
        await params.actions();
    }
    await invokeInsertListInSpreadsheetDialog();
    const value = params.linesNumber ? params.linesNumber.toString() : "10";
    await contains(".o-sp-dialog-meta-threshold-input").edit(value);
    await contains(".modal-content > .modal-footer > .btn-primary").click();
    await def;
    const model = getSpreadsheetActionModel(spreadsheetAction);
    await waitForDataLoaded(model);
    await animationFrame();
    return {
        webClient,
        model,
        env: getSpreadsheetActionEnv(spreadsheetAction),
    };
}

/** @returns */
export async function toggleCogMenuSpreadsheet() {
    await waitFor(".o-dropdown--menu .dropdown-toggle");
    const dropdownMenu = getDropdownMenu(".o_cp_action_menus .dropdown-toggle");
    const dropdownItems = /** @type {HTMLElement[]}*/ ([
        ...dropdownMenu.querySelectorAll(".o-dropdown-item"),
    ]);
    const spreadsheetItem = dropdownItems.find((el) =>
        el.innerText.trim().toLowerCase().includes("spreadsheet"),
    );
    await contains(spreadsheetItem).hover();
    await waitFor(".o-dropdown.show");
}

export async function invokeInsertListInSpreadsheetDialog() {
    getMockEnv().bus.trigger("insert-in-spreadsheet");
    await animationFrame();
}
