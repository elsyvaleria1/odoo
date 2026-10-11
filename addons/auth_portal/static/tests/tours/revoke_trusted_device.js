import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("auth_portal_revoke_trusted_device", {
    url: "/my/security",
    steps: () => [
        {
            content: "The trusted device set up by the test is listed",
            trigger: "td:contains(test-device)",
        },
        {
            content: "Revoke it",
            trigger: ".o_totp_portal_revoke_device",
            run: "click",
        },
        {
            content: "Revoking a device is an identity-check operation",
            trigger:
                "form strong:contains(Please enter your password to confirm you own this account)",
        },
        {
            content: "Input password",
            trigger: "form input[name=password]",
            run: "edit portal",
        },
        {
            content: "Confirm",
            trigger: ".modal-footer button:contains(Confirm Password)",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "The device is gone, and 2FA is still enabled",
            trigger: "button:contains(Disable two-factor authentication)",
        },
        {
            content: "No revoke control is left",
            trigger: "body:not(:has(.o_totp_portal_revoke_device))",
        },
    ],
});
