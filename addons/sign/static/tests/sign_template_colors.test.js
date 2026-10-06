import { expect, test } from "@odoo/hoot";
import { SignTemplate } from "@sign/backend_components/sign_template/sign_template_action";

test("removing a signer makes its color available again", () => {
    const template = Object.create(SignTemplate.prototype);
    template.state = {
        signers: Array.from({ length: 55 }, (_, colorId) => ({ colorId })),
    };
    expect(template.getNextColor()).toBe(0);
    template.state.signers.splice(27, 1);
    expect(template.getNextColor()).toBe(27);
    template.state.signers.splice(0, 1);
    expect(template.getNextColor()).toBe(0);
});
