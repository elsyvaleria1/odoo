import { describe, expect, test } from "@odoo/hoot";
import { click, queryOne } from "@odoo/hoot-dom";
import { animationFrame, Deferred } from "@odoo/hoot-mock";
import {
    getInteraction,
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { CoursePage } from "@website_slides/interactions/course_page";
import { FullscreenPlayer } from "@website_slides/interactions/fullscreen_player";

setupInteractionWhiteList("website_slides.fullscreen_player");
describe.current.tags("interaction_dev");

/**
 * @param {{ id: number, name: string, category: string, active?: boolean }[]} slides
 */
function fullscreenPage(slides) {
    const items = slides
        .map(
            ({ id, name, category, active }) => `
            <li class="o_wslides_fs_sidebar_list_item ${active ? "active" : ""}"
                data-id="${id}" data-can-access="True" data-name="${name}"
                data-category="${category}" data-slug="slide-${id}"
                data-has-question="${category === "quiz" ? 1 : 0}" data-is-quiz="0"
                data-can-self-mark-completed="${category === "quiz" ? "False" : "True"}"
                data-can-self-mark-uncompleted="True" data-is-member="True">
                <div class="o_wslides_sidebar_done_button" data-id="${id}"
                    data-can-self-mark-completed="${category === "quiz" ? "False" : "True"}"
                    data-can-self-mark-uncompleted="True" data-is-member="True">
                    <button class="o_wslides_button_complete">done</button>
                </div>
                <a class="o_wslides_fs_slide_name" href="#">${name}</a>
            </li>`,
        )
        .join("");
    return `
        <div class="o_wslides_fs_main" data-channel-id="7" data-channel-enroll="public">
            <a class="o_wslides_fs_toggle_sidebar" href="#">Lessons</a>
            <div class="o_wslides_fs_sidebar"><ul>${items}</ul></div>
            <div class="o_wslides_fs_content"></div>
        </div>`;
}

function stubCompletionButton() {
    patchWithCleanup(CoursePage.prototype, {
        toggleCompletionButton(slideData, completed) {
            expect.step(`button ${slideData.id} ${completed}`);
        },
    });
}

test("navigating away while a quiz loads shows the newer slide, not the quiz", async () => {
    stubCompletionButton();
    const quizReply = new Deferred();
    onRpc("/slides/slide/quiz/get", () => quizReply);
    onRpc("/slides/slide/get_html_content", () => ({ html_content: "<p>Second</p>" }));
    onRpc("/slides/slide/set_completed", () => ({ channel_completion: 50 }));
    await startInteractions(
        fullscreenPage([
            { id: 1, name: "Quiz", category: "quiz", active: true },
            { id: 2, name: "Article", category: "article" },
        ]),
    );
    await animationFrame();

    await click(
        ".o_wslides_fs_sidebar_list_item[data-id='2'] .o_wslides_fs_slide_name",
    );
    await animationFrame();
    expect(".o_wslides_fs_content .o_wslide_fs_article_content").toHaveText("Second");
    expect.verifySteps(["button 2 true"]);

    quizReply.resolve({ slide_questions: [], slide_description: "" });
    await animationFrame();
    expect(".o_wslides_fs_content .o_wslide_fs_article_content").toHaveText("Second");
    expect(".o_wslides_fs_content .o_wslides_fs_quiz_container").toHaveCount(0);
});

test("an article the server refuses renders empty, never 'undefined'", async () => {
    stubCompletionButton();
    onRpc("/slides/slide/get_html_content", () => ({ error: "slide_access" }));
    onRpc("/slides/slide/set_completed", () => ({ error: "slide_access" }));
    await startInteractions(
        fullscreenPage([{ id: 1, name: "Article", category: "article", active: true }]),
    );
    await animationFrame();

    expect(".o_wslide_fs_article_content").toHaveCount(1);
    expect(queryOne(".o_wslide_fs_article_content").textContent).toBe("");
});

test("a refused completion leaves the fullscreen slide uncompleted", async () => {
    stubCompletionButton();
    onRpc("/slides/slide/get_html_content", () => ({ html_content: "<p>A</p>" }));
    onRpc("/slides/slide/set_completed", () => {
        expect.step("set_completed");
        return { error: "public_user" };
    });
    const { core } = await startInteractions(
        fullscreenPage([{ id: 1, name: "Article", category: "article", active: true }]),
    );
    await animationFrame();

    expect.verifySteps(["set_completed"]);
    expect(Boolean(getInteraction(core, FullscreenPlayer).slides[0].completed)).toBe(
        false,
    );
});

test("completing from the sidebar button (string id) updates the fullscreen slide", async () => {
    stubCompletionButton();
    onRpc("/slides/slide/get_html_content", () => ({ html_content: "<p>A</p>" }));
    onRpc("/slides/slide/set_completed", () => {
        expect.step("set_completed");
        return { channel_completion: 50 };
    });
    const { core } = await startInteractions(
        fullscreenPage([
            { id: 1, name: "Article", category: "article", active: true },
            { id: 2, name: "Doc", category: "infographic" },
        ]),
    );
    await animationFrame();
    expect.verifySteps(["set_completed", "button 1 true"]);

    await click(
        ".o_wslides_sidebar_done_button[data-id='2'] .o_wslides_button_complete",
    );
    await animationFrame();

    expect.verifySteps(["set_completed", "button 2 true"]);
    const player = getInteraction(core, FullscreenPlayer);
    expect(player.slides.find((slide) => slide.id === 2).completed).toBe(true);
});

test("a burst of near-the-end video events marks the slide completed once", async () => {
    stubCompletionButton();
    onRpc("/slides/slide/get_html_content", () => ({ html_content: "<p>A</p>" }));
    const setCompleted = new Deferred();
    onRpc("/slides/slide/set_completed", async (request) => {
        const { params } = JSON.parse(
            new TextDecoder("utf-8").decode(await request.arrayBuffer()),
        );
        expect.step(`set_completed ${params.slide_id}`);
        return params.slide_id === "2" ? setCompleted : { channel_completion: 10 };
    });
    await startInteractions(
        fullscreenPage([
            { id: 1, name: "Article", category: "article", active: true },
            { id: 2, name: "Image", category: "infographic" },
        ]),
    );
    await animationFrame();
    expect.verifySteps(["set_completed 1", "button 1 true"]);

    const contentEl = queryOne(".o_wslides_fs_content");
    for (let i = 0; i < 3; i++) {
        contentEl.dispatchEvent(
            new CustomEvent("slide_mark_completed", {
                bubbles: true,
                detail: { id: 2 },
            }),
        );
    }
    await animationFrame();
    setCompleted.resolve({ channel_completion: 50 });
    await animationFrame();

    expect.verifySteps(["set_completed 2", "button 2 true"]);
});
