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
        swapFragments: (response) =>
            expect.step(`swapped ${response.fragments.map((f) => f.key).join(",")}`),
    };
    return new QuestionFormBehavior(host, getFixture(), "beforeend", {
        sequence: 1,
        slideId: 3,
        onSaved: () => expect.step("saved"),
        onResetDisplay: () => {},
    });
}

/** @param {Object} [data] @param {string[]} [keys] */
const answer = (data = {}, keys = []) => ({
    fragments: keys.map((key) => ({ key, html: "<div/>", swap: "morph" })),
    events: [],
    redirect: null,
    data,
});

test("a saved question swaps the server's answer in and reports itself saved", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/question_add_or_update", async (request) => {
        const { params } = JSON.parse(
            new TextDecoder("utf-8").decode(await request.arrayBuffer()),
        );
        expect.step(`placeholder ${params.placeholder}`);
        return answer({}, [params.placeholder]);
    });
    getFixture().insertAdjacentHTML(
        "beforeend",
        '<div class="d-contents" data-fragment="website_slides.quiz_question_new.3.4"></div>',
    );
    const form = questionForm();

    await form._createOrUpdateQuestion();

    expect.verifySteps([
        "placeholder website_slides.quiz_question_new.3.4",
        "swapped website_slides.quiz_question_new.3.4",
        "saved",
    ]);
    expect(".o_wslides_js_quiz_validation_error").toHaveClass("d-none");
});

test("a refused question shows the server's error and swaps nothing", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/question_add_or_update", () =>
        answer({ error: "A question needs a correct answer" }),
    );
    const form = questionForm();

    await form._createOrUpdateQuestion();

    expect.verifySteps([]);
    expect(".o_wslides_js_quiz_validation_error").not.toHaveClass("d-none");
    expect(".o_wslides_js_quiz_validation_error_text").toHaveText(
        "A question needs a correct answer",
    );
});
