import { expect, test } from "@odoo/hoot";
import { contains, defineModels, webModels } from "@web/../tests/web_test_helpers";
import {
    defineWebsiteModels,
    setupWebsiteBuilder,
} from "@website/../tests/builder/website_helpers";

const formSpecRecords = [
    {
        id: 123,
        model: "website_studio.custom_stuff",
        name: "Custom stuff",
        state: "base",
        website_form_access: true,
        website_form_label: "Create some stuff",
        website_form_key: "website_studio.stuff",
    },
    {
        id: 85,
        model: "res.partner",
        name: "Contact",
        state: "base",
        website_form_label: "Create a Customer",
        website_form_key: "create_customer",
    },
    {
        id: 184,
        model: "mail.mail",
        name: "Outgoing Mails",
        state: "base",
        website_form_label: "Send an E-mail",
        website_form_key: "send_mail",
    },
];

class IrModel extends webModels.IrModel {
    _views = {
        "list,website_studio.select_simple_ir_model": `
            <list>
                <field name="name"/>
                <field name="model"/>
                <field name="state"/>
            </list>
        `,
    };

    get_compatible_form_models() {
        return formSpecRecords;
    }

    search_read() {
        return formSpecRecords;
    }

    web_search_read() {
        return {
            length: formSpecRecords.length,
            records: formSpecRecords,
        };
    }

    web_save(ids, values) {
        const result = formSpecRecords.filter((record) => record.id in ids);
        for (const record of result) {
            Object.assign(record, values);
        }
        expect.step(`webSave ${ids} ${JSON.stringify(values)}`);
        return result;
    }
}

defineWebsiteModels();
defineModels([IrModel]);

test("change action to More models", async () => {
    await setupWebsiteBuilder(
        `<section class="s_website_form"><form data-model_name="mail.mail">
            <div class="s_website_form_field"><label class="s_website_form_label" for="contact1">Name</label><input id="contact1" class="s_website_form_input"/></div>
            <div class="s_website_form_submit">
                <div class="s_website_form_label"/>
                <a>Submit</a>
            </div>
        </form></section>`,
    );

    await contains(":iframe section").click();
    await contains("div:has(>span:contains('Action')) + div button").click();
    await contains("div.o-dropdown-item:contains('More models')").click();
    await contains(".o_data_cell:contains('Custom stuff')").click();
    expect(":iframe form .s_website_form_field").toHaveCount(0);
    expect(":iframe form .s_website_form_submit").toHaveCount(1);
});

test("form access is in history", async () => {
    await setupWebsiteBuilder(
        `<section class="s_website_form"><form data-model_name="website_studio.custom_stuff">
            <div class="s_website_form_submit">
                <div class="s_website_form_label"/>
                <a>Submit</a>
            </div>
        </form></section>`,
    );

    await contains(":iframe section").click();
    expect("[data-action-id='studioToggleFormAccess'] input:checked").toHaveCount(1);
    await contains("[data-action-id='studioToggleFormAccess'] input").click();
    expect.verifySteps(['webSave 123 {"website_form_access":false}']);
    expect("[data-action-id='studioToggleFormAccess'] input:not(:checked)").toHaveCount(
        1,
    );
    await contains("[data-action-id='studioToggleFormAccess'] input").click();
    expect.verifySteps(['webSave 123 {"website_form_access":true}']);
    expect("[data-action-id='studioToggleFormAccess'] input:checked").toHaveCount(1);
    await contains(".o-snippets-top-actions .fa-undo").click();
    expect.verifySteps(['webSave 123 {"website_form_access":false}']);
    expect("[data-action-id='studioToggleFormAccess'] input:not(:checked)").toHaveCount(
        1,
    );
    await contains(".o-snippets-top-actions .fa-undo").click();
    expect.verifySteps(['webSave 123 {"website_form_access":true}']);
    expect("[data-action-id='studioToggleFormAccess'] input:checked").toHaveCount(1);
    await contains(".o-snippets-top-actions .fa-arrow-rotate-right").click();
    expect.verifySteps(['webSave 123 {"website_form_access":false}']);
    expect("[data-action-id='studioToggleFormAccess'] input:not(:checked)").toHaveCount(
        1,
    );
    await contains(".o-snippets-top-actions .fa-arrow-rotate-right").click();
    expect("[data-action-id='studioToggleFormAccess'] input:checked").toHaveCount(1);
    expect.verifySteps(['webSave 123 {"website_form_access":true}']);
});
