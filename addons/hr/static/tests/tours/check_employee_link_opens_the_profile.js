import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("check_employee_link_opens_the_profile", {
    steps: () => [
        {
            trigger: ".o_form_view:contains('Sonic the Hedgehog')",
            content: "The employee profile opens for an internal user",
            timeout: 10000,
        },
    ],
});
