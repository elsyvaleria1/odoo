// @ts-check
/** @odoo-module native */

/** @type {(() => void)[]} */
let reads = [];
/** @type {(() => void)[]} */
let writes = [];
let scheduled = false;
let flushing = false;

function flush() {
    scheduled = false;
    flushing = true;
    /** @type {unknown[]} */
    const errors = [];
    try {
        while (reads.length || writes.length) {
            const batch = reads;
            reads = [];
            for (const fn of batch) {
                run(fn, errors);
            }
            const pending = writes;
            writes = [];
            for (const fn of pending) {
                run(fn, errors);
            }
        }
    } finally {
        flushing = false;
    }
    if (errors.length) {
        throw errors.length === 1 ? errors[0] : new AggregateError(errors);
    }
}

/**
 * @param {() => void} fn
 * @param {unknown[]} errors
 */
function run(fn, errors) {
    try {
        fn();
    } catch (error) {
        errors.push(error);
    }
}

function schedule() {
    if (!scheduled && !flushing) {
        scheduled = true;
        queueMicrotask(flush);
    }
}

/** @param {() => void} fn */
export function measure(fn) {
    reads.push(fn);
    schedule();
}

/** @param {() => void} fn */
export function mutate(fn) {
    writes.push(fn);
    schedule();
}
