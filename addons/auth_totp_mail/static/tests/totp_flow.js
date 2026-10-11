import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

function openAccountSettingsTab() {
    return [
        {
            content: "Go to settings",
            trigger: '[data-menu-xmlid="base.menu_administration"]',
            run: "click",
        },
        {
            content: "Wait for page",
            trigger: '.o_menu_brand:contains("Settings")',
        },
        {
            content: "Open Users menu",
            trigger: '[data-menu-xmlid="base.menu_users"]',
            run: "click",
        },
        {
            content: "Open Users view",
            trigger: '[data-menu-xmlid="base.menu_action_res_users"]',
            run: function (helpers) {
                const breadcrumb = document.querySelector(".breadcrumb");
                if (!breadcrumb || !breadcrumb.textContent.includes("Users")) {
                    helpers.click();
                } else {
                    helpers.click('[data-menu-xmlid="base.menu_users"]');
                }
            },
        },
    ];
}

registry.category("web_tour.tours").add("totp_admin_self_invite", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        ...openAccountSettingsTab(),
        {
            content: "open the user's form",
            trigger: "td.o_data_cell:contains(admin)",
            run: "click",
        },
        {
            content: "go to Security Tab",
            trigger: "a.nav-link:contains(Security)",
            run: "click",
        },
        {
            content: "check that user cannot invite themselves to use 2FA.",
            trigger: "body:not(:has(button:contains(Invite to use 2FA)))",
        },
    ],
});

registry.category("web_tour.tours").add("totp_admin_invite", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        ...openAccountSettingsTab(),
        {
            content: "open the user's form",
            trigger: "td.o_data_cell:contains(test_user)",
            run: "click",
        },
        {
            content: "go to security Tab",
            trigger: "a.nav-link:contains(Security)",
            run: "click",
        },
        {
            content: "check that test_user user can be invited to use 2FA.",
            trigger: "button:contains(Invite to use 2FA)",
        },
    ],
});
