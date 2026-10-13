// @ts-check
import {
    click,
    contains,
    mailModels,
    openView,
    registerArchs,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { ResFake } from "@mail/../tests/mock_server/mock_models/res_fake";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { disableAnimations, mockDate } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    patchWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { Domain } from "@web/core/domain";
import { now, serializeDate } from "@web/core/l10n/dates";
import { deepEqual } from "@web/core/utils/collections/objects";
import { DynamicList, RelationalModel } from "@web/model/relational_model";

describe.current.tags("desktop");

class ActivityResFake extends ResFake {
    activity_state = fields.Selection({
        selection: [
            ["overdue", "Overdue"],
            ["today", "Today"],
            ["planned", "Planned"],
            ["done", "Done"],
        ],
    });
}
defineModels({ ...mailModels, ResFake: ActivityResFake });

const archs = {
    "res.fake,false,activity": `
        <activity string="Fakes">
            <templates>
                <div t-name="activity-box">
                    <field name="name"/>
                </div>
            </templates>
        </activity>
    `,
};

/**
 * @param {Function} load
 * @param {Object} params
 */
function withoutDoneActivityLeaf(load, params) {
    if (params.domain) {
        const domain = new Domain(params.domain);
        const newDomain = Domain.removeDomainLeaves(domain.toList(), [
            "activity_ids.active",
        ]);
        if (!deepEqual(domain.toList(), newDomain.toList())) {
            return load({
                ...params,
                domain: newDomain.toList(),
                context: { ...params.context, active_test: false },
            });
        }
    }
    return load(params);
}

/** @type {Awaited<ReturnType<typeof startServer>>} */
let pyEnv;

beforeEach(async () => {
    disableAnimations();
    mockDate("2023-04-08 10:00:00", 0);
    for (const Model of [DynamicList, RelationalModel]) {
        patchWithCleanup(Model.prototype, {
            /** @param {Object} params */
            async load(params) {
                return withoutDoneActivityLeaf(super.load.bind(this), params);
            },
        });
    }
    pyEnv = await startServer();
    pyEnv["mail.activity.type"].unlink(pyEnv["mail.activity.type"].search([]));
});

/**
 * @param {string} typeName
 * @returns {number}
 */
function createActivity(typeName) {
    const [typeId] = pyEnv["mail.activity.type"].create([{ name: typeName }]);
    const [recordId] = pyEnv["res.fake"].create([{ name: `${typeName} record` }]);
    const [activityId] = pyEnv["mail.activity"].create([
        {
            res_model: "res.fake",
            res_id: recordId,
            display_name: `${typeName} activity`,
            date_deadline: serializeDate(now().add({ days: 3 })),
            can_write: true,
            state: "planned",
            activity_type_id: typeId,
            user_id: serverState.userId,
        },
    ]);
    pyEnv["res.fake"].write([recordId], { activity_ids: [activityId] });
    return typeId;
}

async function openActivityView() {
    await openView({
        res_model: "res.fake",
        views: [[false, "activity"]],
    });
}

test("an activity type created after a column was hidden shows as a column", async () => {
    createActivity("Email");
    createActivity("Call");
    await start();
    registerArchs(archs);
    await openActivityView();
    await contains(".o_activity_type_cell", { text: "Call" });
    await click(".o_optional_columns_dropdown_toggle");
    await click(".o-dropdown-item", { text: "Call" });
    await contains(".o_activity_type_cell", { text: "Call", count: 0 });
    await contains(".o_activity_type_cell", { text: "Email" });

    createActivity("Meeting");
    await openActivityView();
    await contains(".o_activity_type_cell", { text: "Meeting" });
    await contains(".o_activity_type_cell", { text: "Email" });
    await contains(".o_activity_type_cell", { text: "Call", count: 0 });
    expect(".o_activity_type_cell").toHaveCount(2);
});

test("a hidden column comes back when it is toggled again", async () => {
    createActivity("Email");
    createActivity("Call");
    await start();
    registerArchs(archs);
    await openActivityView();
    await click(".o_optional_columns_dropdown_toggle");
    await click(".o-dropdown-item", { text: "Call" });
    await contains(".o_activity_type_cell", { text: "Call", count: 0 });
    await click(".o-dropdown-item", { text: "Call" });
    await contains(".o_activity_type_cell", { text: "Call" });
});

test("columns chosen before hidden columns were stored keep their visibility", async () => {
    const emailTypeId = createActivity("Email");
    createActivity("Call");
    browser.localStorage.setItem(
        "activity_columns,res.fake,false",
        String(emailTypeId),
    );
    await start();
    registerArchs(archs);
    await openActivityView();
    await contains(".o_activity_type_cell", { text: "Email" });
    await contains(".o_activity_type_cell", { text: "Call", count: 0 });
    expect(browser.localStorage.getItem("activity_columns,res.fake,false")).toBe(null);
});
