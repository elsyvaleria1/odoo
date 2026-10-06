import { getMockEnv, makeMockEnv, serverState } from "@web/../tests/web_test_helpers";

import { getDocumentsModel } from "./data.js";

/**
 * @param {Record<string, any[]>} serverData
 */
export function setDocumentsServerData(serverData) {
    for (const [modelName, records] of Object.entries(serverData)) {
        if (!records?.length) {
            continue;
        }
        const PyModel = getDocumentsModel(modelName);
        if (!PyModel) {
            throw new Error(`Model ${modelName} not found inside DocumentsModels`);
        }
        PyModel._records = records;
    }
}

/**
 * @param {{ serverData?: Record<string, any[]> }} [params]
 */
export async function makeDocumentsMockEnv(params) {
    if (params?.serverData) {
        setDocumentsServerData(params.serverData);
    }
    const env = getMockEnv() || (await makeMockEnv());
    env.services["mail.store"].odoobot = {
        userId: serverState.odoobotId,
    };
    return env;
}
