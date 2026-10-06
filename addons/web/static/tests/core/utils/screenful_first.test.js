// @ts-check

import { destroy, expect, test } from "@odoo/hoot";
import { queryAll, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    Component,
    onMounted,
    onPatched,
    onWillDestroy,
    proxy,
    useProps,
    xml,
} from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { useScreenfulFirst } from "@web/core/utils/screenful_first";

/**
 * @param {number} from
 * @param {number} count
 */
const items = (from, count) =>
    Array.from({ length: count }, (_, index) => ({ id: from + index }));

/**
 * @param {{ lists: any[], screenful: number, whole?: boolean }} state
 */
function makeList(state) {
    /** @type {{ built: number[], destroyed: number[], commits: number[] }} */
    const log = { built: [], destroyed: [], commits: [] };

    class Item extends Component {
        static props = null;
        static template = xml`<li t-out="this.props.id"/>`;
        props = useProps(this.constructor.props);
        setup() {
            log.built.push(this.props.id);
            onWillDestroy(() => {
                log.destroyed.push(this.props.id);
            });
        }
    }

    class List extends Component {
        static props = null;
        static components = { Item };
        static template = xml`
            <div>
                <ul t-foreach="this.state.lists" t-as="list" t-key="list_index">
                    <t t-foreach="this.screenfulFirst.leading(list, list.items, this.state.whole)" t-as="item" t-key="item.id">
                        <Item id="item.id"/>
                    </t>
                </ul>
            </div>
        `;
        setup() {
            this.state = proxy(state);
            this.screenfulFirst = useScreenfulFirst({
                screenful: () => state.screenful,
                keyOf: (/** @type {{ id: number }} */ item) => item.id,
            });
            const commit = () => {
                log.commits.push(queryAll("li").length);
            };
            onMounted(commit);
            onPatched(commit);
        }
    }

    return { List, log };
}

async function untilBuilt() {
    for (let frame = 0; frame < 12; frame++) {
        await animationFrame();
    }
}

test("the first commit builds a screenful, each commit after it one more", async () => {
    const state = { lists: [{ items: items(1, 10) }], screenful: 4 };
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    expect(queryAllTexts("li")).toEqual(["1", "2", "3", "4"]);

    await untilBuilt();
    expect(log.commits).toEqual([4, 8, 10]);
    expect(log.built).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(log.destroyed).toEqual([]);
});

test("a collection a screen holds is built whole, and no commit follows", async () => {
    const state = { lists: [{ items: items(1, 4) }], screenful: 4 };
    const { List, log } = makeList(state);
    await mountWithCleanup(List);

    await untilBuilt();
    expect(log.commits).toEqual([4]);
});

test("every collection of a render starts with its own screenful and grows with the others", async () => {
    const state = {
        lists: [
            { items: items(1, 5) },
            { items: items(11, 3) },
            { items: items(21, 7) },
        ],
        screenful: 3,
    };
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    expect("ul:eq(0) li").toHaveCount(3);
    expect("ul:eq(1) li").toHaveCount(3);
    expect("ul:eq(2) li").toHaveCount(3);

    await untilBuilt();
    expect(log.commits).toEqual([9, 14, 15]);
});

test("a new set of items starts over at a screenful", async () => {
    const state = proxy({ lists: [{ items: items(1, 10) }], screenful: 4 });
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    await untilBuilt();
    expect("li").toHaveCount(10);

    log.commits.length = 0;
    state.lists[0].items = items(101, 10);
    await untilBuilt();
    expect(log.commits).toEqual([4, 8, 10]);
    expect(queryAllTexts("li").at(-1)).toBe("110");
    expect(log.destroyed).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
});

test("a new set keeps every item it shares with what was built", async () => {
    const state = proxy({ lists: [{ items: items(1, 10) }], screenful: 4 });
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    await untilBuilt();

    log.commits.length = 0;
    state.lists[0].items = [...items(1, 8), ...items(50, 4)];
    await untilBuilt();
    expect(log.commits).toEqual([8, 12]);
    expect(log.destroyed).toEqual([9, 10]);
    expect(log.built.slice(10)).toEqual([50, 51, 52, 53]);
});

test("once built whole, a collection edited in place is rendered whole in one commit", async () => {
    const state = proxy({ lists: [{ items: items(1, 6) }], screenful: 4 });
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    await untilBuilt();
    expect("li").toHaveCount(6);

    log.commits.length = 0;
    state.lists[0].items.unshift({ id: 0 });
    state.lists[0].items.push(...items(7, 5));
    await untilBuilt();
    expect(log.commits).toEqual([12]);
});

test("the same items handed over in a new array at each render keep growing", async () => {
    const state = proxy({ lists: [{ all: items(1, 10) }], screenful: 4 });
    Object.defineProperty(state.lists[0], "items", {
        get() {
            return [...this.all];
        },
    });
    const { List, log } = makeList(state);
    await mountWithCleanup(List);

    await untilBuilt();
    expect(log.commits).toEqual([4, 8, 10]);
    expect(log.destroyed).toEqual([]);
});

test("a collection asked for whole is built whole, and stays so", async () => {
    const state = proxy({
        lists: [{ items: items(1, 10) }],
        screenful: 4,
        whole: true,
    });
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    expect("li").toHaveCount(10);

    state.whole = false;
    state.lists[0].items.push({ id: 11 });
    await untilBuilt();
    expect(log.commits).toEqual([10, 11]);
    expect(log.destroyed).toEqual([]);
});

test("the size of a screenful is read again for each new set", async () => {
    const state = proxy({ lists: [{ items: items(1, 10) }], screenful: 2 });
    const { List, log } = makeList(state);
    await mountWithCleanup(List);
    await untilBuilt();
    expect(log.commits).toEqual([2, 4, 6, 8, 10]);

    log.commits.length = 0;
    state.screenful = 7;
    state.lists[0].items = items(101, 10);
    await untilBuilt();
    expect(log.commits).toEqual([7, 10]);
});

test("a component destroyed while it grows builds nothing more", async () => {
    const state = { lists: [{ items: items(1, 10) }], screenful: 4 };
    const { List, log } = makeList(state);
    const list = await mountWithCleanup(List);
    const built = [...log.built];
    expect(built.length).toBeLessThan(10);
    destroy(list);

    await untilBuilt();
    expect(log.built).toEqual(built);
});
