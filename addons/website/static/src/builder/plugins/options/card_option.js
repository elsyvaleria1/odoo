/** @odoo-module native */
import { BaseOptionComponent, useGetItemValue } from "@html_builder/core/utils";
import { BorderConfigurator } from "@html_builder/plugins/border_configurator_option";
import { ShadowOption } from "@html_builder/plugins/shadow_option";
import { t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { BaseWebsiteBackgroundOption } from "@website/builder/plugins/options/background_option";

import { CardImageOption } from "./card_image_option.js";
import { CARD_DISABLE_WIDTH_APPLY_TO, CARD_PARENT_HANDLERS } from "./utils.js";

const log = makeLogger("website.builder.option.card_option");

export class BaseCardOption extends BaseOptionComponent {
    static template = "website.CardOption";
    static components = {
        CardImageOption,
        WebsiteBackgroundOption: BaseWebsiteBackgroundOption,
        BorderConfigurator,
        ShadowOption,
    };
    static props = { disableWidth: t.boolean().optional(false) };
    setup() {
        super.setup();
        useLifecycleLog(log);
        this.getItemValue = useGetItemValue();
    }
}

export class CardOption extends BaseCardOption {
    static selector = ".s_card";
    static exclude = `div:is(${CARD_PARENT_HANDLERS}) > .s_card`;
}

export class CardWithoutWidthOption extends BaseCardOption {
    static selector = CARD_PARENT_HANDLERS;
    static applyTo = CARD_DISABLE_WIDTH_APPLY_TO;
    static props = {
        ...BaseCardOption.props,
        disableWidth: BaseCardOption.props.disableWidth.optional(true),
    };
}
