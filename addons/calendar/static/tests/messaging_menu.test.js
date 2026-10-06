// @ts-check
import { defineCalendarModels } from "@calendar/../tests/calendar_test_helpers";
import {
    click,
    contains,
    openMessagingMenu,
    start,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import {
    asyncStep,
    getService,
    onRpc,
    patchWithCleanup,
    waitForSteps,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineCalendarModels();

test("the Meeting menu also schedules a meeting for later, in the calendar", async () => {
    const link = "https://odoo.test/calendar/join_videocall/abc123";
    onRpc("calendar.event", "get_discuss_videocall_location", () => link);
    await start();
    patchWithCleanup(getService("action"), {
        /**
         * @param {any} action
         * @param {any} options
         */
        async doAction(action, options) {
            const context = options?.additionalContext ?? {};
            asyncStep(
                `${action} ${context.default_access_token} ${context.default_videocall_location} ${context.return_to_parent_breadcrumb}`,
            );
        },
    });
    await openMessagingMenu("meeting");
    await click(".o-mail-MessagingMenu-action[title='New Meeting']");
    await contains(".o-mail-MessagingMenu-actionMenu .dropdown-item", { count: 2 });
    await contains(".o-mail-MessagingMenu-actionMenu .dropdown-item:eq(0)", {
        text: "Start Now",
    });
    await click(".o-mail-MessagingMenu-actionMenu .dropdown-item", {
        text: "Schedule for later",
    });
    await waitForSteps([`calendar.action_calendar_event abc123 ${link} true`]);
});
