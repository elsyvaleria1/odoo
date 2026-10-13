/** @odoo-module native */
import {
    getEditableDescendants,
    getEmbeddedProps,
    StateChangeManager,
    useEditableDescendants,
    useEmbeddedState,
} from "@html_editor/others/embedded_component_utils";
import { Component, onMounted, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dictation } from "@speech/live_capture/dictation";
import { RPCError } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { elementRefs } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";

export class VoiceTranscription extends Component {
    static template = "ai_speech.VoiceTranscription";
    static components = {};
    static props = {
        host: t.object(),
        firstRecordingDate: t.function(),
        getTabContent: t.function(),
        getTranscriptContent: t.function(),
        onTranscriptionStarted: t.function(),
        onTranscriptionUpdated: t.function(),
        onRecorderStopped: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.model = useViewModel();
        this.descendantRefs = elementRefs();
        this.descendants = useEditableDescendants(this.props.host, this.descendantRefs);
        this.embeddedState = useEmbeddedState(this.props.host);
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.orm = useService("orm");
        this.mailStore = useService("mail.store");

        this.supportedLanguages = [];

        this.state = proxy({
            isOpened: true,
            isRecording: false,
            currentTab: "notes",
            currentLanguage: user.lang.replace("-", "_"),
            status: "idle",
        });

        this.dictation = new Dictation({
            orm: this.orm,
            bus: useService("bus_service"),
            onChunkSent: (index) => {
                const placeholder = this.props.onTranscriptionUpdated(
                    "delta",
                    this.embeddedState.id,
                    index,
                    "…",
                );
                if (placeholder === null) {
                    this.dictation.stop();
                    return;
                }
                if (this.embeddedState.status === "recording") {
                    this.props.onTranscriptionUpdated(
                        "listening",
                        this.embeddedState.id,
                        null,
                        _t("AI is listening..."),
                    );
                }
            },
            onChunkText: (index, text) => {
                this.props.onTranscriptionUpdated(
                    "completed",
                    this.embeddedState.id,
                    index,
                    text,
                );
            },
            onError: (error) => this.notifyError(error),
        });

        onWillStart(async () => {
            const languages = await this.orm.call("res.lang", "get_installed", []);
            this.supportedLanguages = languages.map(([code]) => ({
                shortCode: code.split("_")[0],
                code,
            }));

            if (this.dictation.recording) {
                this.embeddedState.status = "recording";
            }

            this.composerPrompts = (
                await this.orm.webSearchRead(
                    "ai.composer",
                    [["interface_key", "=", "voice_transcription_component"]],
                    {
                        specification: {
                            ai_agent: {},
                            default_prompt: {},
                            available_prompts: {
                                fields: {
                                    name: {},
                                },
                            },
                        },
                    },
                )
            ).records[0];
            if (this.embeddedState.hasSummary) {
                this.state.currentTab = "summary";
            }
        });

        onMounted(() => {
            this.state.firstRecordingDate = this.props.firstRecordingDate(
                this.embeddedState.id,
            );
        });
    }

    setCurrentTab(tabName) {
        if (tabName === "summary") {
            const summaryContent = this.props.getTabContent(
                this.embeddedState.id,
                "summary",
            );

            if (summaryContent && summaryContent.innerText.trim() === "") {
                this.updateSummary();
            }
        }

        this.state["currentTab"] = tabName;
    }

    onLanguageChange(event) {
        this.state.currentLanguage = event.target.value;
    }

    async toggleRecording() {
        this.state.isRecording = !this.state.isRecording;
        if (this.embeddedState.status === "idle") {
            const transcriptPrompt = this.props.getTabContent(
                this.embeddedState.id,
                "notes",
            );
            try {
                this.embeddedState.status = "waiting";
                const { resModel, resId } = this.model?.config ?? {};
                await this.dictation.start({
                    resModel,
                    resId,
                    language: this.state.currentLanguage.split("_")[0],
                    prompt: transcriptPrompt?.innerText.trim(),
                });
                this.embeddedState.status = "recording";
                this.props.onTranscriptionStarted(
                    this.embeddedState.id,
                    this.state.currentLanguage.replace("_", "-"),
                );
                this.props.onTranscriptionUpdated(
                    "listening",
                    this.embeddedState.id,
                    null,
                    _t("AI is listening..."),
                );
                this.setCurrentTab("transcript");
            } catch (error) {
                this.embeddedState.status = "idle";
                this.state.isRecording = false;
                this.notifyError(error);
            }
        } else if (this.embeddedState.status === "recording") {
            this.embeddedState.status = "transcribing";
            this.props.onTranscriptionUpdated("stopped", this.embeddedState.id);
            await this.dictation.stop();
            this.updateSummary();
        }
    }

    notifyError(error) {
        if (error instanceof DOMException && error.name === "NotAllowedError") {
            this.notificationService.add(
                _t(
                    "You must allow the access to your microphone to start the recording. Try refreshing the page and start again.",
                ),
                {
                    title: _t("Access error"),
                    type: "danger",
                },
            );
        } else if (
            error instanceof RPCError &&
            error.data.name === "odoo.exceptions.UserError"
        ) {
            this.notificationService.add(error.data.message, {
                title: _t("User error"),
                type: "danger",
            });
        } else {
            this.notificationService.add(_t("Unable to record."), {
                title: _t("An error occured"),
                type: "danger",
            });
        }
    }

    async updateSummary(prompt = "") {
        this.embeddedState.status = "summarizing";
        const summary = await this.getSummary(prompt);
        if (summary) {
            this.props.onRecorderStopped(this.embeddedState.id, summary);
            this.embeddedState.hasSummary = true;
            this.setCurrentTab("summary");
        }
        this.embeddedState.status = "idle";
    }

    async getSummary(prompt = "") {
        const textToSummarize = this.props.getTranscriptContent(this.embeddedState.id);
        if (
            !this.composerPrompts ||
            !textToSummarize ||
            textToSummarize.trim() === ""
        ) {
            return null;
        }

        const summaryLanguage = `You MUST provide the summary in the following language: ${this.state.currentLanguage}`;
        const summary = await this.orm.call(
            "ai.agent",
            "get_direct_response",
            [this.composerPrompts.ai_agent],
            {
                prompt: `${this.composerPrompts.default_prompt}\n${prompt}\n${summaryLanguage}\n${textToSummarize}`,
                enable_html_response: true,
            },
        );
        return String(summary);
    }

    async openComposer() {
        const model = this.model;
        await model?.root.save();
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Share transcript summary"),
                view_mode: "form",
                res_model: "wizard.mail.message.send",
                views: [[false, "form"]],
                target: "new",
                view_id: false,
                context: {
                    default_model: model?.config.resModel,
                    default_res_ids: model?.config.resIds,
                    default_subject: _t("Share transcript summary"),
                    default_body:
                        this.props.getTabContent(this.embeddedState.id, "summary")
                            .innerHTML ?? "",
                    clicked_on_full_composer: true,
                },
            },
            {
                onClose: () => {
                    const thread = this.mailStore.Thread.get({
                        model: model?.config.resModel,
                        id: model?.config.resId,
                    });
                    thread?.fetchNewMessages();
                },
            },
        );
    }
}

export const aiVoiceTranscriptionEmbeddedComponent = {
    name: "voice-transcription",
    Component: VoiceTranscription,
    getEditableDescendants: getEditableDescendants,
    getProps: (host) => ({ host }),
    getStateChangeManager: (config) =>
        new StateChangeManager(
            Object.assign(config, {
                getEmbeddedState: (host) => {
                    const props = getEmbeddedProps(host);
                    if (host.dataset.embeddedState) {
                        const currentState = JSON.parse(host.dataset.embeddedState);
                        props.status = currentState.next?.status;
                    }
                    props.status ??= "idle";
                    return props;
                },
                stateToEmbeddedProps: (host, state) => {
                    const props = getEmbeddedProps(host);
                    props.id = state.id;
                    props.hasSummary = state.hasSummary;
                    return props;
                },
            }),
        ),
};
