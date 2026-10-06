// @ts-check
import { appContextOf } from "@web/core/app_context";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("discuss_channel_call_public_tour.js", {
    steps: () => [
        {
            content: "The call does not start on the welcome page",
            trigger: ".o-mail-WelcomePage",
            async run() {
                await new Promise((r) => setTimeout(r, 250));
                const rtcService = appContextOf(odoo.__WOWL_DEBUG__.root).services[
                    "discuss.rtc"
                ];
                if (rtcService?.selfSession || rtcService?.state.hasPendingRequest) {
                    console.error("The call should not have started.");
                }
            },
        },
        {
            content: "Click join",
            trigger: "button[title='Join Channel']",
            run: "click",
        },
        {
            content: "Check that the call has started",
            trigger: ".o-discuss-Call",
        },
        {
            content: "Check that current user is in call ('disconnect' button visible)",
            trigger: "button[title='Disconnect']",
        },
    ],
});
