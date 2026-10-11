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
 * Get a webclient with a list view.
 * The webclient is already configured to work with spreadsheet (env, registries, ...)
 *
 * @param {Object} params
 * @param {string} [params.model] Model name of the list
 * @param {Object} [params.serverData] Data to be injected in the mock server
 * @param {Function} [params.mockRPC] Mock rpc function
 * @param {object} [params.additionalContext] additional action context
 * @param {object[]} [params.orderBy] orderBy argument
 * @param {string} [params.actionXmlId] If set, the list view will be loaded from this action - will ignore model and domain
 * @param {Object} [params.groupBy]
 * @returns {Promise<object>} Webclient
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
 * Create a spreadsheet model from a List controller
 *
 * @param {object} params
 * @param {string} [params.model] Model name of the list
 * @param {object} [params.serverData] Data to be injected in the mock server
 * @param {function} [params.mockRPC] Mock rpc function
 * @param {object[]} [params.orderBy] orderBy argument
 * @param {() => Promise<void>} [params.actions] orderBy argument
 * @param {object} [params.additionalContext] additional action context
 * @param {number} [params.linesNumber]
 * @param {string} [params.actionXmlId] xmlId of the action to load the list view from - model and domain will be ignored
 *
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

/**
 * Toggle the CogMenu's Spreadsheet sub-dropdown
 *
 * @returns Promise
 */
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
