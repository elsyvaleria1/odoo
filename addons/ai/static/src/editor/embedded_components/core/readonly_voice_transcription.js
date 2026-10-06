/** @odoo-module native */
import {
    getEditableDescendants,
    getEmbeddedProps,
    useEditableDescendants,
} from "@html_editor/others/embedded_component_utils";
import { Component, onMounted, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { elementRefs } from "@web/core/utils/element_ref";

export class ReadonlyVoiceTranscription extends Component {
    static template = "ai.ReadonlyVoiceTranscription";
    static components = {};
    static props = { host: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.descendantRefs = elementRefs();
        this.descendants = useEditableDescendants(this.props.host, this.descendantRefs);
        this.supportedLanguages = [];
        this.state = proxy({
            isOpened: true,
            currentTab: "notes",
        });

        onWillStart(() => {
            if (this.props.hasSummary) {
                this.state.currentTab = "summary";
            }
        });

        onMounted(() => {
            const firstRecordingDate = this.props.host.querySelector(
                "#transcript-content b",
            );
            this.state.firstRecordingDate = firstRecordingDate?.textContent ?? "";
        });
    }

    setCurrentTab(tabName) {
        this.state["currentTab"] = tabName;
    }
}

export const aiReadonlyVoiceTranscriptionEmbeddedComponent = {
    name: "voice-transcription",
    Component: ReadonlyVoiceTranscription,
    getEditableDescendants,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
};
