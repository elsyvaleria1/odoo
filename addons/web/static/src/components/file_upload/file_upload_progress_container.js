// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

export class FileUploadProgressContainer extends Component {
    static template = "web.FileUploadProgressContainer";
    static props = {
        Component: t.any(),
        shouldDisplay: t.function().optional(),
        fileUploads: t.object(),
    };
    props = useProps(this.constructor.props);
}
