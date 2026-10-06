/** @odoo-module native */
import {
    getEmbeddedProps,
    StateChangeManager,
    useEmbeddedState,
} from "@html_editor/others/embedded_component_utils";
import { getVideoUrl } from "@html_editor/utils/url";
import {
    Component,
    onMounted,
    onWillDestroy,
    onWillUnmount,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { Dropdown, DropdownItem, useDropdownState } from "@web/components/dropdown";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener } from "@web/core/utils/hooks";

import { ReadonlyEmbeddedVideoComponent } from "../../core/video/readonly_video.js";

export class EmbeddedVideoComponent extends ReadonlyEmbeddedVideoComponent {
    static template = "html_editor.EmbeddedVideo";
    static props = {
        platform: t.string(),
        videoId: t.string(),
        params: t.object().optional(),
        host: t.instanceOf(HTMLElement),
        createOverlay: t.function().optional(),
        focusEditable: t.function().optional(),
        addStep: t.function().optional(),
        openVideoSelectorDialog: t.function().optional(),
    };

    setup() {
        super.setup();
        this.videoBlock = this.props.host;
        this.state = useEmbeddedState(this.videoBlock);
        this.dropdown = useDropdownState();

        this.videoSettingsOverlay = this.props.createOverlay(VideoSettings, {
            positionOptions: {
                position: "right-start",
            },
            className: "video-overlay",
            closeOnPointerdown: false,
        });
        this.iframeRef = elementRef();

        useMountedListener(this.videoBlock, "pointerenter", () => {
            this.videoSettingsOverlay.open({
                target: this.videoBlock,
                props: {
                    videoBlock: this.videoBlock,
                    overlay: this.videoSettingsOverlay,
                    replaceVideo: () => {
                        this.props.openVideoSelectorDialog((media) => {
                            this.replaceVideo(media);
                        }, this.iframeRef.el);
                    },
                    removeVideo: () => {
                        this.videoBlock.remove();
                        this.props.addStep();
                    },
                    focusEditable: this.props.focusEditable,
                    dropdown: this.dropdown,
                },
            });
        });

        useListener(this.videoBlock, "pointerleave", (e) => {
            if (this.dropdown.isOpen || e.relatedTarget?.closest(".video-overlay")) {
                return;
            }
            this.videoSettingsOverlay.close();
        });

        onWillDestroy(() => {
            this.videoSettingsOverlay?.close();
        });
    }

    get url() {
        return getVideoUrl(
            this.state.platform,
            this.state.videoId,
            this.state.params,
        ).toString();
    }

    /**
     * @param {Object} media
     */
    replaceVideo(media) {
        this.state.videoId = media.videoId;
        this.state.platform = media.platform;
        this.state.params = media.params;
        this.props.focusEditable();
    }
}

export const videoEmbedding = {
    name: "video",
    Component: EmbeddedVideoComponent,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
    getStateChangeManager: (config) => new StateChangeManager(config),
};

export class VideoSettings extends Component {
    static template = "html_editor.VideoSettings";
    static components = { Dropdown, DropdownItem };
    static props = {
        videoBlock: t.instanceOf(HTMLElement),
        overlay: t.object(),
        replaceVideo: t.function(),
        removeVideo: t.function(),
        focusEditable: t.function(),
        dropdown: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.menuRef = elementRef();

        onMounted(() => {
            this.menuRef.el.addEventListener("pointerleave", () => {
                if (!this.props.dropdown.isOpen) {
                    this.props.overlay.close();
                }
            });
        });

        useListener(document, "pointerdown", (ev) => {
            if (this.props.dropdown.isOpen) {
                return;
            }
            this.props.overlay.close();
        });

        onWillUnmount(() => {
            if (!this.props.videoBlock.isConnected) {
                this.props.focusEditable();
            }
        });
    }
}
