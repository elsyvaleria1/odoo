import { defineDocumentSpreadsheetModels } from "@document_spreadsheet/../tests/helpers/data";
import { createSpreadsheet } from "@document_spreadsheet/../tests/helpers/spreadsheet_test_utils";
import { describe, expect, test } from "@odoo/hoot";

defineDocumentSpreadsheetModels();
describe.current.tags("desktop");

test("Filter component is visible even without data source", async function () {
    await createSpreadsheet();
    expect(".o_topbar_filter_icon").toHaveCount(1);
});
