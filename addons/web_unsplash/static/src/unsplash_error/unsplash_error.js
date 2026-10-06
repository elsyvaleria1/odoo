/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

import { UnsplashCredentials } from "../unsplash_credentials/unsplash_credentials.js";

export class UnsplashError extends Component {
    static template = "web_unsplash.UnsplashError";
    static components = {
        UnsplashCredentials,
    };
    static props = {
        title: t.string(),
        subtitle: t.string(),
        showCredentials: t.boolean(),
        submitCredentials: t.function().optional(),
        hasCredentialsError: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);
}
