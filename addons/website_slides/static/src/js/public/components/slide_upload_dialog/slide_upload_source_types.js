/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";

export class SlideUploadSourceTypes extends Component {
    static props = {
        attributes: t.object({
            sourceTypeLabel: t.string().optional(),
            selectFileLabel: t.string().optional(),
            acceptedFiles: t.string().optional(),
            urlInputLabel: t.string(),
            urlInputName: t.string(),
        }),
        isLocalSource: t.boolean(),
        onClickSourceType: t.function(),
        onChangeFileInput: t.function(),
        onChangeUrl: t.function(),
    };
    static template = "website_slides.SlideUploadSourceTypes";
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ url: "" });
    }
}
