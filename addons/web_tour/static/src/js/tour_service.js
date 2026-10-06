/** @odoo-module native */
import { Component, markup, t, useProps, validateType, whenReady } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { loadBundle } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { translationIsReady } from "@web/core/translation";
import { redirect } from "@web/core/utils/urls";
import { session } from "@web/session";
import { createPointerState } from "@web_tour/js/tour_pointer/tour_pointer_state";
import {
    TOUR_RECORDER_ACTIVE_LOCAL_STORAGE_KEY,
    tourRecorderState,
} from "@web_tour/js/tour_recorder/tour_recorder_state";
import { tourState } from "@web_tour/js/tour_state";
import { callWithUnloadCheck } from "@web_tour/js/utils/tour_utils";

const AUTOMATIC_ENTRY = "@web_tour/js/tour_automatic/tour_automatic";

function loadAutomaticRuntime() {
    if (odoo.loader?.modules?.has(AUTOMATIC_ENTRY)) {
        return Promise.resolve();
    }
    return loadBundle("web_tour.automatic", { css: false });
}

class OnboardingItem extends Component {
    static components = { DropdownItem };
    static template = "web_tour.OnboardingItem";
    static props = { toursEnabled: t.boolean(), toggleItem: t.function() };
    props = useProps(this.constructor.props);
    setup() {}
}

/**
 * @param {any} issue
 * @returns {string}
 */
function describeIssue(issue) {
    if (issue.unknownKeys) {
        return issue.unknownKeys
            .map((/** @type {string} */ key) => `unknown key '${key}'`)
            .join(", ");
    }
    if (issue.subIssues?.length) {
        const article =
            issue.subIssues[0].message.match(/^value is not (an? )/)?.[1] || "";
        const types = issue.subIssues.map((/** @type {any} */ sub) =>
            sub.message.replace(/^value is not (an? )?/, ""),
        );
        return `'${issue.path}' is not ${article}${types.join(" or ")}`;
    }
    const message = issue.message.replace(/^value /, "");
    return issue.path ? `'${issue.path}' ${message}` : message;
}

/**
 * @param {any[]} issues
 * @returns {string}
 */
function describeIssues(issues) {
    return `Invalid object: ${issues.map(describeIssue).join(", ")}`;
}

const StepSchema = t.strictObject({
    id: t.string().optional(),
    content: t.or([t.string(), t.object()]).optional(),
    debugHelp: t.string().optional(),
    isActive: t.array(t.string()).optional(),
    run: t.or([t.string(), t.function(), t.boolean()]).optional(),
    timeout: t
        .customValidator(t.any(), function (value) {
            return value >= 0 && value <= 60000;
        })
        .optional(),
    tooltipPosition: t
        .customValidator(t.any(), function (value) {
            return ["top", "bottom", "left", "right"].includes(value);
        })
        .optional(),
    trigger: t.string(),
    expectUnloadPage: t.boolean().optional(),
    pause: t.boolean().optional(),
    break: t.boolean().optional(),
});

const TourSchema = t.strictObject({
    name: t.string().optional(),
    steps: t.function(),
    timeout: t
        .customValidator(t.any(), function (value) {
            return value >= 0 && value <= 60000;
        })
        .optional(),
    url: t.string().optional(),
    wait_for: t.or([t.function(), t.object()]).optional(),
});

registry.category("web_tour.tours").addValidation(TourSchema);
const debugMenuRegistry = registry.category("debug").category("default");

const TOUR_REGISTRATION_TIMEOUT = 30000;

export const tourService = {
    dependencies: ["orm", "effect", "overlay", "localization"],
    start: async (env, { orm, effect, overlay }) => {
        await whenReady();
        let toursEnabled = session?.tour_enabled;
        const tourRegistry = registry.category("web_tour.tours");
        const pointer = createPointerState();
        pointer.stop = () => {};

        debugMenuRegistry.add("onboardingItem", () => ({
            type: "component",
            Component: OnboardingItem,
            props: {
                toursEnabled: toursEnabled || false,
                toggleItem: async () => {
                    tourState.clear();
                    toursEnabled = await orm.call("res.users", "switch_tour_enabled", [
                        !toursEnabled,
                    ]);
                    browser.location.reload();
                },
            },
            sequence: 500,
            section: "testing",
        }));

        function getTourFromRegistry(tourName, tourConfig) {
            if (!tourRegistry.contains(tourName)) {
                return;
            }
            const tour = tourRegistry.get(tourName);
            return {
                ...tour,
                steps: tour.steps(tourConfig),
                name: tourName,
                wait_for: tour.wait_for || Promise.resolve(),
            };
        }

        async function getTourFromDB(tourName, tourConfig) {
            const tour = await orm.call("web_tour.tour", "get_tour_json_by_name", [
                tourName,
            ]);
            if (!tour) {
                throw new Error(`Tour '${tourName}' is not found in the database.`);
            }

            if (!tour.steps.length && tourRegistry.contains(tour.name)) {
                tour.steps = tourRegistry.get(tour.name).steps(tourConfig);
            }

            return tour;
        }

        function validateStep(step) {
            const issues = validateType(step, StepSchema);
            if (issues.length) {
                console.error(
                    `Error in schema for TourStep ${JSON.stringify(step, null, 4)}\n${describeIssues(
                        issues,
                    )}`,
                );
            }
        }

        async function startTour(tourName, options = {}) {
            pointer.stop();
            if (!tourRegistry.contains(tourName) && !options.fromDB) {
                return;
            }

            const tour = {
                name: tourName,
                url: options.fromDB ? options.url : tourRegistry.get(tourName).url,
            };
            if (!session.is_public && !toursEnabled && options.mode === "manual") {
                toursEnabled = await orm.call("res.users", "switch_tour_enabled", [
                    !toursEnabled,
                ]);
            }

            let tourConfig = {
                delayToCheckUndeterminisms: 0,
                stepDelay: 0,
                keepWatchBrowser: false,
                mode: "auto",
                showPointerDuration: 0,
                debug: false,
                redirect: true,
            };

            tourConfig = Object.assign(tourConfig, options);
            tourState.setCurrentConfig(tourConfig);
            tourState.setCurrentTour(tour.name);
            tourState.setCurrentIndex(0);

            const willUnload = callWithUnloadCheck(() => {
                if (
                    tour.url &&
                    tourConfig.startUrl !== tour.url &&
                    tourConfig.redirect
                ) {
                    redirect(tour.url);
                }
            });
            if (!willUnload) {
                await resumeTour();
            }
        }

        function whenTourIsRegistered(tourName, timeout = TOUR_REGISTRATION_TIMEOUT) {
            if (tourRegistry.contains(tourName)) {
                return Promise.resolve(true);
            }
            return new Promise((resolve) => {
                let timer;
                const onUpdate = (ev) => {
                    if (ev.detail.key !== tourName) {
                        return;
                    }
                    browser.clearTimeout(timer);
                    tourRegistry.removeEventListener("UPDATE", onUpdate);
                    resolve(true);
                };
                timer = browser.setTimeout(() => {
                    tourRegistry.removeEventListener("UPDATE", onUpdate);
                    resolve(false);
                }, timeout);
                tourRegistry.addEventListener("UPDATE", onUpdate);
            });
        }

        async function resumeTour() {
            const tourName = tourState.getCurrentTour();
            const tourConfig = tourState.getCurrentConfig();

            let tour;
            if (tourConfig.fromDB) {
                tour = await getTourFromDB(tourName, tourConfig);
            } else {
                tour = getTourFromRegistry(tourName, tourConfig);
                if (!tour) {
                    await whenTourIsRegistered(tourName);
                    tour = getTourFromRegistry(tourName, tourConfig);
                }
            }
            if (!tour) {
                if (tourConfig.mode !== "auto") {
                    return;
                }
                tourState.clear();
                browser.console.error(
                    `Tour "${tourName}" was resumed but is registered nowhere` +
                        ` (${tourConfig.fromDB ? "database" : "web_tour.tours registry"}).` +
                        " Its saved state has been dropped.",
                );
                return;
            }

            tour.steps.forEach((step) => validateStep(step));

            if (tourConfig.mode === "auto") {
                await loadAutomaticRuntime();
                const { TourAutomatic } =
                    await import("@web_tour/js/tour_automatic/tour_automatic");
                new TourAutomatic(tour).start();
            } else {
                await loadBundle("web_tour.interactive");
                const { TourPointer } =
                    await import("@web_tour/js/tour_pointer/tour_pointer");
                pointer.stop = overlay.add(
                    TourPointer,
                    {
                        pointerState: pointer.state,
                        bounce: !(
                            tourConfig.mode === "auto" && tourConfig.keepWatchBrowser
                        ),
                    },
                    {
                        sequence: 1100,
                    },
                );
                const { TourInteractive } =
                    await import("@web_tour/js/tour_interactive/tour_interactive");
                new TourInteractive(tour).start(env, pointer, async () => {
                    pointer.stop();
                    tourState.clear();
                    browser.console.log("tour succeeded");
                    let message =
                        tourConfig.rainbowManMessage || tour.rainbowManMessage;
                    if (message) {
                        // loaded here, not with the service: a tour's closing
                        // message is the only reader on the page
                        const { default: DOMPurify } = await import("dompurify");
                        message = DOMPurify.sanitize(message);
                        effect.add({
                            type: "rainbow_man",
                            message: markup(message),
                        });
                    }

                    const nextTour = await orm.call("web_tour.tour", "consume", [
                        tour.name,
                    ]);
                    if (nextTour) {
                        startTour(nextTour.name, {
                            mode: "manual",
                            redirect: false,
                            rainbowManMessage: nextTour.rainbowManMessage,
                        });
                    }
                });
            }
        }

        async function tourRecorder() {
            await loadBundle("web_tour.recorder");
            const { TourRecorder } =
                await import("@web_tour/js/tour_recorder/tour_recorder");
            const remove = overlay.add(
                TourRecorder,
                {
                    onClose: () => {
                        remove();
                        browser.localStorage.removeItem(
                            TOUR_RECORDER_ACTIVE_LOCAL_STORAGE_KEY,
                        );
                        tourRecorderState.clear();
                    },
                },
                { sequence: 99999 },
            );
        }

        async function startTourRecorder() {
            if (!browser.localStorage.getItem(TOUR_RECORDER_ACTIVE_LOCAL_STORAGE_KEY)) {
                await tourRecorder();
            }
            browser.localStorage.setItem(TOUR_RECORDER_ACTIVE_LOCAL_STORAGE_KEY, "1");
        }

        if (!window.frameElement) {
            const paramsTourName = new URLSearchParams(browser.location.search).get(
                "tour",
            );
            // `else if`, not a second `if`: a `?tour=` param already owns the
            // resume, and this block used to run it a SECOND time for the same
            // tour, concurrently. `startTour` only reaches an `await` before it
            // writes the tour state when tours are *disabled* for the user (the
            // `switch_tour_enabled` call above); with them already enabled its
            // body runs synchronously through `tourState.setCurrentTour(...)`
            // and into `resumeTour()`, which itself returns at its own first
            // `await`. So control came back here with `getCurrentTour()`
            // already set, and -- `toursEnabled` being true -- this block
            // called `resumeTour()` again in the same task, with nothing in
            // `resumeTour` guarding re-entrancy: two `TourInteractive`
            // instances and two `overlay.add(TourPointer, ...)` for one tour.
            // Chaining the branches also settles which tour wins when a
            // `?tour=` link is opened while a stale `current_tour` sits in
            // localStorage: the URL, whose state `startTour` overwrites anyway.
            if (paramsTourName) {
                startTour(paramsTourName, { mode: "manual", fromDB: true });
            } else if (tourState.getCurrentTour()) {
                if (tourState.getCurrentConfig().mode === "auto" || toursEnabled) {
                    resumeTour();
                } else {
                    tourState.clear();
                }
            } else if (session.current_tour) {
                startTour(session.current_tour.name, {
                    mode: "manual",
                    redirect: false,
                    rainbowManMessage: session.current_tour.rainbowManMessage,
                });
            }

            if (
                browser.localStorage.getItem(TOUR_RECORDER_ACTIVE_LOCAL_STORAGE_KEY) &&
                !session.is_public
            ) {
                await tourRecorder();
            }
        }

        odoo.startTour = startTour;
        odoo.isTourReady = (tourName) => {
            if (!tourRegistry.contains(tourName)) {
                return false;
            }
            const tour = tourRegistry.get(tourName);
            return Promise.all([
                translationIsReady,
                tour.wait_for || Promise.resolve(),
                loadAutomaticRuntime(),
            ]).then(() => true);
        };

        return {
            startTour,
            startTourRecorder,
        };
    },
};

registry.category("services").add("tour_service", tourService);
