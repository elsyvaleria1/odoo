/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { getVideoUrl } from "@html_editor/utils/url";
import { Component, t, useProps } from "@odoo/owl";

export class ReadonlyEmbeddedVideoComponent extends Component {
    static template = "html_editor.EmbeddedVideo";
    static props = {
        platform: t.string(),
        videoId: t.string(),
        params: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    get url() {
        return getVideoUrl(
            this.props.platform,
            this.props.videoId,
            this.props.params,
        ).toString();
    }
}

export const readonlyVideoEmbedding = {
    name: "video",
    Component: ReadonlyEmbeddedVideoComponent,
    getProps: (host) => ({ ...getEmbeddedProps(host) }),
};
