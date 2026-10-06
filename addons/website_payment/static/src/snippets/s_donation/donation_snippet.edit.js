/** @odoo-module native */
import { registry } from "@web/core/registry";
import { DonationSnippet } from "@website_payment/snippets/s_donation/donation_snippet";

const DonationSnippetEdit = (I) =>
    class extends I {
        onDonateClick() {}
    };

registry.category("public.interactions.edit").add("website_payment.donation_snippet", {
    Interaction: DonationSnippet,
    mixin: DonationSnippetEdit,
});
