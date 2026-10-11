import { describe, expect, getFixture, test } from "@odoo/hoot";
import { makeMockEnv, onRpc } from "@web/../tests/web_test_helpers";
import { parseQuizReply, QuizBehavior } from "@website_slides/interactions/quiz";

describe.current.tags("interaction_dev");

function quizBehavior() {
    const el = document.createElement("div");
    getFixture().append(el);
    const host = {
        addListener: () => () => {},
        registerCleanup: () => {},
        waitFor: (promise) => promise,
    };
    return new QuizBehavior(
        host,
        { el, slideData: { id: 4, isMember: true }, channelData: {} },
        { questions: [{ id: 1 }], quizAttemptsCount: 2 },
    );
}

test("parseQuizReply maps a quiz/get reply and refuses an error reply", () => {
    expect(parseQuizReply({ error: "slide_access" })).toBe(null);
    expect(parseQuizReply(undefined)).toBe(null);

    const parsed = parseQuizReply({
        slide_questions: [{ id: 1 }, { id: 2 }],
        quiz_attempts_count: 3,
        quiz_karma_gain: 5,
        session_answers: [7],
    });
    expect(parsed.quiz.questionsCount).toBe(2);
    expect(parsed.quiz.quizAttemptsCount).toBe(3);
    expect(parsed.quiz.quizKarmaGain).toBe(5);
    expect(parsed.quiz.quizKarmaWon).toBe(0);
    expect(parsed.quiz.slideResources).toEqual([]);
    expect(parsed.sessionAnswers).toEqual([7]);
    expect(parseQuizReply({}).sessionAnswers).toBe(null);
});

test("refetching a quiz the server refuses keeps the current quiz", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/get", () => ({ error: "slide_access" }));
    const quiz = quizBehavior();

    expect(await quiz._fetchQuiz()).toBe(false);
    expect(quiz.quiz.questionsCount).toBe(1);
    expect(quiz.quiz.quizAttemptsCount).toBe(2);
});

test("refetching a quiz replaces it with the server's reply", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/get", () => ({
        slide_questions: [{ id: 1 }, { id: 2 }, { id: 3 }],
        quiz_attempts_count: 0,
    }));
    const quiz = quizBehavior();

    expect(await quiz._fetchQuiz()).toBe(true);
    expect(quiz.quiz.questionsCount).toBe(3);
    expect(quiz.slide.sessionAnswers).toBe(null);
});

test("a quiz the server refuses to load is not rendered", async () => {
    await makeMockEnv();
    onRpc("/slides/slide/quiz/get", () => ({ error: "slide_wrong" }));
    const host = {
        waitFor: (promise) => promise,
        renderAt: () => {
            expect.step("rendered");
            return [document.createElement("div")];
        },
    };

    const quiz = await QuizBehavior.create(host, {
        targetEl: getFixture(),
        slideData: { id: 4 },
        channelData: {},
    });

    expect(quiz).toBe(null);
    expect.verifySteps([]);
});
