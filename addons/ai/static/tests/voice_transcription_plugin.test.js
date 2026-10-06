import { aiVoiceTranscriptionEmbeddedComponent } from "@ai/editor/embedded_components/core/voice_transcription";
import { TranscriptionPlugin } from "@ai/editor/embedded_components/plugins/voice_transcription_plugin";
import {
    setupMultiEditor,
    validateSameHistory,
} from "@html_editor/../tests/_helpers/collaboration";
import { cleanHints } from "@html_editor/../tests/_helpers/dispatch";
import { setupEditor } from "@html_editor/../tests/_helpers/editor";
import { addStep, tripleClick } from "@html_editor/../tests/_helpers/user_actions";
import { EmbeddedComponentPlugin } from "@html_editor/others/embedded_component_plugin";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { parseHTML } from "@html_editor/utils/html";
import { click, contains } from "@mail/../tests/mail_test_helpers";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { animationFrame, queryOne } from "@odoo/hoot-dom";
import { Dictation } from "@speech/live_capture/dictation";
import {
    defineModels,
    fields,
    makeMockServer,
    models,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { user } from "@web/core/user";
import { renderToString } from "@web/core/utils/render";

import { defineAIModels } from "./ai_test_helpers.js";

class Dummy extends models.Model {
    _name = "dummy";

    name = fields.Char();
    message_ids = fields.One2many({
        relation: "mail.message",
        string: "Messages",
    });

    _records = [
        { id: 1, name: "Bob" },
        { id: 2, name: "Patrick" },
        { id: 3, name: "Sheldon" },
    ];
}

defineModels([Dummy]);
defineAIModels();

let dictation;

beforeEach(() => {
    onRpc("ai.composer", "web_search_read", () => ({
        records: [{}],
    }));

    patchWithCleanup(Dictation.prototype, {
        async start() {
            this.id = 1;
            dictation = this;
        },
        async stop() {
            this.id = null;
        },
    });
});

function getCurrentDate() {
    const today = new Date();
    const timeString = today.toLocaleTimeString([user.lang], {
        hour: "2-digit",
        minute: "2-digit",
    });
    return `${today.toLocaleDateString()} - ${timeString}`;
}

const testAiVoiceTranscriptionEmbeddedComponent = {
    ...aiVoiceTranscriptionEmbeddedComponent,
    Component: class AudioTranscriber
        extends aiVoiceTranscriptionEmbeddedComponent.Component
    {
        static props = null;
    },
};

const config = {
    Plugins: [...MAIN_PLUGINS, EmbeddedComponentPlugin, TranscriptionPlugin],
    resources: {
        embedded_components: [testAiVoiceTranscriptionEmbeddedComponent],
    },
    getRecordInfo: () => ({
        resModel: "dummy",
        resId: "1",
    }),
    collaboration: {
        peerId: 1,
    },
};

describe("Component behaviour", () => {
    test.tags("desktop");
    test("transcript component tabs have proper hints", async () => {
        const transcriptBlock = renderToString("ai.VoiceTranscriptionBlueprint");
        await setupEditor(`<p>[]</p>${transcriptBlock}`, {
            config,
        });

        expect("[data-embedded='voice-transcription']").toHaveCount(1);
        expect("button:contains(Notes)").toHaveClass("active");
        expect("[data-embedded-editable='notesContent'] .o-we-hint").toHaveAttribute(
            "o-we-hint-text",
            "Add notes about your upcoming meeting",
        );
        await click("button:contains(Transcript)");
        await animationFrame();
        expect("button:contains(Transcript)").toHaveClass("active");
        expect(
            "[data-embedded-editable='transcriptContent'] .o-we-hint",
        ).toHaveAttribute(
            "o-we-hint-text",
            "Start recording to get a real-time transcript of the conversation",
        );
        await tripleClick(
            queryOne("[data-embedded-editable='transcriptContent'] .o-we-hint>br"),
        );
        await animationFrame();
        expect(
            "[data-embedded-editable='transcriptContent'] .o-we-hint",
        ).toHaveAttribute("o-we-hint-text", 'Type "/" for commands');
    });

    test("transcription items are properly rendered", async () => {
        const transcriptBlock = renderToString("ai.VoiceTranscriptionBlueprint");
        await setupEditor(`<p>[]</p>${transcriptBlock}`, {
            config,
        });

        expect("[data-embedded='voice-transcription']").toHaveCount(1);
        await click("button:contains(Start Recording)");
        await animationFrame();
        expect("button:contains(Transcript)").toHaveClass("active");
        expect("[data-embedded-editable='transcriptContent'] p>b").toHaveText(
            getCurrentDate(),
        );

        expect(".o-ai-transcription-listening").toHaveText("AI is listening...");

        dictation.onChunkSent(0);
        await animationFrame();
        expect("#current-transcript-0").toHaveText("…");
        expect(".o-ai-transcription-listening").toHaveText("AI is listening...");
        dictation.onChunkSent(1);
        dictation.onChunkSent(2);
        dictation.onChunkText(2, "and this arrived first");
        dictation.onChunkText(1, "");
        dictation.onChunkText(0, "This is a test of transcription");
        await click("button:contains(Stop Recording)");
        await animationFrame();
        expect("#current-transcript-0").toHaveCount(0);
        expect("#current-transcript-1").toHaveCount(0);
        expect(".o-ai-transcription-listening").toHaveCount(0);
        expect(
            "[data-embedded-editable='transcriptContent'] p:nth-last-child(2)",
        ).toHaveText("This is a test of transcription");
        expect("[data-embedded-editable='transcriptContent'] p:last-child").toHaveText(
            "and this arrived first",
        );
    });

    test("should only summarize when there is content in the transcription tab", async () => {
        const transcriptBlock = renderToString("ai.VoiceTranscriptionBlueprint");
        await setupEditor(`<p>[]</p>${transcriptBlock}`, {
            config,
        });

        expect("[data-embedded='voice-transcription']").toHaveCount(1);
        expect("[data-embedded-editable='summaryContent'] section").toHaveCount(0);
        expect("button:contains(Summary)").toHaveCount(0);

        await click("button:contains(Start Recording)");
        await click("button:contains(Stop Recording)");
        expect("[data-embedded-editable='summaryContent'] section").toHaveCount(0);

        await click("button:contains(Start Recording)");

        dictation.onChunkSent(1);
        dictation.onChunkText(1, "This is a test of transcription");

        await click("button:contains(Stop Recording)");
        await contains("button.active:contains(Summary)");
        await contains("[data-embedded-editable='summaryContent'] section", {
            textContent: "This is a response",
        });
    });

    test("share composer should have summary content", async () => {
        const transcriptBlock = renderToString("ai.VoiceTranscriptionBlueprint");
        const server = await makeMockServer();
        server.env["wizard.mail.message.send"]._views.form = `
            <form>
                <field name="body" type="html" widget="html_composer_message"/>
            </form>
        `;

        await setupEditor(`<p>[]</p>${transcriptBlock}`, {
            config,
        });

        expect("[data-embedded='voice-transcription']").toHaveCount(1);

        await click("button:contains(Start Recording)");

        dictation.onChunkSent(1);
        dictation.onChunkText(1, "This is a test of transcription");

        await click("button:contains(Stop Recording)");
        await click(
            "[data-embedded='voice-transcription'] button:contains(Share by email)",
        );
        await animationFrame();
        expect("div[name='body'] section").toHaveText("This is a response");
    });

    test("summary has proper prompt actions", async () => {
        onRpc("ai.composer", "web_search_read", () => ({
            records: [
                {
                    ai_agent: 1,
                    default_prompt: "This is a default prompt",
                    available_prompts: [
                        {
                            name: "Summarize this prospect call",
                        },
                        {
                            name: "Write an email recap",
                        },
                    ],
                },
            ],
        }));

        const transcriptBlock = renderToString("ai.VoiceTranscriptionBlueprint");
        const server = await makeMockServer();
        server.env["wizard.mail.message.send"]._views.form = `
        <form>
            <field name="body" type="html" widget="html_composer_message"/>
        </form>
        `;

        await setupEditor(`<p>[]</p>${transcriptBlock}`, {
            config,
        });

        expect("[data-embedded='voice-transcription']").toHaveCount(1);

        await click("button:contains(Start Recording)");

        dictation.onChunkSent(1);
        dictation.onChunkText(1, "This is a test of transcription");

        await click("button:contains(Stop Recording)");
        await animationFrame();
        expect(
            "[data-embedded='voice-transcription'] button:contains(Summarize this prospect call)",
        ).toHaveCount(1);
        expect(
            "[data-embedded='voice-transcription'] button:contains(Write an email recap)",
        ).toHaveCount(1);
    });
});

describe("Collaboration on transcription component", () => {
    test("recording and summarization are synchronized between peers", async () => {
        const peerInfos = await setupMultiEditor({
            peerIds: ["c1", "c2"],
            contentBefore: "<p>[c1}{c1][c2}{c2]<br></p>",
            ...config,
        });

        Object.values(peerInfos).forEach((peer) => {
            peer.editor.config.getRecordInfo = config.getRecordInfo;
        });

        const editor1 = peerInfos.c1.editor;
        const editor2 = peerInfos.c2.editor;

        editor1.shared.dom.insert(
            parseHTML(
                editor1.document,
                renderToString("ai.VoiceTranscriptionBlueprint"),
            ),
        );
        addStep(editor1);
        peerInfos.c2.collaborationPlugin.onExternalHistorySteps(
            peerInfos.c1.historyPlugin.steps,
        );
        validateSameHistory(peerInfos);
        cleanHints(editor2);
        expect(
            editor2.editable.querySelector("[data-embedded='voice-transcription']"),
        ).toHaveCount(1);
        await animationFrame();
        await click(editor1.editable.querySelector("summary>div button:last-child"));
        addStep(editor1);
        peerInfos.c2.collaborationPlugin.onExternalHistorySteps(
            peerInfos.c1.historyPlugin.steps,
        );
        await animationFrame();
        expect(
            editor2.editable.querySelector("summary>div button:last-child"),
        ).toHaveText("Stop Recording");
        expect(
            editor2.editable.querySelector(
                "[data-embedded-editable='transcriptContent'] p>b",
            ),
        ).toHaveText(getCurrentDate());

        dictation.onChunkSent(1);
        dictation.onChunkText(1, "This is a test of transcription");

        await animationFrame();

        await click(editor1.editable.querySelector("summary>div button:last-child"));
        addStep(editor1);
        await animationFrame();
        addStep(editor1);
        peerInfos.c2.collaborationPlugin.onExternalHistorySteps(
            peerInfos.c1.historyPlugin.steps,
        );

        await click(editor2.editable.querySelector("summary>nav button:first-child"));
        await animationFrame();

        expect(
            editor2.editable.querySelector(
                "[data-embedded-editable='summaryContent'] section",
            ),
        ).toHaveText("This is a response");
    });
});
