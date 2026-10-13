import { animationFrame } from "@odoo/hoot-mock";
import { Model } from "@odoo/o-spreadsheet";
import { OdooDataProvider } from "@spreadsheet/data_sources/odoo_data_provider";
import {
    defineActions,
    defineMenus,
    getMockEnv,
    makeMockEnv,
    onRpc,
} from "@web/../tests/web_test_helpers";

import { setCellContent } from "./commands.js";
import { addRecordsFromServerData, addViewsFromServerData } from "./data.js";

/**
 * @typedef {import("@spreadsheet/../tests/helpers/data").ServerData} ServerData
 * @typedef {import("@spreadsheet/helpers/model").OdooSpreadsheetModel} OdooSpreadsheetModel
 */

export function setupDataSourceEvaluation(model) {
    model.config.custom.odooDataProvider.addEventListener("data-source-updated", () => {
        const sheetId = model.getters.getActiveSheetId();
        model.dispatch("EVALUATE_CELLS", { sheetId });
    });
}

/**
 * @param {object} params
 * @param {object} [params.spreadsheetData]
 * @param {object} [params.modelConfig]
 * @param {ServerData} [params.serverData]
 * @param {function} [params.mockRPC]
 * @returns {Promise<{ model: OdooSpreadsheetModel, env: Object }>}
 */
export async function createModelWithDataSource(params = {}) {
    const env = await makeSpreadsheetMockEnv(params);
    const config = params.modelConfig;
    /** @type */
    const model = new Model(params.spreadsheetData, {
        ...config,
        custom: {
            env,
            odooDataProvider: new OdooDataProvider(env),
            ...config?.custom,
        },
    });
    env.model = model;
    setupDataSourceEvaluation(model);
    await animationFrame();
    return { model, env };
}

/**
 * @param {object} params
 * @param {object} [params.spreadsheetData]
 * @param {ServerData} [params.serverData]
 * @param {function} [params.mockRPC]
 * @returns {Promise<Object>}
 */
export async function makeSpreadsheetMockEnv(params = {}) {
    if (params.mockRPC) {
        onRpc((args) => params.mockRPC(args.route, args));
    }
    if (params.serverData?.menus) {
        defineMenus(Object.values(params.serverData.menus));
    }
    if (params.serverData?.actions) {
        defineActions(Object.values(params.serverData.actions));
    }
    if (params.serverData?.models) {
        addRecordsFromServerData(params.serverData);
    }
    if (params.serverData?.views) {
        addViewsFromServerData(params.serverData);
    }
    const env = getMockEnv() || (await makeMockEnv());
    return env;
}

export function createModelFromGrid(grid) {
    const model = new Model();
    for (const xc in grid) {
        if (grid[xc] !== undefined) {
            setCellContent(model, xc, grid[xc]);
        }
    }
    return model;
}
