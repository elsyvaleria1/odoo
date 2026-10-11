import { beforeEach, expect, test } from "@odoo/hoot";
import { mountView } from "@web/../tests/web_test_helpers";

import { ResourceResource } from "../_framework/mock_server/mock_models/resource_resource.js";
import { defineResourceModels } from "../resource_test_helpers.js";

defineResourceModels();

beforeEach(() => {
    ResourceResource._records = [
        {
            id: 1,
            name: "admin",
            type: "human",
        },
        {
            id: 2,
            name: "crane",
            type: "material",
        },
        {
            id: 3,
            name: "grid supply",
            type: "intangible",
        },
    ];
});

test("Check the resource avatar icon", async () => {
    await mountView({
        type: "list",
        resModel: "resource.resource",
        arch: `<list>
                    <field name="avatar_128" widget="resource_avatar" options="{'size': [24, 24], 'img_class': 'rounded-3'}" nolabel="1"/>
                    <field name="name"/>
                </list>`,
    });

    expect(".img").toHaveCount(1);
    expect(".o_resource_icon .fa-wrench").toHaveCount(1);
    expect(".o_resource_icon .fa-bolt").toHaveCount(1);
});
