import { describe, expect, test } from "@odoo/hoot";
import {
    contains,
    makeMockServer,
    mountView,
    serverState,
} from "@web/../tests/web_test_helpers";
import { now, serializeDateTime } from "@web/core/l10n/dates";

import { defineSignModels } from "./mock_server/mock_models/sign_model.js";

describe.current.tags("desktop");
defineSignModels();

test("list activity widget: sign button in dropdown", async () => {
    const { env } = await makeMockServer();
    const activityId = env["mail.activity"].create({
        summary: "Sign a new contract",
        activity_category: "sign_request",
        date_deadline: serializeDateTime(now().add({ days: 1 })),
        can_write: true,
        state: "planned",
        user_id: serverState.userId,
        activity_type_id: 1,
    });
    env["res.partner"].write(serverState.partnerId, {
        activity_ids: [activityId],
        activity_state: "today",
    });
    env["res.users"].write(serverState.userId, {
        activity_ids: [activityId],
        activity_summary: "Sign a new contract",
        activity_type_id: 1,
    });

    await mountView({
        type: "list",
        resModel: "res.users",
        arch: `<list>
            <field name="activity_ids" widget="list_activity"/>
        </list>`,
    });
    expect(".o-mail-ListActivity-summary").toHaveText("Sign a new contract");
    await contains(".o-mail-ActivityButton").click();
    expect(".o-mail-ActivityListPopoverItem-markAsDone").toHaveCount(0);
    expect(".o-mail-ActivityListPopoverItem-requestSign").toHaveCount(1);
});
