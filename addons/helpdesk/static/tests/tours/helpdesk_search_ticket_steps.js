class HelpdeskSearchTicketSteps {
    _searchTickets() {
        return {
            content: "search Ticket",
            trigger: ".oi-search",
            run: "click",
            expectUnloadPage: true,
        };
    }
}

export default HelpdeskSearchTicketSteps;
