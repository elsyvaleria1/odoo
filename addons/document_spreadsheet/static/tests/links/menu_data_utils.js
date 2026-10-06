import { getDocumentBasicData } from "@document_spreadsheet/../tests/helpers/data";
import { getMenuServerData as getSpreadsheetMenuServerData } from "@spreadsheet/../tests/links/menu_data_utils";

export const getMenuServerData = () => {
    const res = getSpreadsheetMenuServerData();
    res.models["res.users"] = getDocumentBasicData().models["res.users"];
    return res;
};
