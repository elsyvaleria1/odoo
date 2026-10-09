import { describe, expect, getFixture, test } from "@odoo/hoot";
import { makeMockEnv, onRpc } from "@web/../tests/web_test_helpers";
import { QuestionFormBehavior } from "@website_slides/interactions/quiz_question_form";

describe.current.tags("interaction_dev");

function questionForm() {
    const el = document.createElement("div");
    el.innerHTML = `
        <form>
            <div class="o_wslides_quiz_question"><input type="text" value="Capital of France?"/></div>
            <div class="o_wslides_js_quiz_answer">
                <input type="radio" checked=""/>
                <input type="text" class="o_wslides_js_quiz_answer_value" value="Paris"/>
            </div>
        </form>
        <div class="o_wslides_js_quiz_validation_error d-none">
            <span class="o_wslides_js_quiz_validation_error_text"></span>
        </div>`;
    getFixture().append(el);
    const host = {
        renderAt: () => [el],
        addListener: () => {},
        waitFor: (promise) => promise,
    };
    return new QuestionFormBehavior(host, getFixture(), "beforeend", {
        sequence: 1,
        slideId: 3,
        onDisplayCreated: (_form, html) => expect.step(`created ${html}`),
        onDisplayUpdated: (_form, html) => expect.step(`updated ${html}`),
        onResetDisplay: () => {},
    });
}

test("a saved question hands its rendered HTML to the display", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/question_add_or_update", () => ({
        question_html: "<div>Capital of France?</div>",
    }));
    const form = questionForm();

    await form._createOrUpdateQuestion({ update: false });

    expect.verifySteps(["created <div>Capital of France?</div>"]);
    expect(".o_wslides_js_quiz_validation_error").toHaveClass("d-none");
});

test("a refused question shows the server's error and displays nothing", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/question_add_or_update", () => ({
        error: "A question needs a correct answer",
    }));
    const form = questionForm();

    await form._createOrUpdateQuestion({ update: true });

    expect.verifySteps([]);
    expect(".o_wslides_js_quiz_validation_error").not.toHaveClass("d-none");
    expect(".o_wslides_js_quiz_validation_error_text").toHaveText(
        "A question needs a correct answer",
    );
});
