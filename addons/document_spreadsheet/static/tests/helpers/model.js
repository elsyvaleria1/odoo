import { makeSpreadsheetMockEnv } from "@spreadsheet/../tests/helpers/model";
import { serverState } from "@web/../tests/web_test_helpers";

import { getDocumentBasicData } from "./data.js";

export const makeDocumentsSpreadsheetMockEnv = async (params = {}) => {
    params.serverData = ensureDocumentsRequiredRecords(params.serverData);
    const env = await makeSpreadsheetMockEnv(params);
    env.services["mail.store"].odoobot = { userId: serverState.odoobotId };
    return env;
};

export const ensureDocumentsRequiredRecords = (serverData) => {
    const res = { ...serverData };
    if (!serverData?.models?.["res.users"]) {
        const resUsers = getDocumentBasicData().models["res.users"];
        if (!serverData || !serverData.models) {
            res.models = { "res.users": resUsers };
        } else if (!serverData.models["res.users"]) {
            res.models["res.users"] = resUsers;
        }
    }
    return res;
};
