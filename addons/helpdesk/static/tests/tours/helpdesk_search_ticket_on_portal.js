import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("helpdesk_search_ticket_on_portal_tour", {
    url: "/my/tickets",
    steps: () => [
        {
            trigger: ".o_portal_search_panel .dropdown-toggle",
            content: "click on dropdown.",
            run: "click",
        },
        {
            trigger:
                '.o_portal_search_panel .dropdown-menu a:contains("Search Tickets")',
            content: "select Search Tickets.",
            run: "click",
        },
        {
            content: "Type name of ticket",
            trigger: '.o_portal_search_panel input[name="search"]',
            run: "edit lamp stand",
        },
        {
            content: "search Ticket",
            trigger: ".o_portal_search_panel button[type=submit]",
            run: "click",
        },
        {
            content: "the search results replace the list in place",
            trigger: '.o_portal_search_panel input[name="search"][value="lamp stand"]',
        },
        {
            trigger: "table > tbody > tr a:has(span:contains(lamp stand))",
            content: "click on ticket.",
            run: "click",
            expectUnloadPage: true,
        },
        {
            trigger: "#chatterRoot:shadow div.o-mail-Thread-empty",
        },
    ],
});
