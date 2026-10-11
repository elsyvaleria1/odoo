import { mailModels } from "@mail/../tests/mail_test_helpers";
import { beforeEach, expect, test } from "@odoo/hoot";
import {
    defineModels,
    getService,
    mountWebClient,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

defineModels(mailModels);

let clientData;

beforeEach(() => {
    clientData = {
        action: {
            tag: "stock_barcode_client_action",
            type: "ir.actions.client",
            res_model: "stock.picking",
            context: {},
        },
        currentState: {
            actions: {},
            data: {
                records: {
                    "barcode.nomenclature": [
                        {
                            id: 1,
                            rule_ids: [],
                        },
                    ],
                    "stock.location": [],
                    "stock.move.line": [],
                    "stock.picking": [],
                },
                nomenclature_id: 1,
            },
            groups: {},
        },
    };
    onRpc("/stock_barcode/get_barcode_data", () =>
        Promise.resolve(clientData.currentState),
    );
});

test("exclamation-triangle when picking is done", async () => {
    const pickingRecord = {
        id: 2,
        state: "done",
        move_line_ids: [],
    };
    clientData.action.context.active_id = pickingRecord.id;
    clientData.currentState.data.records["stock.picking"].push(pickingRecord);

    await mountWebClient({ WebClient: WebClient });
    await getService("action").doAction(clientData.action);
    expect(".o_barcode_pic .fa-triangle-exclamation").toHaveCount(1, {
        message: "Should have warning icon",
    });
});

test.tags("mobile");
test("scan barcode button in mobile device", async () => {
    const pickingRecord = {
        id: 2,
        state: "done",
        move_line_ids: [],
    };
    clientData.action.context.active_id = pickingRecord.id;
    clientData.currentState.data.records["stock.picking"].push(pickingRecord);
    clientData.currentState.groups.group_stock_multi_locations = false;

    await mountWebClient({ WebClient: WebClient });
    await getService("action").doAction(clientData.action);
    expect(".o_stock_mobile_barcode").toHaveCount(1);
});
