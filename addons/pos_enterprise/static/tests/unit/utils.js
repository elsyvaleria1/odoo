import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { PosDataService } from "@point_of_sale/app/services/data_service";
import { uuidv4 } from "@point_of_sale/utils";
import { preparationDisplayService } from "@pos_enterprise/app/services/preparation_display_service";
import {
    getService,
    makeMockEnv,
    MockServer,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

export const setupPosEnvForPrepDisplay = async () => {
    registry.category("services").remove("preparation_display");
    return await setupPosEnv();
};

export const setupPosPrepDisplayEnv = async () => {
    patchWithCleanup(odoo, {
        access_token: uuidv4(),
        info: {
            isEnterprise: true,
        },
        preparation_display: {
            id: 1,
            name: "Test Kitchen Display",
            access_token: uuidv4(),
            bus_channel: uuidv4(),
        },
    });
    patchWithCleanup(session, {
        db: "test",
        data: {
            config_id: 1,
        },
    });

    const services = registry.category("services");
    const serviceNames = ["contextual_utils_service", "debug", "report", "pos"];
    serviceNames.forEach((serviceName) => services.remove(serviceName));

    services.add("pos_data", PosDataService, { force: true });
    services.add("preparation_display", preparationDisplayService, { force: true });

    await makeMockEnv();
    const store = getService("preparation_display");
    return store;
};

export const generateLinesData = (lines = []) => {
    if (!lines.length) {
        return [
            generateLine({
                qty: 3,
                price_unit: 3,
                product_id: 5,
                full_product_name: "TEST",
                tax_ids: [1],
            }),
            generateLine({
                qty: 2,
                price_unit: 3,
                product_id: 6,
                full_product_name: "TEST 2",
                tax_ids: [2],
            }),
        ];
    }
    return lines.map((line) => generateLine(line));
};

export const generateLine = ({
    qty = 1,
    price_unit = 1,
    product_id = 1,
    full_product_name = "Default Product",
    uuid = uuidv4(),
    tax_ids = [],
    price_type = "original",
    attribute_value_ids = [],
    extraLineFields = {},
}) => [
    0,
    0,
    {
        qty,
        attribute_value_ids,
        price_unit,
        uuid,
        price_subtotal: qty * price_unit,
        price_subtotal_incl: qty * price_unit,
        price_type,
        product_id,
        tax_ids,
        full_product_name,
        write_date: "2019-03-11 09:30:06",
        ...extraLineFields,
    },
];

export const generateOrderData = ({ extraOrderFields = {}, lines = [] }) => [
    {
        create_date: "2019-03-11 09:30:06",
        write_date: "2019-03-11 09:30:06",
        access_token: uuidv4(),
        name: "Order 00001",
        date_order: "2019-03-11 09:30:06",
        user_id: 2,
        company_id: 1,
        pricelist_id: 1,
        sequence_number: 1,
        session_id: 1,
        config_id: 1,
        state: "draft",
        ticket_code: "4kqm5",
        tracking_number: "0001",
        uuid: uuidv4(),
        lines: generateLinesData(lines),
        ...extraOrderFields,
    },
];

export const createPrepDisplayTicket = async (store, orderData = {}) => {
    const data = generateOrderData(orderData);
    MockServer.env["pos.order"].sync_from_ui(data);
    await store.data.initData();
};

export const createComboPrepDisplayTicket = async (store) => {
    await createPrepDisplayTicket(store, {
        lines: [
            {
                qty: 1,
                price_unit: 0,
                product_id: 7,
                full_product_name: "Product combo",
                tax_ids: [2],
                uuid: "39335cf8-acee-4275-8985-38dfa4b78a16",
            },
            {
                qty: 1,
                price_unit: 1,
                product_id: 8,
                full_product_name: "Wood chair",
                tax_ids: [2],
                combo_item_id: 1,
                uuid: "cf9c105b-df50-4c1e-b8df-a965b231f9f2",
            },
            {
                qty: 1,
                price_unit: 2,
                product_id: 10,
                full_product_name: "Wood desk",
                tax_ids: [2],
                combo_item_id: 3,
                uuid: "56780df0-c429-4dc8-a838-4c64fe2e40be",
            },
        ],
        extraOrderFields: {
            relations_uuid_mapping: {
                "pos.order.line": {
                    "cf9c105b-df50-4c1e-b8df-a965b231f9f2": {
                        combo_parent_id: "39335cf8-acee-4275-8985-38dfa4b78a16",
                    },
                    "56780df0-c429-4dc8-a838-4c64fe2e40be": {
                        combo_parent_id: "39335cf8-acee-4275-8985-38dfa4b78a16",
                    },
                },
            },
        },
    });
};
