import { describe, expect, test } from "@odoo/hoot";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";

import { switchToEditMode } from "../../helpers.js";

describe.current.tags("interaction_dev");
setupInteractionWhiteList("website.image_gallery_edit");

test("an empty image gallery shows the add images alert in edit mode", async () => {
    const { core } = await startInteractions(
        `<section class="s_image_gallery"><div class="container"></div></section>`,
        { waitForStart: true, editMode: true },
    );
    await switchToEditMode(core);
    expect(".o_empty_gallery_alert").toHaveCount(1);
});

test("an image gallery whose image was replaced by an icon is not empty", async () => {
    const { core } = await startInteractions(
        `<section class="s_image_gallery"><div class="container">
            <span class="fa-solid fa-star object-fit-cover"></span>
        </div></section>`,
        { waitForStart: true, editMode: true },
    );
    await switchToEditMode(core);
    expect(".o_empty_gallery_alert").toHaveCount(0);
});
