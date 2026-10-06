// ../owl-runtime/src/version.ts
var version = "3.0.0-alpha.49";

// ../owl-core/dist/owl-core.es.js
var OwlError = class extends Error {
  cause;
};
var STATUS = {
  NEW: 0,
  MOUNTED: 1,
  // is ready, and in DOM. It has a valid el
  DESTROYED: 2
};
function batched(callback) {
  let scheduled = false;
  return function batchedCall(...args) {
    if (!scheduled) {
      scheduled = true;
      Promise.resolve().then(() => {
        scheduled = false;
        callback(...args);
      });
    }
  };
}
var DEBUG_CHANNELS = [
  "reactivity",
  "effect",
  "computed",
  "scope",
  "plugin",
  "scheduler",
  "fiber",
  "lifecycle",
  "error",
  "template",
  "event"
];
var debug = Object.seal({
  reactivity: false,
  effect: false,
  computed: false,
  scope: false,
  plugin: false,
  scheduler: false,
  fiber: false,
  lifecycle: false,
  error: false,
  template: false,
  event: false
});
var consoleSink = (channel, message, details) => {
  console.debug(`[owl:${channel}] ${message}`, ...details);
};
var sink = consoleSink;
function setDebug(channels) {
  const wanted = typeof channels === "boolean" ? channels ? DEBUG_CHANNELS : [] : typeof channels === "string" ? channels.split(",").map((channel) => channel.trim()).filter(Boolean) : channels;
  for (const channel of wanted) {
    if (!DEBUG_CHANNELS.includes(channel)) {
      throw new Error(
        `Unknown debug channel "${channel}" (channels: ${DEBUG_CHANNELS.join(", ")})`
      );
    }
  }
  for (const channel of DEBUG_CHANNELS) {
    debug[channel] = wanted.includes(channel);
  }
}
function setDebugSink(newSink) {
  sink = newSink || consoleSink;
}
function debugNow() {
  return typeof performance === "undefined" ? Date.now() : performance.now();
}
function debugLog(channel, message, ...details) {
  sink(channel, message, details);
}
function neverEqual() {
  return false;
}
function toEqualsFn(equals) {
  if (equals === false) {
    return neverEqual;
  }
  if (!equals) {
    return Object.is;
  }
  return (a, b) => {
    const previousComputation = currentComputation;
    currentComputation = void 0;
    try {
      return equals(a, b);
    } finally {
      currentComputation = previousComputation;
    }
  };
}
var ComputationState = /* @__PURE__ */ ((ComputationState2) => {
  ComputationState2[ComputationState2["EXECUTED"] = 0] = "EXECUTED";
  ComputationState2[ComputationState2["STALE"] = 1] = "STALE";
  ComputationState2[ComputationState2["PENDING"] = 2] = "PENDING";
  return ComputationState2;
})(ComputationState || {});
var Link = class {
  dep;
  sub;
  // the run of `sub` that last read `dep` (see ComputationAtom.version), or
  // DEAD once the edge is removed
  version;
  prevDep;
  nextDep;
  prevSub;
  nextSub;
  // what dep.activeLink pointed at before this run pointed it here
  rollback;
  // dep's value when sub read it: a signal written back to that value since
  // (a write and its revert in one batch) has not changed for sub
  seen;
  constructor(dep, sub, version2, prevDep, nextDep, prevSub, rollback) {
    this.dep = dep;
    this.sub = sub;
    this.version = version2;
    this.prevDep = prevDep;
    this.nextDep = nextDep;
    this.prevSub = prevSub;
    this.nextSub = void 0;
    this.rollback = rollback;
    this.seen = dep.value;
  }
};
var DEAD = -1;
function createAtom(value, type) {
  return { type, value, subs: void 0, subsTail: void 0, activeLink: void 0 };
}
function isLive(link) {
  return link.version === link.sub.version;
}
function hasObservers(atom) {
  for (let link = atom.subs; link !== void 0; link = link.nextSub) {
    if (isLive(link)) {
      return true;
    }
  }
  return false;
}
var atomSymbol = /* @__PURE__ */ Symbol("Atom");
var computationScopes = /* @__PURE__ */ new WeakMap();
var observers = [];
var immediateObservers = [];
var currentComputation;
var pendingDisposals = /* @__PURE__ */ new Set();
var invalidations = 0;
function createComputation(compute, isDerived, state = 1, immediate = false, name = "") {
  return {
    value: void 0,
    subs: void 0,
    subsTail: void 0,
    activeLink: void 0,
    compute,
    isDerived,
    deps: void 0,
    depsTail: void 0,
    version: 0,
    prepared: false,
    tracksElsewhere: false,
    observed: null,
    state,
    immediate,
    notifiesWithoutRecompute: false,
    owned: null,
    owner: null,
    isEffect: false,
    running: false,
    name
  };
}
var currentObserver;
function isObserving() {
  return currentComputation !== void 0 || currentObserver !== void 0;
}
function onReadAtom(atom) {
  const sub = currentComputation;
  if (sub !== void 0) {
    const tail = sub.depsTail;
    if (tail === void 0 || tail.dep !== atom) {
      track(atom, sub, tail);
    }
  }
  const observer = currentObserver;
  if (observer !== void 0 && observer !== sub) {
    if (observer.running) {
      const tail = observer.depsTail;
      if (tail === void 0 || tail.dep !== atom) {
        track(atom, observer, tail);
      }
      return;
    }
    const observed = observer.observed ??= observedSources(observer);
    if (!observed.has(atom)) {
      observed.add(atom);
      const tail = observer.depsTail;
      const link = new Link(
        atom,
        observer,
        observer.version,
        tail,
        void 0,
        atom.subsTail,
        void 0
      );
      if (tail !== void 0) {
        tail.nextDep = link;
      } else {
        observer.deps = link;
      }
      observer.depsTail = link;
      appendSub(atom, link);
    }
  }
}
function track(dep, sub, tail) {
  const version2 = sub.version;
  let active = dep.activeLink;
  if (active !== void 0 && active.sub === sub && active.version !== DEAD) {
    if (active.version !== version2) {
      reuse(active, sub, tail, version2);
    }
    return;
  }
  const next = tail !== void 0 ? tail.nextDep : sub.deps;
  if (next !== void 0) {
    if (next.dep === dep) {
      next.version = version2;
      next.seen = dep.value;
      next.rollback = active;
      dep.activeLink = next;
      sub.depsTail = next;
      return;
    }
    if (!sub.prepared) {
      sub.prepared = true;
      for (let link2 = next; link2 !== void 0; link2 = link2.nextDep) {
        const source = link2.dep;
        if (source.activeLink !== link2) {
          link2.rollback = source.activeLink;
          source.activeLink = link2;
        }
      }
      active = dep.activeLink;
      if (active !== void 0 && active.sub === sub && active.version !== DEAD) {
        reuse(active, sub, tail, version2);
        return;
      }
    }
  }
  const link = new Link(dep, sub, version2, tail, next, dep.subsTail, active);
  if (next !== void 0) {
    next.prevDep = link;
  }
  if (tail !== void 0) {
    tail.nextDep = link;
  } else {
    sub.deps = link;
  }
  sub.depsTail = link;
  dep.activeLink = link;
  appendSub(dep, link);
}
function reuse(link, sub, tail, version2) {
  link.version = version2;
  link.seen = link.dep.value;
  const next = tail !== void 0 ? tail.nextDep : sub.deps;
  if (link !== next) {
    const prevDep = link.prevDep;
    const nextDep = link.nextDep;
    prevDep.nextDep = nextDep;
    if (nextDep !== void 0) {
      nextDep.prevDep = prevDep;
    }
    link.prevDep = tail;
    link.nextDep = next;
    next.prevDep = link;
    if (tail !== void 0) {
      tail.nextDep = link;
    } else {
      sub.deps = link;
    }
  }
  sub.depsTail = link;
}
function appendSub(dep, link) {
  const subsTail = dep.subsTail;
  if (subsTail !== void 0) {
    subsTail.nextSub = link;
  } else {
    dep.subs = link;
  }
  dep.subsTail = link;
}
function unlinkSub(link) {
  const dep = link.dep;
  const prevSub = link.prevSub;
  const nextSub = link.nextSub;
  if (prevSub !== void 0) {
    prevSub.nextSub = nextSub;
  } else {
    dep.subs = nextSub;
  }
  if (nextSub !== void 0) {
    nextSub.prevSub = prevSub;
  } else {
    dep.subsTail = prevSub;
  }
  if (dep.activeLink === link) {
    dep.activeLink = link.rollback;
  }
  link.rollback = void 0;
  link.version = DEAD;
}
function withObserver(observer, fn) {
  const previousObserver = currentObserver;
  currentObserver = observer;
  try {
    return fn();
  } finally {
    currentObserver = previousObserver;
  }
}
function onWriteAtom(atom, comparable = false) {
  if (debug.reactivity) {
    const names = observerNames(atom);
    debugLog("reactivity", `write, ${names.length} observer(s)`, names);
  }
  for (let link = atom.subs; link !== void 0; link = link.nextSub) {
    const ctx = link.sub;
    if (ctx.state === 0) {
      if (link.version !== ctx.version) {
        continue;
      }
      invalidations++;
      if (ctx.isDerived) {
        markDownstream(ctx);
      } else if (ctx.immediate) {
        immediateObservers.push(ctx);
      } else {
        observers.push(ctx);
      }
    }
    ctx.state = comparable && ctx.state !== 1 && !ctx.notifiesWithoutRecompute ? 2 : 1;
    if (ctx.isDerived && ctx.subs === void 0) {
      pendingDisposals.add(ctx);
    }
  }
  let errors = null;
  if (immediateObservers.length && !batchDepth) {
    const toRun = immediateObservers;
    immediateObservers = [];
    errors = updateEach(toRun);
  }
  if (!flushScheduled) {
    scheduleFlush();
  }
  rethrow(errors);
}
var batchDepth = 0;
function batch(fn) {
  batchDepth++;
  let completed = false;
  try {
    const result = fn();
    completed = true;
    return result;
  } finally {
    if (--batchDepth === 0 && immediateObservers.length) {
      const toRun = immediateObservers;
      immediateObservers = [];
      if (debug.effect) {
        debugLog("effect", `batch end, ${toRun.length} immediate effect(s)`);
      }
      const errors = updateEach(toRun);
      if (completed) {
        rethrow(errors);
      } else if (errors) {
        for (const error of errors) {
          Promise.reject(error);
        }
      }
    }
  }
}
function updateEach(computations) {
  let errors = null;
  for (let i = 0; i < computations.length; i++) {
    try {
      updateOwnerFirst(computations[i]);
    } catch (error) {
      (errors ||= []).push(error);
    }
  }
  return errors;
}
function updateOwnerFirst(computation) {
  let first = null;
  for (let owner = computation.owner; owner !== null; owner = owner.owner) {
    if (owner.state !== 0 && !owner.running && owner.immediate === computation.immediate) {
      first = owner;
    }
  }
  if (first) {
    if (debug.effect) {
      debugLog("effect", `run owner ${first.name} before ${computation.name}`);
    }
    updateComputation(first);
  }
  updateComputation(computation);
}
function rethrow(errors) {
  if (errors) {
    for (let i = 1; i < errors.length; i++) {
      Promise.reject(errors[i]);
    }
    throw errors[0];
  }
}
var flushScheduled = false;
function scheduleFlush() {
  flushScheduled = true;
  Promise.resolve().then(processEffects);
}
function processEffects() {
  flushScheduled = false;
  const pending = observers;
  observers = [];
  if (debug.effect) {
    debugLog(
      "effect",
      `flush ${pending.length} effect(s)`,
      pending.map((c) => c.name)
    );
  }
  const errors = updateEach(pending);
  if (pendingDisposals.size !== 0) {
    const candidates = pendingDisposals;
    pendingDisposals = /* @__PURE__ */ new Set();
    for (const computation of candidates) {
      if (!hasObservers(computation)) {
        if (debug.computed) {
          debugLog("computed", `dispose unobserved ${computation.name}`);
        }
        disposeComputation(computation);
      }
    }
  }
  rethrow(errors);
}
function getCurrentComputation() {
  return currentComputation;
}
function setComputation(computation) {
  currentComputation = computation;
}
function updateComputation(computation) {
  const state = computation.state;
  if (state === 0) {
    return;
  }
  if (state === 2) {
    for (let link = computation.deps; link !== void 0; link = link.nextDep) {
      const source = link.dep;
      if (!source.isDerived) {
        if (!Object.is(link.seen, source.value)) {
          computation.state = 1;
          break;
        }
        continue;
      }
      updateComputation(source);
      if (computation.state === 1) {
        break;
      }
    }
    if (computation.state !== 1) {
      computation.state = 0;
      return;
    }
  }
  const invalidationsBefore = invalidations;
  computation.running = true;
  if (computation.isEffect ? debug.effect : computation.isDerived && debug.computed) {
    debugLog(computation.isEffect ? "effect" : "computed", `run ${computation.name}`);
  }
  try {
    computation.value = computation.tracksElsewhere ? detachAndRun(computation) : runTracked(computation, computation.compute);
  } catch (error) {
    if (debug.error) {
      debugLog("error", `${computation.name} threw`, error);
    }
    throw error;
  } finally {
    computation.running = false;
    try {
      if (invalidations !== invalidationsBefore) {
        settleDerivedSources(computation);
      }
    } finally {
      computation.state = 0;
    }
  }
}
function detachAndRun(computation) {
  computation.version++;
  const previousComputation = currentComputation;
  const previousObserver = currentObserver;
  currentComputation = void 0;
  currentObserver = void 0;
  try {
    return computation.compute();
  } finally {
    currentComputation = previousComputation;
    currentObserver = previousObserver;
  }
}
function settleDerivedSources(computation) {
  for (let link = computation.deps; link !== void 0; link = link.nextDep) {
    const source = link.dep;
    if (source.isDerived && source.state) {
      if (debug.computed) {
        debugLog(
          "computed",
          `settle ${source.name}, invalidated by ${computation.name}`
        );
      }
      updateComputation(source);
    }
  }
}
function runTracked(computation, fn) {
  const previousComputation = currentComputation;
  const previousObserver = currentObserver;
  computation.version++;
  computation.depsTail = void 0;
  computation.prepared = false;
  currentComputation = computation;
  currentObserver = void 0;
  try {
    return fn();
  } finally {
    currentComputation = previousComputation;
    currentObserver = previousObserver;
    endTracking(computation);
  }
}
function endTracking(computation) {
  const tail = computation.depsTail;
  let link = tail !== void 0 ? tail.nextDep : computation.deps;
  if (link !== void 0) {
    if (tail !== void 0) {
      tail.nextDep = void 0;
    } else {
      computation.deps = void 0;
    }
    do {
      const next = link.nextDep;
      unlinkSub(link);
      link = next;
    } while (link !== void 0);
  }
  for (link = computation.deps; link !== void 0; link = link.nextDep) {
    link.dep.activeLink = link.rollback;
    link.rollback = void 0;
  }
  computation.observed = null;
}
function observedSources(observer) {
  const result = /* @__PURE__ */ new Set();
  for (let link = observer.deps; link !== void 0; link = link.nextDep) {
    result.add(link.dep);
  }
  return result;
}
function removeSources(computation) {
  let link = computation.deps;
  computation.deps = void 0;
  computation.depsTail = void 0;
  computation.observed = null;
  while (link !== void 0) {
    const next = link.nextDep;
    unlinkSub(link);
    link = next;
  }
}
function disposeComputation(computation) {
  let link = computation.deps;
  computation.deps = void 0;
  computation.depsTail = void 0;
  computation.observed = null;
  let failure = null;
  while (link !== void 0) {
    const next = link.nextDep;
    unlinkSub(link);
    const derived = link.dep;
    if (derived.isDerived && !hasObservers(derived)) {
      try {
        disposeComputation(derived);
      } catch (error) {
        failure ||= { error };
      }
    }
    link = next;
  }
  computation.state = 1;
  try {
    disposeOwned(computation);
  } catch (error) {
    failure ||= { error };
  }
  if (failure) {
    throw failure.error;
  }
}
function disposeOwned(computation) {
  const owned = computation.owned;
  if (!owned) {
    return;
  }
  computation.owned = null;
  let failure = null;
  for (const dispose of owned) {
    try {
      dispose();
    } catch (error) {
      failure ||= { error };
    }
  }
  if (failure) {
    throw failure.error;
  }
}
var downstream = [];
function markDownstream(computation) {
  const stack = downstream;
  stack.push(computation);
  let current;
  while (current = stack.pop()) {
    for (let link = current.subs; link !== void 0; link = link.nextSub) {
      const observer = link.sub;
      if (observer.isDerived && observer.subs === void 0) {
        pendingDisposals.add(observer);
      }
      if (observer.state || link.version !== observer.version) {
        continue;
      }
      observer.state = observer.notifiesWithoutRecompute ? 1 : 2;
      if (observer.isDerived) {
        stack.push(observer);
      } else if (observer.immediate) {
        immediateObservers.push(observer);
      } else {
        observers.push(observer);
      }
    }
  }
}
function untrack(fn) {
  const previousComputation = currentComputation;
  currentComputation = void 0;
  let result;
  try {
    result = fn();
  } finally {
    currentComputation = previousComputation;
  }
  return result;
}
function observerNames(atom) {
  const names = [];
  for (let link = atom.subs; link !== void 0; link = link.nextSub) {
    names.push(link.sub.name || "?");
  }
  return names;
}
var scopeStack = [];
function runReversed(cbs, reportError) {
  for (let i = cbs.length - 1; i >= 0; i--) {
    try {
      cbs[i]();
    } catch (e) {
      reportError(e);
    }
  }
}
function useScope() {
  const scope = getScope();
  if (!scope) {
    throw new OwlError("No active scope");
  }
  return scope;
}
var Scope = class {
  app;
  pluginManager;
  status = STATUS.NEW;
  computations = [];
  willStart = [];
  // true while the scope runs the setup code whose onWillStart callbacks it
  // will await; outside that window a callback would be queued and never run
  collectingWillStart = false;
  _controller = null;
  _destroyCbs = null;
  _finalizing = false;
  constructor(app) {
    this.app = app;
    this.pluginManager = app.pluginManager;
  }
  /**
   * Pushes this scope on the stack for the duration of `fn`, invoking it with
   * the given arguments. Any code executed synchronously inside `fn` can reach
   * this scope via `useScope()`.
   *
   * If the scope is already dead when `run` is called, it throws an
   * `OwlError` (a programming error — nothing should schedule work in a
   * destroyed scope). This is deliberately *not* an AbortError.
   *
   * If `fn` returns a promise, `run` guards the await with the scope's
   * lifetime: the returned promise rejects with an AbortError if the scope
   * dies during the await. AbortError is part of the normal async workflow,
   * unlike the up-front OwlError above. This does not allocate an
   * AbortController — status checks are sufficient for guarding between awaits.
   */
  run(fn, ...args) {
    if (this.status > STATUS.MOUNTED) {
      throw new OwlError("Cannot run a callback in a destroyed scope");
    }
    scopeStack.push(this);
    let result;
    try {
      result = fn(...args);
    } finally {
      scopeStack.pop();
    }
    if (result !== null && typeof result?.then === "function") {
      return this._guard(result);
    }
    return result;
  }
  async _guard(p) {
    let result;
    try {
      result = await p;
    } catch (e) {
      if (this.status > STATUS.MOUNTED) {
        if (debug.scope) {
          debugLog(
            "scope",
            `${scopeName(this)}: a guarded promise failed after destroy, aborted`,
            e
          );
        }
        throw makeAbortError(e);
      }
      throw e;
    }
    if (this.status > STATUS.MOUNTED) {
      if (debug.scope) {
        debugLog("scope", `${scopeName(this)}: a guarded promise settled after destroy, aborted`);
      }
      throw makeAbortError();
    }
    return result;
  }
  /**
   * An AbortSignal tied to this scope's lifetime. If the scope is already
   * dead, returns a pre-aborted signal. Lazily allocates an AbortController
   * on first access.
   */
  get abortSignal() {
    if (this._finalizing || this.status > STATUS.MOUNTED) {
      if (!this._controller) {
        this._controller = new AbortController();
        this._controller.abort();
      }
      return this._controller.signal;
    }
    return (this._controller ??= new AbortController()).signal;
  }
  /**
   * Returns true once the scope has been destroyed, i.e. `finalize` has run:
   * the abort signal is aborted, onDestroy callbacks have executed and
   * computations are disposed.
   */
  isDestroyed() {
    return this.status >= STATUS.DESTROYED;
  }
  /**
   * Registers a callback to run when the scope is destroyed. If the scope is
   * already destroyed, the callback is invoked immediately.
   */
  onDestroy(cb) {
    if (this.status >= STATUS.DESTROYED) {
      cb();
      return;
    }
    (this._destroyCbs ??= []).push(cb);
  }
  /**
   * Aborts the scope's signal, runs all registered onDestroy callbacks in
   * reverse registration order, disposes the computations attached to this
   * scope that nothing else observes, and transitions status to DESTROYED. Callbacks run *before* the
   * status transition so they can still observe the pre-destroyed state
   * (matching the prior onWillDestroy contract). A callback registered by
   * another callback runs too, after the current round. Errors in callbacks
   * are routed to `reportError`.
   */
  finalize(reportError) {
    if (this._finalizing || this.status >= STATUS.DESTROYED) {
      return;
    }
    this._finalizing = true;
    if (debug.scope) {
      debugLog(
        "scope",
        `${scopeName(this)}: finalize, ${this._destroyCbs?.length ?? 0} destroy callback(s), ${this.computations.length} computation(s)`
      );
    }
    try {
      this._controller?.abort();
      let cbs;
      while (cbs = this._destroyCbs) {
        this._destroyCbs = null;
        runReversed(cbs, reportError);
      }
    } finally {
      disposeUnobserved(this.computations.splice(0));
      this.status = STATUS.DESTROYED;
    }
  }
  /**
   * What the scope has registered so far, for `rollback`.
   */
  mark() {
    return [this.willStart.length, this._destroyCbs?.length ?? 0, this.computations.length];
  }
  /**
   * Undoes what the scope registered since `mark`: drops the onWillStart
   * callbacks, runs the onDestroy callbacks in reverse and disposes the
   * computations. Used when a setup fails half way.
   */
  rollback(mark, reportError) {
    if (debug.scope) {
      debugLog(
        "scope",
        `${scopeName(this)}: rollback to ${mark[0]} willStart, ${mark[1]} destroy callback(s), ${mark[2]} computation(s)`
      );
    }
    this.willStart.length = mark[0];
    if (this._destroyCbs) {
      runReversed(this._destroyCbs.splice(mark[1]), reportError);
    }
    disposeUnobserved(this.computations.splice(mark[2]));
  }
  /**
   * Wrapper applied to lifecycle callbacks before they are stored. The base
   * implementation prepends the scope as the first argument, so every
   * lifecycle callback receives the scope it was registered in.
   * ComponentNode overrides to additionally bind `this` to the component and,
   * in dev mode, to rename the bound function so the hook shows up as
   * `ComponentName.hookName` in stack traces.
   */
  decorate(fn, _hookName) {
    return fn.bind(void 0, this);
  }
};
function disposeUnobserved(computations) {
  for (const computation of computations) {
    if (!hasObservers(computation)) {
      disposeComputation(computation);
    }
  }
}
function getScope() {
  const len = scopeStack.length;
  return len ? scopeStack[len - 1] : null;
}
function isAbortError(e) {
  return typeof e === "object" && e !== null && e.name === "AbortError";
}
function makeAbortError(cause) {
  const err = new Error("The operation was aborted", cause === void 0 ? void 0 : { cause });
  err.name = "AbortError";
  return err;
}
function scopeName(scope) {
  return scope.componentName ?? scope.constructor.name;
}
var KEYCHANGES = /* @__PURE__ */ Symbol("Key changes");
var objectToString = Object.prototype.toString;
var objectHasOwnProperty = Object.prototype.hasOwnProperty;
function canBeMadeReactive(value) {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const raw = toRaw(value);
  if (Array.isArray(raw) || raw instanceof Set || raw instanceof Map || raw instanceof WeakMap) {
    return true;
  }
  return objectToString.call(raw) === "[object Object]";
}
function possiblyReactive(val, shallow) {
  return !shallow && canBeMadeReactive(val) ? proxy(val) : val;
}
var skipped = /* @__PURE__ */ new WeakSet();
function markRaw(value) {
  skipped.add(value);
  return value;
}
function toRaw(value) {
  return targets.has(value) ? targets.get(value) : value;
}
var itemAtoms = { keys: /* @__PURE__ */ new WeakMap(), objectKeys: /* @__PURE__ */ new WeakMap() };
var presenceAtoms = { keys: /* @__PURE__ */ new WeakMap(), objectKeys: /* @__PURE__ */ new WeakMap() };
function isObjectKey(key) {
  return typeof key === "object" && key !== null || typeof key === "function";
}
function getTargetKeyAtom(target, key, atoms = itemAtoms) {
  if (isObjectKey(key)) {
    let table2 = atoms.objectKeys.get(target);
    if (table2 === void 0) {
      table2 = /* @__PURE__ */ new WeakMap();
      atoms.objectKeys.set(target, table2);
    }
    let atom2 = table2.get(key);
    if (atom2 === void 0) {
      atom2 = createAtom(void 0, "key");
      table2.set(key, atom2);
    }
    return atom2;
  }
  const table = getKeyAtoms(target, atoms);
  let atom = table.get(key);
  if (atom === void 0) {
    atom = createAtom(void 0, "key");
    table.set(key, atom);
  }
  return atom;
}
function getKeyAtoms(target, atoms) {
  let table = atoms.keys.get(target);
  if (table === void 0) {
    table = /* @__PURE__ */ new Map();
    atoms.keys.set(target, table);
  }
  return table;
}
function findAtom(target, key, atoms) {
  return isObjectKey(key) ? atoms.objectKeys.get(target)?.get(key) : atoms.keys.get(target)?.get(key);
}
function onReadTargetKey(target, key) {
  if (isObserving()) {
    onReadAtom(getTargetKeyAtom(target, key));
  }
}
function onWriteTargetKey(target, key, atoms = itemAtoms) {
  const atom = findAtom(target, key, atoms);
  if (atom) {
    if (debug.reactivity) {
      debugLog("reactivity", `proxy write ${describeKey(key)}`, target);
    }
    onWriteAtom(atom);
  }
}
function describeKey(key) {
  return key === KEYCHANGES ? "(keys)" : String(key);
}
function onReadKeyPresence(target, key) {
  if (isObserving()) {
    onReadAtom(getTargetKeyAtom(target, key, presenceAtoms));
  }
}
function onWriteKeyPresence(target, key) {
  onWriteTargetKey(target, KEYCHANGES);
  onWriteTargetKey(target, key, presenceAtoms);
}
function releaseKey(target, key) {
  releaseKeyAtom(target, key, itemAtoms);
  releaseKeyAtom(target, key, presenceAtoms);
}
function releaseKeyAtom(target, key, atoms) {
  const atom = findAtom(target, key, atoms);
  if (atom !== void 0 && !hasObservers(atom)) {
    if (isObjectKey(key)) {
      atoms.objectKeys.get(target).delete(key);
    } else {
      atoms.keys.get(target).delete(key);
    }
  }
}
function onWriteDroppedIndices(target, newLength, oldLength) {
  onWriteDroppedIndicesIn(target, newLength, oldLength, itemAtoms);
  onWriteDroppedIndicesIn(target, newLength, oldLength, presenceAtoms);
}
function onWriteDroppedIndicesIn(target, newLength, oldLength, atoms) {
  const table = atoms.keys.get(target);
  if (table !== void 0) {
    if (oldLength - newLength <= table.size) {
      for (let i = newLength; i < oldLength; i++) {
        onWriteDroppedIndex(target, String(i), atoms);
      }
    } else {
      for (const key of table.keys()) {
        if (typeof key === "string" && isIndexIn(key, newLength, oldLength)) {
          onWriteDroppedIndex(target, key, atoms);
        }
      }
    }
  }
}
function isIndexIn(key, start, end) {
  const index = Number(key);
  return index >= start && index < end && String(index) === key;
}
function onWriteDroppedIndex(target, key, atoms) {
  onWriteTargetKey(target, key, atoms);
  releaseKey(target, key);
}
var targets = /* @__PURE__ */ new WeakMap();
var deepProxies = /* @__PURE__ */ new WeakMap();
var shallowProxies = /* @__PURE__ */ new WeakMap();
function proxifyTarget(target, shallow) {
  if (!canBeMadeReactive(target)) {
    throw new OwlError(`Cannot make the given value reactive`);
  }
  const raw = targets.get(target);
  if (raw) {
    if ((shallow ? deepProxies : shallowProxies).get(raw) !== target) {
      return target;
    }
    target = raw;
  }
  if (skipped.has(target)) {
    return target;
  }
  const cache3 = shallow ? shallowProxies : deepProxies;
  const reactive = cache3.get(target);
  if (reactive) {
    return reactive;
  }
  let handler;
  if (target instanceof Map) {
    handler = collectionsProxyHandler(target, "Map", shallow);
  } else if (target instanceof Set) {
    handler = collectionsProxyHandler(target, "Set", shallow);
  } else if (target instanceof WeakMap) {
    handler = collectionsProxyHandler(target, "WeakMap", shallow);
  } else {
    handler = new BasicHandler(shallow);
  }
  const proxy2 = new Proxy(target, handler);
  cache3.set(target, proxy2);
  targets.set(proxy2, target);
  return proxy2;
}
function proxy(target) {
  return proxifyTarget(target, false);
}
var viewBases = /* @__PURE__ */ new WeakMap();
function observe(target, callback) {
  const computation = createComputation(
    () => untrack(callback),
    false,
    0,
    true,
    `observe ${callback.name || "callback"}`
  );
  computation.notifiesWithoutRecompute = true;
  const views = /* @__PURE__ */ new WeakMap();
  const read = (fn) => withObserver(computation, fn);
  const wrap = (value) => typeof value === "object" && value !== null && targets.has(value) ? view(value) : value;
  function view(target2) {
    const reactive = viewBases.get(target2) ?? target2;
    let result = views.get(reactive);
    if (result) {
      return result;
    }
    const raw = toRaw(reactive);
    const isCollection = raw instanceof Map || raw instanceof Set || raw instanceof WeakMap;
    result = new Proxy(reactive, {
      get(r, key, receiver) {
        const value = read(() => Reflect.get(r, key, receiver));
        if (isCollection && typeof value === "function") {
          return (...args) => {
            const result2 = read(() => value.apply(r, args));
            return isIterator(result2) ? observedIterator(result2) : wrap(result2);
          };
        }
        return wrap(value);
      },
      has(r, key) {
        return read(() => Reflect.has(r, key));
      },
      ownKeys(r) {
        return read(() => Reflect.ownKeys(r));
      },
      getOwnPropertyDescriptor(r, key) {
        return read(() => Reflect.getOwnPropertyDescriptor(r, key));
      },
      set(r, key, value) {
        return Reflect.set(r, key, value, r);
      },
      deleteProperty(r, key) {
        return Reflect.deleteProperty(r, key);
      }
    });
    views.set(reactive, result);
    viewBases.set(result, reactive);
    targets.set(result, raw);
    return result;
  }
  function observedIterator(iterator) {
    return {
      next() {
        const step = read(() => iterator.next());
        if (step.done) {
          return step;
        }
        const value = Array.isArray(step.value) ? step.value.map(wrap) : wrap(step.value);
        return { done: false, value };
      },
      [Symbol.iterator]() {
        return this;
      }
    };
  }
  return view(proxy(target));
}
function isIterator(value) {
  return typeof value === "object" && value !== null && typeof value.next === "function" && typeof value[Symbol.iterator] === "function";
}
var BasicHandler = class {
  shallow;
  // the value atoms of the target's keys
  keyAtoms;
  constructor(shallow) {
    this.shallow = shallow;
    this.keyAtoms = void 0;
  }
  get(target, key, receiver) {
    if (isObserving()) {
      let table = this.keyAtoms;
      if (table === void 0) {
        table = this.keyAtoms = getKeyAtoms(target, itemAtoms);
      }
      let atom = table.get(key);
      if (atom === void 0) {
        atom = createAtom(void 0, "key");
        table.set(key, atom);
      }
      onReadAtom(atom);
    }
    const value = Reflect.get(target, key, receiver);
    if (typeof value === "function") {
      return arrayMethods.get(value) ?? value;
    }
    if (this.shallow || typeof value !== "object" || value === null) {
      return value;
    }
    const reactive = deepProxies.get(value);
    if (reactive ? skipped.has(value) : !canBeMadeReactive(value)) {
      return value;
    }
    const desc = Object.getOwnPropertyDescriptor(target, key);
    if (desc && !desc.writable && !desc.configurable) {
      return value;
    }
    return reactive ?? proxifyTarget(value, false);
  }
  set(target, key, value, receiver) {
    return isObserving() ? untrack(() => writeKey(target, key, value, receiver)) : writeKey(target, key, value, receiver);
  }
  deleteProperty(target, key) {
    const hadKey = objectHasOwnProperty.call(target, key);
    const ret = Reflect.deleteProperty(target, key);
    if (hadKey && ret) {
      onWriteKeyPresence(target, key);
      onWriteTargetKey(target, key);
      releaseKey(target, key);
      if (Array.isArray(target)) {
        onWriteItems(target);
      }
    }
    return ret;
  }
  ownKeys(target) {
    onReadTargetKey(target, KEYCHANGES);
    return Reflect.ownKeys(target);
  }
  has(target, key) {
    onReadKeyPresence(target, key);
    return Reflect.has(target, key);
  }
};
function writeKey(target, key, value, receiver) {
  const hadKey = objectHasOwnProperty.call(target, key);
  const originalValue = Reflect.get(target, key, receiver);
  const isArray2 = Array.isArray(target);
  const originalLength = isArray2 ? target.length : 0;
  const ret = Reflect.set(target, key, toRaw(value), receiver);
  const created = !hadKey && objectHasOwnProperty.call(target, key);
  if (created) {
    onWriteKeyCreated(target, key, originalLength);
  }
  if (key === "length" && isArray2) {
    onWriteTargetKey(target, key);
    if (target.length < originalValue) {
      onWriteTargetKey(target, KEYCHANGES);
      onWriteDroppedIndices(target, target.length, originalValue);
    }
    onWriteItems(target);
  } else if (!Object.is(originalValue, Reflect.get(target, key, receiver))) {
    onWriteTargetKey(target, key);
    if (isArray2) {
      onWriteItems(target);
    }
  } else if (created && isArray2) {
    onWriteItems(target);
  }
  return ret;
}
var itemsAtoms = /* @__PURE__ */ new WeakMap();
function onWriteItems(target) {
  const atom = itemsAtoms.get(target);
  if (atom !== void 0) {
    onWriteAtom(atom);
  }
}
function readArrayItems(array) {
  const raw = targets.get(array);
  if (raw === void 0 || deepProxies.get(raw) !== array) {
    return array;
  }
  if (isObserving()) {
    let atom = itemsAtoms.get(raw);
    if (atom === void 0) {
      atom = createAtom(void 0, "key");
      itemsAtoms.set(raw, atom);
    }
    onReadAtom(atom);
  }
  if (Object.isFrozen(raw)) {
    return raw.slice();
  }
  const length = raw.length;
  const items = new Array(length);
  for (let i = 0; i < length; i++) {
    items[i] = deepItem(raw[i]);
  }
  return items;
}
function deepItem(value) {
  if (typeof value !== "object" || value === null) {
    return value;
  }
  const reactive = deepProxies.get(value);
  if (reactive ? skipped.has(value) : !canBeMadeReactive(value)) {
    return value;
  }
  return reactive ?? proxifyTarget(value, false);
}
function onWriteKeyCreated(target, key, originalLength) {
  onWriteKeyPresence(target, key);
  if (key !== "length" && Array.isArray(target) && target.length !== originalLength) {
    onWriteTargetKey(target, "length");
  }
}
var arrayMethods = /* @__PURE__ */ new Map();
for (const name of ["copyWithin", "fill", "reverse", "sort"]) {
  const method = Array.prototype[name];
  arrayMethods.set(method, function(...args) {
    return batch(() => method.apply(this, args));
  });
}
for (const name of ["pop", "push", "shift", "splice", "unshift"]) {
  const method = Array.prototype[name];
  arrayMethods.set(method, function(...args) {
    return batch(() => untrack(() => method.apply(this, args)));
  });
}
for (const name of ["includes", "indexOf", "lastIndexOf"]) {
  const method = Array.prototype[name];
  arrayMethods.set(method, function(...args) {
    const result = method.apply(this, args);
    if (result !== -1 && result !== false) {
      return result;
    }
    return method.apply(toRaw(this), [toRaw(args[0]), ...args.slice(1)]);
  });
}
var deepHandler = new BasicHandler(false);
var shallowHandler = new BasicHandler(true);
function makeKeyObserver(methodName, target, shallow) {
  return (key) => {
    key = toRaw(key);
    if (methodName === "has") {
      onReadKeyPresence(target, key);
    } else {
      onReadTargetKey(target, key);
    }
    return possiblyReactive(target[methodName](key), shallow);
  };
}
function makeIteratorObserver(methodName, target, shallow) {
  const yieldsEntries = methodName === "entries" || methodName === Symbol.iterator && target instanceof Map;
  const readsValues = target instanceof Map && methodName !== "keys";
  return function* () {
    onReadTargetKey(target, KEYCHANGES);
    for (const entry of target.entries()) {
      if (readsValues) {
        onReadTargetKey(target, entry[0]);
      }
      const item = yieldsEntries ? entry : methodName === "keys" ? entry[0] : entry[1];
      if (shallow) {
        yield item;
      } else if (yieldsEntries) {
        yield [possiblyReactive(entry[0], false), possiblyReactive(entry[1], false)];
      } else {
        yield possiblyReactive(item, false);
      }
    }
  };
}
function makeForEachObserver(target, shallow) {
  const readsValues = target instanceof Map;
  return function forEach(forEachCb, thisArg) {
    onReadTargetKey(target, KEYCHANGES);
    target.forEach(function(val, key, targetObj) {
      if (readsValues) {
        onReadTargetKey(target, key);
      }
      forEachCb.call(
        thisArg,
        possiblyReactive(val, shallow),
        possiblyReactive(key, shallow),
        possiblyReactive(targetObj, shallow)
      );
    }, thisArg);
  };
}
function membersByRaw(members) {
  const byRaw = /* @__PURE__ */ new Map();
  for (const member of members) {
    byRaw.set(toRaw(member), member);
  }
  return byRaw;
}
function makeSetOperation(name, target) {
  return (other) => {
    onReadTargetKey(target, KEYCHANGES);
    const mine = membersByRaw(target);
    const theirs = membersByRaw(other.keys());
    const notIn = (a, b) => [...a].filter(([raw]) => !b.has(raw)).map(([, member]) => member);
    switch (name) {
      case "union":
        return /* @__PURE__ */ new Set([...target, ...notIn(theirs, mine)]);
      case "intersection":
        return new Set([...mine].filter(([raw]) => theirs.has(raw)).map(([, member]) => member));
      case "difference":
        return new Set(notIn(mine, theirs));
      case "symmetricDifference":
        return /* @__PURE__ */ new Set([...notIn(mine, theirs), ...notIn(theirs, mine)]);
      case "isSubsetOf":
        return notIn(mine, theirs).length === 0;
      case "isSupersetOf":
        return notIn(theirs, mine).length === 0;
      case "isDisjointFrom":
        return [...mine.keys()].every((raw) => !theirs.has(raw));
    }
  };
}
function delegateAndNotify(setterName, getterName, target, shallow) {
  return (key, value) => {
    key = toRaw(key);
    const hadKey = target.has(key);
    const originalValue = target[getterName](key);
    const ret = target[setterName](key, shallow ? value : toRaw(value));
    const hasKey = target.has(key);
    if (hadKey !== hasKey) {
      onWriteKeyPresence(target, key);
    }
    if (!Object.is(originalValue, target[getterName](key))) {
      onWriteTargetKey(target, key);
    }
    if (!hasKey) {
      releaseKey(target, key);
    }
    return ret;
  };
}
function makeClearNotifier(target) {
  return () => {
    const allKeys = [...target.keys()];
    target.clear();
    onWriteTargetKey(target, KEYCHANGES);
    for (const key of allKeys) {
      onWriteTargetKey(target, key, presenceAtoms);
      onWriteTargetKey(target, key);
      releaseKey(target, key);
    }
  };
}
var setMethods = [
  ["has", (target, shallow) => makeKeyObserver("has", target, shallow)],
  ["add", (target, shallow) => delegateAndNotify("add", "has", target, shallow)],
  ["delete", (target, shallow) => delegateAndNotify("delete", "has", target, shallow)],
  ["keys", (target, shallow) => makeIteratorObserver("keys", target, shallow)],
  ["values", (target, shallow) => makeIteratorObserver("values", target, shallow)],
  ["entries", (target, shallow) => makeIteratorObserver("entries", target, shallow)],
  [Symbol.iterator, (target, shallow) => makeIteratorObserver(Symbol.iterator, target, shallow)],
  ["forEach", (target, shallow) => makeForEachObserver(target, shallow)],
  ["clear", (target) => makeClearNotifier(target)]
];
var setOperations = [
  "difference",
  "intersection",
  "isDisjointFrom",
  "isSubsetOf",
  "isSupersetOf",
  "symmetricDifference",
  "union"
].filter((name) => name in Set.prototype).map((name) => [name, (target) => makeSetOperation(name, target)]);
var weakMapMethods = [
  ["has", (target, shallow) => makeKeyObserver("has", target, shallow)],
  ["get", (target, shallow) => makeKeyObserver("get", target, shallow)],
  ["set", (target, shallow) => delegateAndNotify("set", "get", target, shallow)],
  ["delete", (target, shallow) => delegateAndNotify("delete", "has", target, shallow)]
];
var methodFactories = {
  Set: new Map([...setMethods, ...setOperations]),
  Map: new Map([...setMethods, ...weakMapMethods]),
  WeakMap: new Map(weakMapMethods)
};
function collectionsProxyHandler(target, targetRawType, shallow) {
  const factories = methodFactories[targetRawType];
  const hasSize = targetRawType !== "WeakMap";
  const methods = /* @__PURE__ */ new Map();
  return Object.assign(Object.create(shallow ? shallowHandler : deepHandler), {
    // FIXME: probably broken when part of prototype chain since we ignore the receiver
    get(target2, key) {
      const factory = factories.get(key);
      if (factory) {
        let method = methods.get(key);
        if (!method) {
          method = factory(target2, shallow);
          methods.set(key, method);
        }
        return method;
      }
      if (key === "size" && hasSize) {
        onReadTargetKey(target2, KEYCHANGES);
        return target2.size;
      }
      onReadTargetKey(target2, key);
      return possiblyReactive(target2[key], shallow);
    }
  });
}
function buildSignal(value, toRead, equals) {
  const atom = createAtom(value, "signal");
  const equalsFn = toEqualsFn(equals);
  const comparable = equals === void 0;
  let readValue = toRead(value);
  const readSignal = () => {
    onReadAtom(atom);
    return readValue;
  };
  readSignal[atomSymbol] = atom;
  readSignal.set = function writeSignal(newValue) {
    if (equalsFn(atom.value, newValue)) {
      return;
    }
    readValue = toRead(newValue);
    atom.value = newValue;
    onWriteAtom(atom, comparable);
  };
  return readSignal;
}
function identity(value) {
  return value;
}
function shallowProxy(value) {
  return proxifyTarget(value, true);
}
function triggerSignal(signal2) {
  if (typeof signal2 !== "function" || signal2[atomSymbol]?.type !== "signal") {
    throw new OwlError(`Value is not a signal (${signal2})`);
  }
  onWriteAtom(signal2[atomSymbol]);
}
function signalRef() {
  return buildSignal(null, identity);
}
function signalArray(initialValue = [], options = {}) {
  return buildSignal(initialValue, shallowProxy, options.equals);
}
function signalObject(initialValue = {}, options = {}) {
  return buildSignal(initialValue, shallowProxy, options.equals);
}
function signalMap(initialValue = /* @__PURE__ */ new Map(), options = {}) {
  return buildSignal(initialValue, shallowProxy, options.equals);
}
function signalSet(initialValue = /* @__PURE__ */ new Set(), options = {}) {
  return buildSignal(initialValue, shallowProxy, options.equals);
}
function signal(value, options = {}) {
  return buildSignal(value, identity, options.equals);
}
signal.trigger = triggerSignal;
signal.ref = signalRef;
signal.Array = signalArray;
signal.Map = signalMap;
signal.Object = signalObject;
signal.Set = signalSet;
function readonlySetter() {
  throw new OwlError(
    "Cannot write to a read-only computed value. Pass a `set` option to make it writable."
  );
}
function computed(getter, options = {}) {
  const equalsFn = toEqualsFn(options.equals);
  let hasValue = false;
  let failure = null;
  const computation = createComputation(() => {
    let newValue;
    try {
      newValue = getter();
      if (hasValue && !failure && equalsFn(computation.value, newValue)) {
        if (debug.computed) {
          debugLog("computed", `${computation.name} recomputed an equal value, readers kept`);
        }
        return computation.value;
      }
    } catch (error) {
      if (debug.computed) {
        debugLog("computed", `${computation.name} failed, the error is its value`, error);
      }
      if (hasValue) {
        onWriteAtom(computation);
      }
      hasValue = true;
      failure = { error };
      return void 0;
    }
    if (hasValue) {
      onWriteAtom(computation);
    }
    hasValue = true;
    failure = null;
    return newValue;
  }, true);
  computation.name = options.name || debug.computed && getter.name || "computed";
  function readComputed() {
    if (computation.state !== 0) {
      updateComputation(computation);
    }
    onReadAtom(computation);
    if (failure) {
      throw failure.error;
    }
    return computation.value;
  }
  readComputed[atomSymbol] = computation;
  readComputed.set = options.set ?? readonlySetter;
  if (!options.detached) {
    const scope = getScope();
    if (scope) {
      scope.computations.push(computation);
      computationScopes.set(computation, scope);
    }
  }
  return readComputed;
}
function selector(source, options = {}) {
  const atoms = /* @__PURE__ */ new Map();
  let swept = 0;
  let current;
  let started = false;
  let disposed = false;
  const computation = createComputation(
    () => {
      const next = source();
      if (!started) {
        started = true;
        current = next;
        return;
      }
      const previous = current;
      if (Object.is(previous, next)) {
        return;
      }
      current = next;
      untrack(() => {
        notify(previous);
        notify(next);
      });
    },
    false,
    1,
    true,
    options.name || debug.computed && source.name || "selector"
  );
  function notify(key) {
    const atom = atoms.get(key);
    if (atom === void 0) {
      return;
    }
    onWriteAtom(atom);
    if (!hasObservers(atom)) {
      atoms.delete(key);
    }
  }
  function sweep() {
    const before = atoms.size;
    atoms.forEach((atom, key) => {
      if (!hasObservers(atom)) {
        atoms.delete(key);
      }
    });
    swept = atoms.size;
    if (debug.computed) {
      debugLog(
        "computed",
        `${computation.name} swept ${before - swept} unread key(s), ${swept} kept`
      );
    }
  }
  function isSelected(key) {
    if (disposed) {
      return Object.is(current, key);
    }
    if (computation.state !== 0) {
      updateComputation(computation);
    }
    if (isObserving()) {
      let atom = atoms.get(key);
      if (atom === void 0) {
        if (atoms.size >= 2 * swept + 16) {
          sweep();
        }
        atom = createAtom(void 0, "key");
        atoms.set(key, atom);
      }
      onReadAtom(atom);
    }
    return Object.is(current, key);
  }
  if (!options.detached) {
    getScope()?.onDestroy(() => {
      disposed = true;
      disposeComputation(computation);
      atoms.clear();
    });
  }
  return isSelected;
}
function effect(fn, options) {
  return createEffect(fn, false, options);
}
function immediateEffect(fn, options) {
  return createEffect(fn, true, options);
}
function createEffect(fn, immediate, options) {
  let disposed = false;
  const computation = createComputation(
    () => {
      let failure = null;
      if (computation.value || computation.owned) {
        try {
          releaseUntracked(computation);
        } catch (error) {
          failure = { error };
        }
      }
      const result = fn();
      if (disposed) {
        computation.value = result;
        removeSources(computation);
        releaseUntracked(computation);
        return void 0;
      }
      if (failure) {
        computation.value = result;
        throw failure.error;
      }
      return result;
    },
    false,
    1,
    immediate,
    // fn.name costs a measurable share of an effect's creation: read only
    // while debugging
    options?.name || debug.effect && fn.name || (immediate ? "immediateEffect" : "effect")
  );
  const parent = getCurrentComputation();
  if (parent && !parent.isDerived) {
    (parent.owned ??= /* @__PURE__ */ new Set()).add(cleanupEffect);
    if (parent.isEffect) {
      computation.owner = parent;
    }
  } else if (parent) {
    computationScopes.get(parent)?.onDestroy(cleanupEffect);
  }
  computation.isEffect = true;
  if (debug.effect) {
    debugLog(
      "effect",
      `create ${computation.name}, owned by ${parent && !parent.isDerived ? parent.name : "nothing"}`
    );
  }
  function cleanupEffect() {
    if (debug.effect) {
      debugLog("effect", `dispose ${computation.name}`);
    }
    disposed = true;
    if (parent !== void 0 && parent.owned !== null) {
      parent.owned.delete(cleanupEffect);
    }
    computation.state = 0;
    removeSources(computation);
    if (computation.value || computation.owned) {
      releaseUntracked(computation);
    }
  }
  try {
    updateComputation(computation);
  } catch (error) {
    cleanupEffect();
    throw error;
  }
  return cleanupEffect;
}
function releaseUntracked(effect2) {
  const previousComputation = getCurrentComputation();
  setComputation(void 0);
  try {
    release(effect2);
  } finally {
    setComputation(previousComputation);
  }
}
function release(effect2) {
  let failure = null;
  try {
    disposeOwned(effect2);
  } catch (error) {
    failure = { error };
  }
  try {
    runCleanup(effect2);
  } catch (error) {
    failure ||= { error };
  }
  if (failure) {
    throw failure.error;
  }
}
function runCleanup(effect2) {
  const cleanupFn = effect2.value;
  effect2.value = void 0;
  if (typeof cleanupFn === "function") {
    cleanupFn();
  }
}
function asyncComputed(fetcher, options = {}) {
  const value = signal(options.initial, { equals: options.equals });
  const loading = signal(false);
  const error = signal(null);
  const refreshTick = signal(0);
  const scope = getScope();
  let runId = 0;
  let inFlight = false;
  let pending = null;
  function beginRun() {
    loading.set(true);
    inFlight = true;
  }
  function endRun() {
    loading.set(false);
    inFlight = false;
    pending?.resolve();
    pending = null;
  }
  function fail(e) {
    if (!isAbortError(e)) {
      error.set(toError(e));
    }
    endRun();
  }
  const stopEffect = effect(() => {
    refreshTick();
    const myRunId = ++runId;
    const controller = new AbortController();
    const abortSignals = [controller.signal];
    if (scope?.abortSignal) {
      abortSignals.push(scope.abortSignal);
    }
    beginRun();
    error.set(null);
    let promise;
    try {
      promise = Promise.resolve(fetcher({ abortSignal: AbortSignal.any(abortSignals) }));
    } catch (e) {
      fail(e);
      return;
    }
    promise.then(
      (result) => {
        if (myRunId === runId) {
          value.set(result);
          endRun();
        }
      },
      (e) => {
        if (myRunId === runId) {
          fail(e);
        }
      }
    );
    return () => controller.abort();
  });
  function dispose() {
    runId++;
    stopEffect();
    inFlight = false;
    pending?.resolve();
    pending = null;
  }
  scope?.onDestroy(dispose);
  const read = (() => value());
  read.loading = () => loading();
  read.error = () => error();
  read.refresh = () => refreshTick.set(untrack(refreshTick) + 1);
  read.dispose = dispose;
  read.currentPromise = () => {
    if (!inFlight) {
      return Promise.resolve();
    }
    if (!pending) {
      let resolve;
      pending = { promise: new Promise((res) => resolve = res), resolve };
    }
    return pending.promise;
  };
  return read;
}
function toError(e) {
  return e instanceof Error || Object.prototype.toString.call(e) === "[object Error]" ? e : new Error(String(e), { cause: e });
}
var PRINT_BUDGET = 1e3;
function makeSafeReplacer() {
  const ancestors = [];
  const seen = /* @__PURE__ */ new Set();
  let printed = 0;
  return function(_key, value) {
    if (typeof value === "function") {
      return value.name || "[Function]";
    }
    if (value && typeof value === "object") {
      const ctor = value.constructor;
      if (ctor && ctor !== Object && ctor !== Array) {
        return `[Instance of ${ctor.name || "anonymous"}]`;
      }
      while (ancestors.length && ancestors[ancestors.length - 1] !== this) {
        ancestors.pop();
      }
      if (ancestors.includes(value)) {
        return "[Circular]";
      }
      if (seen.has(value) && printed >= PRINT_BUDGET) {
        return "[Repeated]";
      }
      seen.add(value);
      printed += 1 + (Array.isArray(value) ? value.length : Object.keys(value).length);
      ancestors.push(value);
    }
    return value;
  };
}
function assertType(value, validation, errorMessage = "Value does not match the type") {
  const issues = validateType(value, validation);
  if (issues.length) {
    const issueStrings = JSON.stringify(issues, makeSafeReplacer(), 2);
    throw new OwlError(`${errorMessage}
${issueStrings}`);
  }
}
function createContext(issues, value, path, parent, depthOffset = 1) {
  return {
    issueDepth: 0,
    path,
    value,
    addIssue(issue) {
      issues.push({
        received: this.value,
        path: this.path.join(" > "),
        ...issue
      });
    },
    mergeIssues(newIssues) {
      issues.push(...newIssues);
    },
    validate(type) {
      const before = issues.length;
      type(this);
      if (issues.length > before && parent) {
        parent.issueDepth = Math.max(parent.issueDepth, this.issueDepth + depthOffset);
      }
    },
    withIssues(issues2) {
      return createContext(issues2, this.value, this.path, this, 0);
    },
    withKey(key) {
      return createContext(issues, this.value[key], this.path.concat(key), this);
    }
  };
}
function validateType(value, validation) {
  const issues = [];
  validation(createContext(issues, value, []));
  return issues;
}
var defaultSymbol = /* @__PURE__ */ Symbol("default");
var innerTypeSymbol = /* @__PURE__ */ Symbol("innerType");
var shapeSymbol = /* @__PURE__ */ Symbol("shape");
var elementTypeSymbol = /* @__PURE__ */ Symbol("elementType");
var optionalSymbol = /* @__PURE__ */ Symbol("optional");
var intersectionSymbol = /* @__PURE__ */ Symbol("intersection");
function getDefault(type) {
  return typeof type === "function" ? type[defaultSymbol] : void 0;
}
function makeOptional(type, value) {
  const validate = function validateOptional(context) {
    if (context.value === void 0) {
      return;
    }
    context.validate(type);
  };
  validate[optionalSymbol] = true;
  validate[innerTypeSymbol] = type;
  if (value !== void 0) {
    validate[defaultSymbol] = typeof value === "function" ? value : () => value;
  }
  validate.optional = (newValue) => makeOptional(type, newValue !== void 0 ? newValue : validate[defaultSymbol]);
  return validate;
}
function isOptionalType(type) {
  return typeof type === "function" && optionalSymbol in type;
}
function makeType(validate) {
  validate.optional = (value) => makeOptional(validate, value);
  return validate;
}
function applyDefaults(value, type) {
  return applyDefaultsRec(value, type);
}
function applyDefaultsRec(value, type) {
  if (typeof type !== "function") {
    return value;
  }
  if (value === void 0) {
    const factory = type[defaultSymbol];
    if (!factory) {
      return value;
    }
    value = factory();
  }
  let inner = type;
  while (typeof inner === "function" && inner[innerTypeSymbol]) {
    inner = inner[innerTypeSymbol];
  }
  if (typeof inner !== "function" || !value || typeof value !== "object") {
    return value;
  }
  const members = inner[intersectionSymbol];
  if (members) {
    let result2 = value;
    for (const member of members) {
      result2 = applyDefaultsRec(result2, member);
    }
    return result2;
  }
  const elementType2 = inner[elementTypeSymbol];
  if (elementType2 && Array.isArray(value)) {
    let result2 = value;
    for (let index = 0; index < value.length; index++) {
      const newValue = applyDefaultsRec(value[index], elementType2);
      if (newValue !== value[index]) {
        if (result2 === value) {
          result2 = [...value];
        }
        result2[index] = newValue;
      }
    }
    return result2;
  }
  const shape = inner[shapeSymbol];
  if (!shape) {
    return value;
  }
  let result = value;
  for (const key in shape) {
    const subValue = result[key];
    const newValue = applyDefaultsRec(subValue, shape[key]);
    if (newValue !== subValue) {
      if (result === value) {
        result = Array.isArray(value) ? [...value] : { ...value };
      }
      result[key] = newValue;
    }
  }
  return result;
}
function anyType() {
  return makeType(function validateAny() {
  });
}
function booleanType() {
  return makeType(function validateBoolean(context) {
    if (typeof context.value !== "boolean") {
      context.addIssue({ message: "value is not a boolean" });
    }
  });
}
function numberType() {
  return makeType(function validateNumber(context) {
    if (typeof context.value !== "number") {
      context.addIssue({ message: "value is not a number" });
    }
  });
}
function stringType() {
  return makeType(function validateString(context) {
    if (typeof context.value !== "string" && !(context.value instanceof String)) {
      context.addIssue({ message: "value is not a string" });
    }
  });
}
function arrayType(elementType2) {
  const validate = makeType(function validateArray(context) {
    if (!Array.isArray(context.value)) {
      context.addIssue({ message: "value is not an array" });
      return;
    }
    if (!elementType2) {
      return;
    }
    for (let index = 0; index < context.value.length; index++) {
      context.withKey(index).validate(elementType2);
    }
  });
  if (elementType2) {
    validate[elementTypeSymbol] = elementType2;
  }
  return validate;
}
function constructorType(constructor) {
  return makeType(function validateConstructor(context) {
    if (!(typeof context.value === "function") || !(context.value === constructor || context.value.prototype instanceof constructor)) {
      context.addIssue({ message: `value is not '${constructor.name}' or an extension` });
    }
  });
}
function customValidator(type, validator, errorMessage = "value does not match custom validation") {
  const validate = makeType(function validateCustom(context) {
    const typeIssues = [];
    context.withIssues(typeIssues).validate(type);
    if (typeIssues.length) {
      context.mergeIssues(typeIssues);
      return;
    }
    if (!validator(context.value)) {
      context.addIssue({ message: errorMessage });
    }
  });
  validate[innerTypeSymbol] = type;
  return validate;
}
function functionType(parameters = [], result = void 0) {
  return makeType(function validateFunction(context) {
    if (typeof context.value !== "function") {
      context.addIssue({ message: "value is not a function" });
    }
  });
}
function instanceType(constructor) {
  return makeType(function validateInstanceType(context) {
    if (!(context.value instanceof constructor)) {
      context.addIssue({ message: `value is not an instance of '${constructor.name}'` });
    }
  });
}
function intersection(types22) {
  const validate = makeType(function validateIntersection(context) {
    for (const type of types22) {
      context.validate(type);
    }
  });
  validate[intersectionSymbol] = types22;
  validate.toShape = () => {
    const shape = {};
    for (const member of types22) {
      const memberShape = typeof member.toShape === "function" ? member.toShape() : void 0;
      if (memberShape && !Array.isArray(memberShape)) {
        Object.assign(shape, memberShape);
      }
    }
    return shape;
  };
  return validate;
}
function literalType(literal) {
  return makeType(function validateLiteral(context) {
    if (context.value !== literal) {
      context.addIssue({
        message: `value is not equal to ${typeof literal === "string" ? `'${literal}'` : literal}`
      });
    }
  });
}
function literalSelection(literals) {
  return union(literals.map(literalType));
}
function validateObject(context, schema, isStrict) {
  if (typeof context.value !== "object" || Array.isArray(context.value) || context.value === null) {
    context.addIssue({ message: "value is not an object" });
    return;
  }
  if (!schema) {
    return;
  }
  const isShape = !Array.isArray(schema);
  let shape;
  let keys;
  if (isShape) {
    keys = Object.keys(schema);
    shape = schema;
  } else {
    keys = schema;
    shape = {};
    for (const key of keys) {
      shape[key] = null;
    }
  }
  const missingKeys = [];
  for (const key of keys) {
    if (context.value[key] === void 0) {
      if (!isOptionalType(shape[key])) {
        missingKeys.push(key);
      }
      continue;
    }
    if (isShape) {
      context.withKey(key).validate(shape[key]);
    }
  }
  if (missingKeys.length) {
    context.addIssue({
      message: "object value has missing keys",
      missingKeys
    });
  }
  if (isStrict) {
    const unknownKeys = [];
    for (const key in context.value) {
      if (!keys.includes(key)) {
        unknownKeys.push(key);
      }
    }
    if (unknownKeys.length) {
      context.addIssue({
        message: "object value has unknown keys",
        unknownKeys
      });
    }
  }
}
function objectType(schema = {}) {
  const validate = makeType(function validateLooseObject(context) {
    validateObject(context, schema, false);
  });
  if (!Array.isArray(schema)) {
    validate[shapeSymbol] = schema;
  }
  validate.toShape = () => schema;
  return validate;
}
function strictObjectType(schema) {
  const validate = makeType(function validateStrictObject(context) {
    validateObject(context, schema, true);
  });
  if (!Array.isArray(schema)) {
    validate[shapeSymbol] = schema;
  }
  validate.toShape = () => schema;
  return validate;
}
function promiseType(type) {
  return makeType(function validatePromise(context) {
    if (!(context.value instanceof Promise)) {
      context.addIssue({ message: "value is not a promise" });
    }
  });
}
function recordType(valueType) {
  return makeType(function validateRecord(context) {
    if (typeof context.value !== "object" || Array.isArray(context.value) || context.value === null) {
      context.addIssue({ message: "value is not an object" });
      return;
    }
    if (!valueType) {
      return;
    }
    for (const key in context.value) {
      context.withKey(key).validate(valueType);
    }
  });
}
function tuple(types22) {
  const validate = makeType(function validateTuple(context) {
    if (!Array.isArray(context.value)) {
      context.addIssue({ message: "value is not an array" });
      return;
    }
    if (context.value.length !== types22.length) {
      context.addIssue({ message: "tuple value does not have the correct length" });
      return;
    }
    for (let index = 0; index < types22.length; index++) {
      context.withKey(index).validate(types22[index]);
    }
  });
  validate[shapeSymbol] = types22;
  return validate;
}
function union(types22) {
  return makeType(function validateUnion(context) {
    const subIssues = [];
    let deepestIssues = null;
    let deepest = 0;
    for (const type of types22) {
      const memberIssues = [];
      const subContext = context.withIssues(memberIssues);
      subContext.validate(type);
      if (!memberIssues.length) {
        return;
      }
      if (subContext.issueDepth > deepest) {
        deepest = subContext.issueDepth;
        deepestIssues = memberIssues;
      }
      subIssues.push(...memberIssues);
    }
    if (deepestIssues) {
      context.mergeIssues(deepestIssues);
      return;
    }
    context.addIssue({
      message: "value does not match union type",
      subIssues
    });
  });
}
function reactiveValueType(type) {
  return makeType(function validateReactiveValue(context) {
    if (typeof context.value !== "function" || !context.value[atomSymbol]) {
      context.addIssue({ message: "value is not a reactive value" });
    }
  });
}
function ref(type) {
  if (typeof HTMLElement === "undefined") {
    throw new OwlError("Cannot use ref in a non-DOM environment");
  }
  return union([literalType(null), elementType(type || HTMLElement)]);
}
function elementType(constructor) {
  return makeType(function validateElement(context) {
    const value = context.value;
    const realmConstructor = value?.ownerDocument?.defaultView?.[constructor.name];
    if (!(value instanceof constructor) && !(typeof realmConstructor === "function" && value instanceof realmConstructor)) {
      context.addIssue({ message: `value is not an instance of '${constructor.name}'` });
    }
  });
}
var types = {
  and: intersection,
  any: anyType,
  array: arrayType,
  boolean: booleanType,
  constructor: constructorType,
  customValidator,
  function: functionType,
  instanceOf: instanceType,
  literal: literalType,
  number: numberType,
  object: objectType,
  or: union,
  promise: promiseType,
  record: recordType,
  ref,
  selection: literalSelection,
  signal: reactiveValueType,
  strictObject: strictObjectType,
  string: stringType,
  tuple
};
var Registry = class {
  _map = signal.Object(/* @__PURE__ */ Object.create(null));
  _order = 0;
  _name;
  _validation;
  constructor(options = {}) {
    this._name = options.name || "registry";
    this._validation = options.validation;
  }
  entries = computed(
    () => {
      const entries = Object.entries(this._map()).sort((el1, el2) => el1[1][0] - el2[1][0] || el1[1][2] - el2[1][2]).map(([str, elem]) => [str, elem[1]]);
      return entries;
    },
    { detached: true }
  );
  items = computed(() => this.entries().map((e) => e[1]), {
    detached: true
  });
  addById(item, options = {}) {
    if (!item.id) {
      throw new OwlError(`Item should have an id key (registry '${this._name}')`);
    }
    return this.add(item.id, item, options);
  }
  add(key, value, options = {}) {
    this._add(key, value, options);
    return this;
  }
  _add(key, value, options) {
    if (!options.force && untrack(() => key in this._map())) {
      throw new OwlError(
        `Key "${key}" is already registered (registry '${this._name}'). Use { force: true } to overwrite.`
      );
    }
    if (this._validation) {
      assertType(
        value,
        this._validation,
        `Registry entry does not match the type (registry '${this._name}', key: '${key}')`
      );
    }
    return untrack(() => {
      const map = this._map();
      const order = key in map ? map[key][2] : this._order++;
      const entry = [options.sequence ?? 50, value, order];
      map[key] = entry;
      return entry;
    });
  }
  get(key, defaultValue) {
    const hasKey = key in this._map();
    if (!hasKey && arguments.length < 2) {
      throw new OwlError(`Cannot find key "${key}" (registry '${this._name}')`);
    }
    return hasKey ? this._map()[key][1] : defaultValue;
  }
  delete(key) {
    untrack(() => {
      delete this._map()[key];
    });
    return this;
  }
  clear() {
    this._map.set(/* @__PURE__ */ Object.create(null));
  }
  has(key) {
    return key in this._map();
  }
  use(key, value, options = {}) {
    const scope = useScope();
    const entry = this._add(key, value, options);
    scope.onDestroy(() => {
      if (untrack(() => this._map()[key]) === entry) {
        this.delete(key);
      }
    });
    return this;
  }
  useById(item, options = {}) {
    if (!item.id) {
      throw new OwlError(`Item should have an id key (registry '${this._name}')`);
    }
    return this.use(item.id, item, options);
  }
};
var Resource = class {
  _items = signal.Array([]);
  _name;
  _validation;
  constructor(options = {}) {
    this._name = options.name;
    this._validation = options.validation;
  }
  items = computed(
    () => {
      return [...this._items()].sort((el1, el2) => el1[0] - el2[0]).map((elem) => elem[1]);
    },
    { detached: true }
  );
  add(item, options = {}) {
    this._add(item, options);
    return this;
  }
  _add(item, options) {
    if (this._validation) {
      const info = this._name ? ` (resource '${this._name}')` : "";
      assertType(item, this._validation, `Resource item does not match the type${info}`);
    }
    const entry = [options.sequence ?? 50, item];
    untrack(() => {
      this._items().push(entry);
    });
    return entry;
  }
  delete(item) {
    this._remove((entry) => entry[1] === item);
    return this;
  }
  _remove(match) {
    untrack(() => {
      const entries = this._items();
      if (entries.some(match)) {
        this._items.set(entries.filter((entry) => !match(entry)));
      }
    });
  }
  clear() {
    this._items.set([]);
  }
  has(item) {
    return this._items().some(([s, value]) => value === item);
  }
  use(item, options = {}) {
    const scope = useScope();
    const entry = this._add(item, options);
    scope.onDestroy(() => this._remove((e) => e === entry));
    return this;
  }
};
var EventModifier = {
  PREVENT_ANY: 1,
  STOP_ANY: 2,
  SELF: 4,
  PREVENT: 8,
  STOP: 16
};
var Plugin = class {
  static _shadowId;
  static get id() {
    return this._shadowId ?? this.name;
  }
  static set id(shadowId) {
    this._shadowId = shadowId;
  }
  // Plugins passed to `startPlugins` are started in batches of equal sequence,
  // ascending (lower first), like Resource/Registry. Each batch's onWillStart
  // callbacks fully settle before the next batch is instantiated, so
  // foundational plugins (low sequence) are ready before later plugins even
  // run their setup. Explicit `plugin(X)` dependencies bypass batching and
  // start immediately.
  static sequence = 50;
  __owl__;
  constructor(manager) {
    this.__owl__ = manager;
  }
  setup() {
  }
};
var PluginManager = class extends Scope {
  config;
  plugins;
  parent;
  // Resolves once all batches of plugins have started and their willStart
  // callbacks have settled. The scope transitions to MOUNTED as the last step
  // of this chain. Consumers (the root's mount(), providePlugins) await this
  // before treating the manager as ready. `willStart` itself is inherited
  // from Scope.
  ready = Promise.resolve();
  hasPendingReady = false;
  // constructors of the batches still waiting for an earlier batch's
  // willStart, by id, to tell a consumer why the plugin is not there yet
  pending = /* @__PURE__ */ new Map();
  // plugins whose constructor is running: a plugin is registered only once it
  // is built, so asking for one of them again is a dependency cycle
  constructing = /* @__PURE__ */ new Set();
  // plugins being started (constructor or setup), in dependency order: the
  // path a cycle error reports
  startingPath = [];
  // own plugin ids in start order, so a failed setup can unregister what it started
  startedIds = [];
  constructor(app, options = {}) {
    super(app);
    const parent = options.parent ?? null;
    this.parent = parent;
    this.config = parent ? Object.assign(Object.create(parent.config), options.config) : options.config ?? {};
    this.pluginManager = this;
    if (parent) {
      this.plugins = Object.create(parent.plugins);
    } else {
      this.plugins = /* @__PURE__ */ Object.create(null);
    }
  }
  destroy() {
    this.finalize((e) => console.error(e));
  }
  getPluginById(id) {
    return this.plugins[id] || null;
  }
  getPlugin(pluginConstructor) {
    return this.getPluginById(pluginConstructor.id);
  }
  startPlugin(pluginConstructor) {
    const id = pluginConstructor.id;
    if (!id) {
      throw new OwlError(`Plugin "${pluginConstructor.name}" has no id`);
    }
    if (Object.hasOwn(this.plugins, id)) {
      const existingPluginType = this.plugins[id].constructor;
      if (existingPluginType !== pluginConstructor) {
        throw new OwlError(
          `Trying to start a plugin with the same id as an other plugin (id: '${id}', existing plugin: '${existingPluginType.name}', starting plugin: '${pluginConstructor.name}')`
        );
      }
      return null;
    }
    if (this.constructing.has(pluginConstructor)) {
      const path = this.startingPath.slice(this.startingPath.indexOf(pluginConstructor));
      const ids = [...path, pluginConstructor].map((ctor) => ctor.id);
      throw new OwlError(`Circular plugin dependency: ${ids.join(" -> ")}`);
    }
    const mark = this.mark();
    const startedMark = this.startedIds.length;
    const undo = () => {
      if (debug.plugin) {
        debugLog("plugin", `start of ${id} failed, undo`, this.startedIds.slice(startedMark));
      }
      for (const startedId of this.startedIds.splice(startedMark)) {
        delete this.plugins[startedId];
      }
      this.rollback(mark, (e) => console.error(e));
    };
    if (debug.plugin) {
      debugLog(
        "plugin",
        `start ${id}`,
        this.startingPath.map((ctor) => ctor.id)
      );
    }
    let plugin2;
    this.constructing.add(pluginConstructor);
    this.startingPath.push(pluginConstructor);
    try {
      try {
        plugin2 = new pluginConstructor(this);
      } catch (e) {
        undo();
        throw e;
      } finally {
        this.constructing.delete(pluginConstructor);
      }
      this.plugins[id] = plugin2;
      this.startedIds.push(id);
      try {
        plugin2.setup();
      } catch (e) {
        undo();
        throw e;
      }
    } finally {
      this.startingPath.pop();
    }
    this.pending.delete(id);
    return plugin2;
  }
  /**
   * Whether the nearest manager, up the parent chain, that provides `id` has
   * not started it yet: its batch still waits for an earlier batch's
   * onWillStart.
   */
  isPending(id) {
    for (let manager = this; manager; manager = manager.parent) {
      if (manager.pending.has(id)) {
        return true;
      }
      if (Object.hasOwn(manager.plugins, id)) {
        return false;
      }
    }
    return false;
  }
  // Runs a batch in this scope, collecting its onWillStart callbacks. Not
  // through run(): its result is returned as is, never guarded as a promise.
  collect(fn) {
    const collecting = this.collectingWillStart;
    this.collectingWillStart = true;
    scopeStack.push(this);
    try {
      return untrack(fn);
    } finally {
      scopeStack.pop();
      this.collectingWillStart = collecting;
    }
  }
  startPlugins(pluginConstructors) {
    const fresh = pluginConstructors.filter((ctor) => {
      if (!ctor.id || Object.hasOwn(this.plugins, ctor.id)) {
        this.startPlugin(ctor);
        return false;
      }
      return true;
    });
    if (!fresh.length) {
      return;
    }
    fresh.sort((p1, p2) => p1.sequence - p2.sequence);
    const batches = [];
    for (const ctor of fresh) {
      const batch2 = batches[batches.length - 1];
      if (batch2 && batch2[0].sequence === ctor.sequence) {
        batch2.push(ctor);
      } else {
        batches.push([ctor]);
      }
    }
    for (const batch2 of batches.slice(1)) {
      for (const ctor of batch2) {
        this.pending.set(ctor.id, ctor);
      }
    }
    const startBatch = (batch2) => {
      if (this.status >= STATUS.DESTROYED) {
        return null;
      }
      if (debug.plugin) {
        debugLog(
          "plugin",
          `batch of sequence ${batch2[0].sequence}`,
          batch2.map((ctor) => ctor.id)
        );
      }
      return this.collect(() => {
        for (const ctor of batch2) {
          this.pending.delete(ctor.id);
          this.startPlugin(ctor);
        }
        const pending = this.willStart.splice(0);
        if (debug.plugin && pending.length) {
          debugLog("plugin", `batch of sequence ${batch2[0].sequence}: ${pending.length} willStart`);
        }
        return pending.length ? Promise.all(pending.map((fn) => fn())) : null;
      });
    };
    let chain = this.hasPendingReady ? this.ready : null;
    for (const batch2 of batches) {
      if (chain) {
        chain = chain.then(() => startBatch(batch2));
      } else {
        chain = startBatch(batch2);
      }
    }
    if (!chain) {
      if (this.status < STATUS.MOUNTED) {
        this.status = STATUS.MOUNTED;
      }
      return;
    }
    this.hasPendingReady = true;
    const ready = this.ready = chain.then(
      () => {
        if (debug.plugin) {
          debugLog("plugin", "ready");
        }
        if (this.status < STATUS.MOUNTED) {
          this.status = STATUS.MOUNTED;
        }
        if (this.ready === ready) {
          this.hasPendingReady = false;
        }
      },
      (e) => {
        if (debug.plugin) {
          debugLog("plugin", "start failed, later batches skipped", e);
        }
        this.pending.clear();
        if (this.status >= STATUS.DESTROYED) {
          if (debug.plugin) {
            debugLog(
              "plugin",
              `${isAbortError(e) ? "abort" : "failure"} after destroy, dropped`,
              e
            );
          }
          return;
        }
        throw e;
      }
    );
  }
};
function startPlugins(manager, plugins) {
  if (Array.isArray(plugins)) {
    manager.startPlugins(plugins);
  } else {
    manager.onDestroy(effect(() => manager.startPlugins(plugins.items())));
  }
}
function onWillStart(fn) {
  const scope = useScope();
  if (!scope.collectingWillStart) {
    throw new OwlError("onWillStart can only be called while a component or plugin is set up");
  }
  scope.willStart.push(scope.decorate(fn, "onWillStart"));
}
function onWillDestroy(fn) {
  const scope = useScope();
  scope.onDestroy(scope.decorate(fn, "onWillDestroy"));
}
var EventBus = class extends EventTarget {
  trigger(name, payload) {
    this.dispatchEvent(new CustomEvent(name, { detail: payload }));
  }
};
function shallowEqual(a, b) {
  if (Object.is(a, b)) {
    return true;
  }
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) {
    return false;
  }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
      return false;
    }
    for (let i = 0; i < a.length; i++) {
      if (!Object.is(a[i], b[i])) {
        return false;
      }
    }
    return true;
  }
  const protoA = Object.getPrototypeOf(a);
  const protoB = Object.getPrototypeOf(b);
  if (protoA !== Object.prototype && protoA !== null || protoB !== Object.prototype && protoB !== null) {
    return false;
  }
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) {
    return false;
  }
  for (const key of keysA) {
    if (!Object.prototype.hasOwnProperty.call(b, key) || !Object.is(a[key], b[key])) {
      return false;
    }
  }
  return true;
}
var Markup = class extends String {
};
var ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "'": "&#x27;",
  '"': "&quot;",
  "`": "&#x60;"
};
var ESCAPED_CHAR = /[&<>'"`]/g;
function htmlEscape(str) {
  if (str instanceof Markup) {
    return str;
  }
  if (str === void 0) {
    return markup("");
  }
  if (typeof str === "number") {
    return markup(String(str));
  }
  return markup(String(str).replace(ESCAPED_CHAR, (char) => ESCAPES[char]));
}
function markup(valueOrStrings, ...placeholders) {
  if (!Array.isArray(valueOrStrings)) {
    return new Markup(valueOrStrings);
  }
  const strings = valueOrStrings;
  let acc = "";
  let i = 0;
  for (; i < placeholders.length; ++i) {
    acc += strings[i] + htmlEscape(placeholders[i]);
  }
  acc += strings[i];
  return new Markup(acc);
}
function useEffect(fn) {
  onWillDestroy(effect(fn));
}
function useOnChange(dependencies, callback, { initialRun = true } = {}) {
  const deps = computed(dependencies, { equals: shallowEqual });
  let skipRun = !initialRun;
  useEffect(() => {
    const args = deps();
    if (skipRun) {
      skipRun = false;
      return;
    }
    return untrack(() => callback(...args));
  });
}
function useListener(target, eventName, handler, eventParams) {
  if (typeof target === "function") {
    useEffect(() => {
      const el = target();
      if (el) {
        const listener = makeListener(handler);
        el.addEventListener(eventName, listener, eventParams);
        return () => el.removeEventListener(eventName, listener, eventParams);
      }
      return;
    });
  } else {
    const listener = makeListener(handler);
    target.addEventListener(eventName, listener, eventParams);
    onWillDestroy(() => target.removeEventListener(eventName, listener, eventParams));
  }
}
var currentEvent = null;
function setCurrentEvent(ev) {
  if (currentEvent?.deref() !== ev) {
    currentEvent = new WeakRef(ev);
  }
}
function makeListener(handler) {
  const attachedDuring = currentEvent?.deref();
  return function(ev) {
    if (ev === attachedDuring) {
      return;
    }
    setCurrentEvent(ev);
    handler.call(this, ev);
  };
}
function useApp() {
  return useScope().app;
}
function usePlugin(pluginType) {
  const scope = useScope();
  const manager = scope.pluginManager;
  const isPlugin = scope instanceof PluginManager;
  if (!isPlugin && manager.isPending(pluginType.id)) {
    throw new OwlError(
      `Plugin "${pluginType.id}" is not started yet: its batch waits for the onWillStart of a lower sequence. Use it from a child component, or lower its sequence.`
    );
  }
  const plugin2 = manager.getPluginById(pluginType.id) ?? (isPlugin ? manager.startPlugin(pluginType) : null);
  if (!plugin2) {
    throw new OwlError(`Unknown plugin "${pluginType.id}"`);
  }
  const scoped = plugin2.constructor.scoped;
  return scoped ? scoped(plugin2, scope) : plugin2;
}
var plugin = usePlugin;
function useConfig(key, type) {
  const scope = useScope();
  if (!(scope instanceof PluginManager)) {
    throw new OwlError("Expected to be in a plugin scope");
  }
  if (scope.app.dev && type) {
    assertType(scope.config, types.object({ [key]: type }), "Config does not match the type");
  }
  const configValue = scope.config[key];
  return configValue === void 0 ? getDefault(type)?.() : configValue;
}
var config = useConfig;

// ../owl-runtime/src/status.ts
function status(entity) {
  switch (entity.__owl__.status) {
    case STATUS.NEW:
      return "new";
    case STATUS.MOUNTED:
      return entity instanceof Plugin ? "started" : "mounted";
    case STATUS.DESTROYED:
      return "destroyed";
  }
}

// ../owl-runtime/src/rendering/error_handling.ts
var fibersInError = /* @__PURE__ */ new WeakMap();
var nodeErrorHandlers = /* @__PURE__ */ new WeakMap();
function invokeErrorHandlers(node, error, finalize) {
  while (node) {
    const handlers = nodeErrorHandlers.get(node);
    if (handlers) {
      for (let i = handlers.length - 1; i >= 0; i--) {
        try {
          handlers[i](error, finalize);
          return { handled: true, error };
        } catch (e) {
          error = e;
        }
      }
    }
    node = node.parent;
  }
  return { handled: false, error };
}
function forwardErrorToParent(boundary) {
  return (error, finalize) => {
    if (boundary.app.destroyed) {
      throw error;
    }
    const result = invokeErrorHandlers(boundary, error, finalize);
    if (!result.handled) {
      finalize();
      boundary.app._handleError(result.error);
    }
  };
}
function handleError(params) {
  const { error } = params;
  const node = "node" in params ? params.node : params.fiber.node;
  const fiber = "fiber" in params ? params.fiber : node.fiber;
  const app = node.app;
  if (app.destroyed) {
    throw error;
  }
  if (fiber) {
    let current = fiber;
    do {
      current.node.fiber = current;
      fibersInError.set(current, error);
      current = current.parent;
    } while (current);
    const root = fiber.root;
    fibersInError.set(root, error);
    (root.failed ||= /* @__PURE__ */ new Set()).add(fiber);
  }
  const finalize = () => {
    try {
      app.destroy();
    } catch {
    }
  };
  const result = invokeErrorHandlers(node, error, finalize);
  if (debug.error) {
    debugLog(
      "error",
      result.handled ? `${node.componentName}: error handled by an ancestor's onError` : `${node.componentName}: error not handled, the app is destroyed`,
      error
    );
  }
  if (!result.handled) {
    finalize();
    app._handleError(result.error);
  }
  if (fiber && fiber.root.counter !== 0) {
    fiber.root.node.app.scheduler.requestFrame();
  }
}
function handleHookRejection(node, error) {
  if (node.status > STATUS.MOUNTED) {
    if (debug.error) {
      debugLog(
        "error",
        `${node.componentName}: ${isAbortError(error) ? "abort" : "rejection"} after destroy, dropped`,
        error
      );
    }
    return;
  }
  handleError({ node, error });
}

// ../owl-runtime/src/blockdom/config.ts
var config2 = {
  // this is the main event handler. Every event handler registered with blockdom
  // will go through this function, giving it the data registered in the block
  // and the event
  mainEventHandler: (data, ev, currentTarget) => {
    if (typeof data === "function") {
      data(ev);
    } else if (Array.isArray(data)) {
      data[0](data[1], ev);
    }
  }
};

// ../owl-runtime/src/blockdom/toggler.ts
var txt = globalThis.document?.createTextNode("");
var VToggler = class {
  // not `key`: a toggler in a keyed list gets its list key written there
  kind;
  child;
  constructor(kind, child) {
    this.kind = kind;
    this.child = child;
  }
  mount(parent, afterNode) {
    this.child.mount(parent, afterNode);
  }
  moveBeforeDOMNode(node) {
    this.child.moveBeforeDOMNode(node);
  }
  moveBeforeVNode(other, afterNode) {
    this.moveBeforeDOMNode(other && other.firstNode() || afterNode);
  }
  patch(other, withBeforeRemove) {
    if (this === other) {
      return;
    }
    let child1 = this.child;
    let child2 = other.child;
    if (this.kind === other.kind) {
      child1.patch(child2, withBeforeRemove);
    } else {
      const firstNode = child1.firstNode();
      const parent = firstNode.parentNode;
      parent.insertBefore(txt, firstNode);
      if (withBeforeRemove) {
        child1.beforeRemove();
      }
      child1.remove();
      child2.mount(parent, txt);
      parent.removeChild(txt);
      this.child = child2;
      this.kind = other.kind;
    }
  }
  beforeRemove() {
    this.child.beforeRemove();
  }
  remove() {
    this.child.remove();
  }
  firstNode() {
    return this.child.firstNode();
  }
  toString() {
    return this.child.toString();
  }
};
function toggler(kind, child) {
  return new VToggler(kind, child);
}

// ../owl-runtime/src/blockdom/attributes.ts
var elemSetAttribute;
var removeAttribute;
var tokenListAdd;
var tokenListRemove;
if (typeof Element !== "undefined") {
  ({ setAttribute: elemSetAttribute, removeAttribute } = Element.prototype);
  const tokenList = DOMTokenList.prototype;
  tokenListAdd = tokenList.add;
  tokenListRemove = tokenList.remove;
}
var isArray = Array.isArray;
var { split, trim } = String.prototype;
var wordRegexp = /\s+/;
function setAttribute(key, value) {
  switch (value) {
    case false:
    case null:
    case void 0:
      removeAttribute.call(this, key);
      break;
    case true:
      elemSetAttribute.call(this, key, "");
      break;
    default:
      elemSetAttribute.call(this, key, value);
  }
}
function createAttrUpdater(attr) {
  return function(value) {
    setAttribute.call(this, attr, value);
  };
}
var NO_ATTRS = Object.freeze({});
function toAttrs(attrs) {
  return !attrs ? NO_ATTRS : isArray(attrs) ? { [attrs[0]]: attrs[1] } : attrs;
}
function makeAttrsUpdaters(updateClassFn, updateStyleFn) {
  function updateAttr(el, name, val, oldVal) {
    if (name === "class") {
      updateClassFn.call(el, val, oldVal);
    } else if (name === "style") {
      updateStyleFn.call(el, val, oldVal);
    } else {
      setAttribute.call(el, name, val);
    }
  }
  function attrsUpdater2(attrs, oldAttrs) {
    const next = toAttrs(attrs);
    const prev = toAttrs(oldAttrs);
    for (const name in prev) {
      if (!(name in next)) {
        updateAttr(this, name, void 0, prev[name]);
      }
    }
    for (const name in next) {
      const val = next[name];
      if (val !== prev[name]) {
        updateAttr(this, name, val, prev[name]);
      }
    }
  }
  function attrsSetter2(attrs) {
    attrsUpdater2.call(this, attrs, NO_ATTRS);
  }
  return { attrsSetter: attrsSetter2, attrsUpdater: attrsUpdater2 };
}
var { attrsSetter, attrsUpdater } = makeAttrsUpdaters(updateClass, updateStyle);
function toClassObj(expr) {
  const result = {};
  addClasses(result, expr);
  return result;
}
function addClasses(result, expr) {
  if (expr === false || expr === null || expr === void 0) {
    return;
  }
  switch (typeof expr) {
    case "string":
      addWords(result, expr, true);
      return;
    case "object":
      if (isArray(expr)) {
        for (const item of expr) {
          addClasses(result, item);
        }
      } else if (expr instanceof String) {
        addWords(result, expr.valueOf(), true);
      } else {
        for (const key in expr) {
          const value = expr[key];
          if (value) {
            addWords(result, key, value);
          }
        }
      }
      return;
    default:
      result[expr] = true;
  }
}
function addWords(result, str, value) {
  str = trim.call(str);
  if (str) {
    const words = split.call(str, wordRegexp);
    for (let i = 0, l = words.length; i < l; i++) {
      result[words[i]] = value;
    }
  }
}
var CSS_PROP_CACHE = /* @__PURE__ */ Object.create(null);
function toKebabCase(prop) {
  if (prop in CSS_PROP_CACHE) {
    return CSS_PROP_CACHE[prop];
  }
  const result = prop.startsWith("--") ? prop : prop.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());
  CSS_PROP_CACHE[prop] = result;
  return result;
}
var IMPORTANT_RE = /\s*!\s*important\s*$/i;
function holdsStyleProp(style, prop, value) {
  const important = IMPORTANT_RE.test(value);
  return style.getPropertyPriority(prop) === (important ? "important" : "") && style.getPropertyValue(prop) === (important ? value.replace(IMPORTANT_RE, "") : value);
}
function setStyleProp(style, prop, value) {
  if (IMPORTANT_RE.test(value)) {
    style.setProperty(prop, value.replace(IMPORTANT_RE, ""), "important");
  } else {
    style.setProperty(prop, value);
  }
}
function toStyleObj(expr) {
  const result = {};
  switch (typeof expr) {
    case "string": {
      const str = expr;
      const len = str.length;
      let i = 0;
      while (i < len) {
        const start = i;
        let depth = 0;
        let quote = 0;
        while (i < len) {
          const c = str.charCodeAt(i);
          if (quote) {
            if (c === 92) {
              i += 2;
              continue;
            }
            if (c === quote) {
              quote = 0;
            }
          } else if (c === 34 || c === 39) {
            quote = c;
          } else if (c === 40) {
            depth++;
          } else if (c === 41) {
            if (depth > 0) depth--;
          } else if (c === 59 && depth === 0) {
            break;
          }
          i++;
        }
        const part = trim.call(str.slice(start, i));
        i++;
        if (!part) {
          continue;
        }
        const colonIdx = part.indexOf(":");
        if (colonIdx === -1) {
          continue;
        }
        const prop = trim.call(part.slice(0, colonIdx));
        const value = trim.call(part.slice(colonIdx + 1));
        if (prop && value && value !== "undefined") {
          result[prop] = value;
        }
      }
      return result;
    }
    case "object":
      for (let prop in expr) {
        const value = expr[prop];
        if (value || value === 0) {
          result[toKebabCase(prop)] = String(value);
        }
      }
      return result;
    default:
      return {};
  }
}
function setClass(val) {
  val = toClassObj(val);
  for (let k in val) {
    tokenListAdd.call(this.classList, k);
  }
}
function updateClass(val, oldVal) {
  oldVal = toClassObj(oldVal);
  val = toClassObj(val);
  for (let k in oldVal) {
    if (!(k in val)) {
      tokenListRemove.call(this.classList, k);
    }
  }
  for (let k in val) {
    if (val[k] !== oldVal[k]) {
      tokenListAdd.call(this.classList, k);
    }
  }
}
var classCounts = /* @__PURE__ */ new WeakMap();
function makeSharedClassUpdaters(staticClasses) {
  function getCounts(el) {
    let counts = classCounts.get(el);
    if (!counts) {
      counts = /* @__PURE__ */ new Map();
      for (const k of staticClasses) {
        counts.set(k, 1);
      }
      classCounts.set(el, counts);
    }
    return counts;
  }
  function classUpdater(val, oldVal) {
    const prev = toClassObj(oldVal);
    const next = toClassObj(val);
    const classList = this.classList;
    let counts;
    for (const k in prev) {
      if (!(k in next)) {
        counts ||= getCounts(this);
        const count = counts.get(k) - 1;
        if (count) {
          counts.set(k, count);
        } else {
          counts.delete(k);
          tokenListRemove.call(classList, k);
        }
      }
    }
    for (const k in next) {
      if (!(k in prev)) {
        counts ||= getCounts(this);
        counts.set(k, (counts.get(k) || 0) + 1);
        tokenListAdd.call(classList, k);
      } else if (next[k] !== prev[k]) {
        tokenListAdd.call(classList, k);
      }
    }
  }
  return classUpdater;
}
function setStyle(val) {
  val = val === "" ? {} : toStyleObj(val);
  const style = this.style;
  for (let prop in val) {
    setStyleProp(style, prop, val[prop]);
  }
}
function updateStyle(val, oldVal) {
  patchStyle(this, oldVal === "" ? {} : toStyleObj(oldVal), val === "" ? {} : toStyleObj(val));
}
function patchStyle(el, oldVal, val) {
  const style = el.style;
  let removed2 = false;
  for (let prop in oldVal) {
    if (!(prop in val)) {
      style.removeProperty(prop);
      removed2 = true;
    }
  }
  const oldProps = removed2 ? null : Object.keys(oldVal);
  let next = 0;
  let changed = false;
  for (let prop in val) {
    const value = val[prop];
    if (oldProps && prop in oldVal && oldProps[next++] !== prop) {
      changed = true;
    }
    if (removed2 || value !== oldVal[prop] || changed && !holdsStyleProp(style, prop, value)) {
      setStyleProp(style, prop, value);
      changed = true;
    }
  }
  if (!style.cssText) {
    removeAttribute.call(el, "style");
  }
}
var styleLayers = /* @__PURE__ */ new WeakMap();
function makeSharedStyleUpdaters(staticStyle) {
  const base = toStyleObj(staticStyle);
  let sources = 0;
  return () => {
    const layer = ++sources;
    return function styleUpdater(val) {
      let state = styleLayers.get(this);
      if (!state) {
        state = { layers: [base], applied: base };
        styleLayers.set(this, state);
      }
      const layers = state.layers;
      layers[layer] = toStyleObj(val);
      const merged = {};
      for (let i = 0; i < layers.length; i++) {
        const props2 = layers[i];
        for (const prop in props2) {
          delete merged[prop];
          merged[prop] = props2[prop];
        }
      }
      patchStyle(this, state.applied, merged);
      state.applied = merged;
    };
  };
}

// ../owl-runtime/src/blockdom/events.ts
function createEventHandler(rawEvent) {
  const eventName = rawEvent.split(".")[0];
  const capture = rawEvent.includes(".capture");
  const passive = rawEvent.includes(".passive");
  if (rawEvent.includes(".synthetic")) {
    return createSyntheticHandler(eventName, capture, passive);
  } else {
    return createElementHandler(eventName, capture, passive);
  }
}
var nextNativeEventId = 1;
function createElementHandler(evName, capture = false, passive = false) {
  let eventKey = `__event__${evName}_${nextNativeEventId++}`;
  if (capture) {
    eventKey = `${eventKey}_capture`;
  }
  function listener(ev) {
    const currentTarget = ev.currentTarget;
    if (!currentTarget || !currentTarget.isConnected) return;
    const data = currentTarget[eventKey];
    if (!data) return;
    config2.mainEventHandler(data, ev, currentTarget);
  }
  const options = passive ? { capture, passive } : capture;
  function setup(data) {
    this[eventKey] = data;
    this.addEventListener(evName, listener, options);
  }
  function remove2() {
    delete this[eventKey];
    this.removeEventListener(evName, listener, options);
  }
  function update(data) {
    this[eventKey] = data;
  }
  return { setup, update, remove: remove2 };
}
var nextSyntheticEventId = 1;
function createSyntheticHandler(evName, capture = false, passive = false) {
  let eventKey = `__event__synthetic_${evName}`;
  if (capture) {
    eventKey = `${eventKey}_capture`;
  }
  if (passive) {
    eventKey = `${eventKey}_passive`;
  }
  setupSyntheticEvent(evName, eventKey, capture, passive);
  const currentId = nextSyntheticEventId++;
  function setup(data) {
    const _data = this[eventKey] || {};
    _data[currentId] = data;
    this[eventKey] = _data;
  }
  function remove2() {
    delete this[eventKey]?.[currentId];
  }
  return { setup, update: setup, remove: remove2 };
}
function nativeToSyntheticEvent(eventKey, capture, event) {
  const path = event.composedPath();
  const last = path.length - 1;
  let stoppedImmediately = false;
  const shadowed = Object.hasOwn(event, "stopImmediatePropagation");
  const stopImmediatePropagation = event.stopImmediatePropagation;
  event.stopImmediatePropagation = function() {
    stoppedImmediately = true;
    stopImmediatePropagation.call(this);
  };
  try {
    for (let i = 0; i <= last; i++) {
      const node = path[capture ? last - i : i];
      const handlers = node[eventKey];
      if (!handlers || !node.isConnected) {
        continue;
      }
      for (const id in handlers) {
        config2.mainEventHandler(handlers[id], event, node);
        if (stoppedImmediately) {
          return;
        }
      }
      if (event.cancelBubble) {
        return;
      }
    }
  } finally {
    if (shadowed) {
      event.stopImmediatePropagation = stopImmediatePropagation;
    } else {
      delete event.stopImmediatePropagation;
    }
  }
}
var SYNTHETIC_LISTENER = /* @__PURE__ */ Symbol.for("owl.syntheticListener");
var CONFIGURED_SYNTHETIC_EVENTS = {};
function setupSyntheticEvent(evName, eventKey, capture = false, passive = false) {
  if (CONFIGURED_SYNTHETIC_EVENTS[eventKey]) {
    return;
  }
  const listener = (event) => nativeToSyntheticEvent(eventKey, capture, event);
  listener[SYNTHETIC_LISTENER] = true;
  document.addEventListener(evName, listener, { capture, passive });
  CONFIGURED_SYNTHETIC_EVENTS[eventKey] = true;
}

// ../owl-runtime/src/blockdom/event_catcher.ts
var catchersByParent = /* @__PURE__ */ new WeakMap();
function releaseCatchers(parent) {
  const catchers = catchersByParent.get(parent);
  if (catchers) {
    catchersByParent.delete(parent);
    for (const catcher of catchers) {
      catcher.releaseHandlers();
    }
  }
}
function createCatcher(eventsSpec) {
  const n = Object.keys(eventsSpec).length;
  class VCatcher {
    child;
    handlerData;
    handlerFns = [];
    parentEl;
    afterNode = null;
    constructor(child, handlers) {
      this.child = child;
      this.handlerData = handlers;
    }
    mount(parent, afterNode) {
      this.parentEl = parent;
      this.child.mount(parent, afterNode);
      this.afterNode = document.createTextNode("");
      parent.insertBefore(this.afterNode, afterNode);
      for (let name in eventsSpec) {
        const index = eventsSpec[name];
        const handler = createEventHandler(name);
        this.handlerFns[index] = handler;
        handler.setup.call(parent, [this.makeDispatcher(index), null]);
      }
      let catchers = catchersByParent.get(parent);
      if (!catchers) {
        catchersByParent.set(parent, catchers = /* @__PURE__ */ new Set());
      }
      catchers.add(this);
    }
    releaseHandlers() {
      for (let i = 0; i < n; i++) {
        this.handlerFns[i].remove.call(this.parentEl);
      }
    }
    // Registered once per event, it reads the latest handler data at dispatch,
    // and applies its modifiers only to an event from inside the child: the
    // listener sits on the parent, which the child shares with its siblings.
    makeDispatcher(index) {
      return (_, ev) => {
        const target = ev.target;
        const afterNode = this.afterNode;
        let currentNode = this.child.firstNode();
        while (currentNode && currentNode !== afterNode) {
          if (currentNode.contains(target)) {
            config2.mainEventHandler(this.handlerData[index], ev, this.parentEl);
            return;
          }
          currentNode = currentNode.nextSibling;
        }
      };
    }
    moveBeforeDOMNode(node) {
      this.child.moveBeforeDOMNode(node);
      this.parentEl.insertBefore(this.afterNode, node);
    }
    moveBeforeVNode(other, afterNode) {
      if (other) {
        afterNode = other.firstNode() || afterNode;
      }
      this.child.moveBeforeVNode(other ? other.child : null, afterNode);
      this.parentEl.insertBefore(this.afterNode, afterNode);
    }
    patch(other, withBeforeRemove) {
      if (this === other) {
        return;
      }
      this.handlerData = other.handlerData;
      this.child.patch(other.child, withBeforeRemove);
    }
    beforeRemove() {
      this.child.beforeRemove();
    }
    remove() {
      this.releaseHandlers();
      catchersByParent.get(this.parentEl)?.delete(this);
      this.child.remove();
      this.afterNode.remove();
    }
    firstNode() {
      return this.child.firstNode();
    }
    toString() {
      return this.child.toString();
    }
  }
  return function(child, handlers) {
    return new VCatcher(child, handlers);
  };
}

// ../owl-runtime/src/blockdom/dom.ts
var nodeInsertBefore;
var nodeAppendChild;
var nodeRemoveChild;
var nodeSetTextContent;
var characterDataSetData;
var nodeGetFirstChild;
var nodeGetNextSibling;
if (typeof Node !== "undefined") {
  const nodeProto = Node.prototype;
  const getDescriptor = (o, p) => Object.getOwnPropertyDescriptor(o, p);
  nodeInsertBefore = nodeProto.insertBefore;
  nodeAppendChild = nodeProto.appendChild;
  nodeRemoveChild = nodeProto.removeChild;
  nodeSetTextContent = getDescriptor(nodeProto, "textContent").set;
  characterDataSetData = getDescriptor(CharacterData.prototype, "data").set;
  nodeGetFirstChild = getDescriptor(nodeProto, "firstChild").get;
  nodeGetNextSibling = getDescriptor(nodeProto, "nextSibling").get;
}

// ../owl-runtime/src/blockdom/multi.ts
var VMulti = class {
  children;
  anchors;
  parentEl;
  isOnlyChild;
  constructor(children) {
    this.children = children;
  }
  mount(parent, afterNode) {
    const children = this.children;
    const l = children.length;
    const anchors = new Array(l);
    for (let i = 0; i < l; i++) {
      let child = children[i];
      if (child) {
        child.mount(parent, afterNode);
      } else {
        const childAnchor = document.createTextNode("");
        anchors[i] = childAnchor;
        nodeInsertBefore.call(parent, childAnchor, afterNode);
      }
    }
    this.anchors = anchors;
    this.parentEl = parent;
  }
  moveBeforeDOMNode(node) {
    const parent = this.parentEl;
    const children = this.children;
    const anchors = this.anchors;
    for (let i = 0, l = children.length; i < l; i++) {
      let child = children[i];
      if (child) {
        child.moveBeforeDOMNode(node);
      } else {
        const anchor = anchors[i];
        nodeInsertBefore.call(parent, anchor, node);
      }
    }
  }
  moveBeforeVNode(other, afterNode) {
    if (other) {
      const next = other.children[0];
      afterNode = (next ? next.firstNode() : other.anchors[0]) || null;
    }
    const children = this.children;
    const parent = this.parentEl;
    const anchors = this.anchors;
    for (let i = 0, l = children.length; i < l; i++) {
      let child = children[i];
      if (child) {
        child.moveBeforeVNode(null, afterNode);
      } else {
        const anchor = anchors[i];
        nodeInsertBefore.call(parent, anchor, afterNode);
      }
    }
  }
  patch(other, withBeforeRemove) {
    if (this === other) {
      return;
    }
    const children1 = this.children;
    const children2 = other.children;
    const anchors = this.anchors;
    const parentEl = this.parentEl;
    for (let i = 0, l = children1.length; i < l; i++) {
      const vn1 = children1[i];
      const vn2 = children2[i];
      if (vn1) {
        if (vn2) {
          vn1.patch(vn2, withBeforeRemove);
        } else {
          const afterNode = vn1.firstNode();
          const anchor = anchors[i] || (anchors[i] = document.createTextNode(""));
          nodeInsertBefore.call(parentEl, anchor, afterNode);
          if (withBeforeRemove) {
            vn1.beforeRemove();
          }
          vn1.remove();
          children1[i] = void 0;
        }
      } else if (vn2) {
        children1[i] = vn2;
        const anchor = anchors[i];
        vn2.mount(parentEl, anchor);
        nodeRemoveChild.call(parentEl, anchor);
      }
    }
  }
  beforeRemove() {
    const children = this.children;
    for (let i = 0, l = children.length; i < l; i++) {
      const child = children[i];
      if (child) {
        child.beforeRemove();
      }
    }
  }
  remove() {
    const parentEl = this.parentEl;
    if (this.isOnlyChild) {
      nodeSetTextContent.call(parentEl, "");
      releaseCatchers(parentEl);
    } else {
      const children = this.children;
      const anchors = this.anchors;
      for (let i = 0, l = children.length; i < l; i++) {
        const child = children[i];
        if (child) {
          child.remove();
        } else {
          nodeRemoveChild.call(parentEl, anchors[i]);
        }
      }
    }
  }
  firstNode() {
    const child = this.children[0];
    return child ? child.firstNode() : this.anchors[0];
  }
  toString() {
    return this.children.map((c) => c ? c.toString() : "").join("");
  }
};
function multi(children) {
  return new VMulti(children);
}

// ../owl-runtime/src/blockdom/text.ts
var VText = class {
  text;
  parentEl;
  el;
  constructor(text2) {
    this.text = text2;
  }
  mount(parent, afterNode) {
    this.parentEl = parent;
    const node = document.createTextNode(toText(this.text));
    nodeInsertBefore.call(parent, node, afterNode);
    this.el = node;
  }
  moveBeforeDOMNode(node) {
    nodeInsertBefore.call(this.parentEl, this.el, node);
  }
  moveBeforeVNode(other, afterNode) {
    nodeInsertBefore.call(this.parentEl, this.el, other ? other.el : afterNode);
  }
  beforeRemove() {
  }
  remove() {
    nodeRemoveChild.call(this.parentEl, this.el);
  }
  firstNode() {
    return this.el;
  }
  patch(other) {
    const text2 = other.text;
    if (this.text !== text2) {
      characterDataSetData.call(this.el, toText(text2));
      this.text = text2;
    }
  }
  toString() {
    return this.text;
  }
};
function text(str) {
  return new VText(str);
}
function toText(value) {
  switch (typeof value) {
    case "string":
      return value;
    case "number":
      return String(value);
    case "boolean":
      return value ? "true" : "false";
    default:
      return value || "";
  }
}

// ../owl-runtime/src/blockdom/block_compiler.ts
var NO_OP = () => {
};
var XMLNS_URI = "http://www.w3.org/2000/xmlns/";
var stringifying = 0;
function makePropSetter(name) {
  return function setProp(value) {
    this[name] = value === 0 ? 0 : value ? value.valueOf() : "";
  };
}
var cache = {};
function createBlock(str) {
  if (str in cache) {
    return cache[str];
  }
  const doc = new DOMParser().parseFromString(`<t>${str}</t>`, "text/xml");
  const node = doc.firstChild.firstChild;
  const tree = buildTree(node);
  const context = buildContext(tree);
  const template = tree.el;
  const Block = buildBlock(template, context);
  cache[str] = Block;
  return Block;
}
function buildTree(node, parent = null, domParentTree = null) {
  switch (node.nodeType) {
    case Node.ELEMENT_NODE: {
      let currentNS = domParentTree && domParentTree.currentNS;
      const tagName = node.tagName;
      let el = void 0;
      const info = [];
      if (tagName.startsWith("block-text-")) {
        const index = parseInt(tagName.slice(11), 10);
        info.push({ type: "text", idx: index });
        el = document.createTextNode("");
      }
      if (tagName.startsWith("block-child-")) {
        if (!domParentTree.isRef) {
          addRef(domParentTree);
        }
        const index = parseInt(tagName.slice(12), 10);
        info.push({ type: "child", idx: index });
        el = document.createTextNode("");
      }
      currentNS ||= node.namespaceURI;
      if (!el) {
        el = currentNS ? document.createElementNS(currentNS, tagName) : document.createElement(tagName);
      }
      if (el instanceof Element) {
        if (!domParentTree) {
          const fragment = document.createElement("template").content;
          fragment.appendChild(el);
        }
        const attrs = node.attributes;
        for (let i = 0; i < attrs.length; i++) {
          const attrName = attrs[i].name;
          const attrValue = attrs[i].value;
          if (attrName.startsWith("block-handler-")) {
            const idx = parseInt(attrName.slice(14), 10);
            info.push({
              type: "handler",
              idx,
              event: attrValue
            });
          } else if (attrName.startsWith("block-attribute-")) {
            const idx = parseInt(attrName.slice(16), 10);
            info.push({
              type: "attribute",
              idx,
              name: attrValue
            });
          } else if (attrName.startsWith("block-property-")) {
            const idx = parseInt(attrName.slice(15), 10);
            info.push({
              type: "property",
              idx,
              name: attrValue
            });
          } else if (attrName === "block-attributes") {
            info.push({
              type: "attributes",
              idx: parseInt(attrValue, 10)
            });
          } else if (attrName === "block-ref") {
            info.push({
              type: "ref",
              idx: parseInt(attrValue, 10)
            });
          } else {
            const ns = attrs[i].namespaceURI;
            if (ns && ns !== XMLNS_URI) {
              el.setAttributeNS(ns, attrName, attrValue);
            } else {
              el.setAttribute(attrName, attrValue);
            }
          }
        }
        const classSources = info.filter(
          (i) => i.type === "attributes" || i.type === "attribute" && i.name === "class"
        );
        const staticClass = el.getAttribute("class")?.trim();
        if (classSources.length > 1 || classSources.length && staticClass) {
          const sharedClass = makeSharedClassUpdaters(staticClass ? staticClass.split(/\s+/) : []);
          for (const source of classSources) {
            source.sharedClass = sharedClass;
          }
        }
        const styleSources = info.filter(
          (i) => i.type === "attributes" || i.type === "attribute" && i.name === "style"
        );
        const staticStyle = el.getAttribute("style")?.trim();
        if (styleSources.length > 1 || styleSources.length && staticStyle) {
          const nextStyleSource = makeSharedStyleUpdaters(staticStyle || "");
          for (const source of styleSources) {
            source.sharedStyle = nextStyleSource();
          }
        }
      }
      const tree = {
        parent,
        firstChild: null,
        nextSibling: null,
        el,
        info,
        refN: 0,
        currentNS
      };
      if (node.firstChild) {
        const childNode = node.childNodes[0];
        if (node.childNodes.length === 1 && childNode.nodeType === Node.ELEMENT_NODE && childNode.tagName.startsWith("block-child-")) {
          const tagName2 = childNode.tagName;
          const index = parseInt(tagName2.slice(12), 10);
          info.push({ idx: index, type: "child", isOnlyChild: true });
        } else {
          tree.firstChild = buildTree(node.firstChild, tree, tree);
          el.appendChild(tree.firstChild.el);
          let curNode = node.firstChild;
          let curTree = tree.firstChild;
          while (curNode = curNode.nextSibling) {
            curTree.nextSibling = buildTree(curNode, curTree, tree);
            el.appendChild(curTree.nextSibling.el);
            curTree = curTree.nextSibling;
          }
        }
      }
      if (tree.info.length && !tree.isRef) {
        addRef(tree);
      }
      return tree;
    }
    case Node.TEXT_NODE: {
      return {
        parent,
        firstChild: null,
        nextSibling: null,
        el: document.createTextNode(node.textContent),
        info: [],
        refN: 0,
        currentNS: null
      };
    }
  }
  throw new OwlError("boom");
}
function addRef(tree) {
  tree.isRef = true;
  do {
    tree.refN++;
  } while (tree = tree.parent);
}
function parentTree(tree) {
  let parent = tree.parent;
  while (parent && parent.nextSibling === tree) {
    tree = parent;
    parent = parent.parent;
  }
  return parent;
}
function buildContext(tree, ctx, fromIdx) {
  if (!ctx) {
    ctx = { collectors: [], locations: [], children: [], cbRefs: [], refN: tree.refN };
    fromIdx = 0;
  }
  if (tree.refN) {
    const initialIdx = fromIdx;
    const isRef = tree.isRef;
    const firstChild = tree.firstChild ? tree.firstChild.refN : 0;
    const nextSibling = tree.nextSibling ? tree.nextSibling.refN : 0;
    if (isRef) {
      for (let info of tree.info) {
        info.refIdx = initialIdx;
      }
      tree.refIdx = initialIdx;
      updateCtx(ctx, tree);
      fromIdx++;
    }
    if (nextSibling) {
      const idx = fromIdx + firstChild;
      ctx.collectors.push({ idx, prevIdx: initialIdx, isFirstChild: false });
      buildContext(tree.nextSibling, ctx, idx);
    }
    if (firstChild) {
      ctx.collectors.push({ idx: fromIdx, prevIdx: initialIdx, isFirstChild: true });
      buildContext(tree.firstChild, ctx, fromIdx);
    }
  }
  return ctx;
}
function updateCtx(ctx, tree) {
  for (let info of tree.info) {
    switch (info.type) {
      case "text":
        ctx.locations.push({
          idx: info.idx,
          refIdx: info.refIdx,
          setData: setText,
          updateData: setText
        });
        break;
      case "child":
        if (info.isOnlyChild) {
          ctx.children[info.idx] = {
            parentRefIdx: info.refIdx,
            isOnlyChild: true
          };
        } else {
          ctx.children[info.idx] = {
            parentRefIdx: parentTree(tree).refIdx,
            afterRefIdx: info.refIdx
          };
        }
        break;
      case "property": {
        const refIdx = info.refIdx;
        const setProp = makePropSetter(info.name);
        ctx.locations.push({
          idx: info.idx,
          refIdx,
          setData: setProp,
          updateData: setProp
        });
        break;
      }
      case "attribute": {
        const refIdx = info.refIdx;
        let updater;
        let setter;
        if (info.sharedClass) {
          setter = updater = info.sharedClass;
        } else if (info.sharedStyle) {
          setter = updater = info.sharedStyle;
        } else if (info.name === "class") {
          setter = setClass;
          updater = updateClass;
        } else if (info.name === "style") {
          setter = setStyle;
          updater = updateStyle;
        } else {
          setter = createAttrUpdater(info.name);
          updater = setter;
        }
        ctx.locations.push({
          idx: info.idx,
          refIdx,
          setData: setter,
          updateData: updater
        });
        break;
      }
      case "attributes": {
        const { sharedClass, sharedStyle } = info;
        const shared = (sharedClass || sharedStyle) && makeAttrsUpdaters(sharedClass || updateClass, sharedStyle || updateStyle);
        ctx.locations.push({
          idx: info.idx,
          refIdx: info.refIdx,
          setData: shared ? shared.attrsSetter : attrsSetter,
          updateData: shared ? shared.attrsUpdater : attrsUpdater
        });
        break;
      }
      case "handler": {
        const { setup, update } = createEventHandler(info.event);
        ctx.locations.push({
          idx: info.idx,
          refIdx: info.refIdx,
          setData: setup,
          updateData: update
        });
        break;
      }
      case "ref": {
        ctx.locations.push({
          idx: info.idx,
          refIdx: info.refIdx,
          setData: NO_OP,
          updateData: updateRef
        });
        ctx.cbRefs.push(info.idx);
        break;
      }
    }
  }
}
function buildBlock(template, ctx) {
  let B = createBlockClass(template, ctx);
  if (ctx.children.length) {
    B = class extends B {
      children;
      constructor(data, children) {
        super(data);
        this.children = children;
      }
    };
    B.prototype.beforeRemove = VMulti.prototype.beforeRemove;
    return (data, children = []) => new B(data, children);
  }
  return (data) => new B(data);
}
function createBlockClass(template, ctx) {
  const { refN, collectors, children, locations, cbRefs } = ctx;
  locations.sort((a, b) => a.idx - b.idx);
  const locN = locations.length;
  const childN = children.length;
  const isDynamic = refN > 0;
  const locRefIdxs = locations.map((l) => l.refIdx);
  const locSetters = locations.map((l) => l.setData);
  const locUpdaters = locations.map((l) => l.updateData);
  const GETTERS = [nodeGetNextSibling, nodeGetFirstChild];
  const colN = collectors.length;
  const colPacked = collectors.map(
    (c) => c.idx & 32767 | (c.prevIdx & 32767) << 15 | (c.isFirstChild ? 1 : 0) << 30
  );
  const childInfos = children.map(
    (c) => c.parentRefIdx & 32767 | (c.isOnlyChild ? 1 : 0) << 15 | ((c.afterRefIdx ?? 0) & 32767) << 16
  );
  const nodeProto = Node.prototype;
  const nodeCloneNode = nodeProto.cloneNode;
  const nodeInsertBefore2 = nodeProto.insertBefore;
  const elementRemove = Element.prototype.remove;
  class Block {
    el;
    parentEl;
    data;
    children;
    refs;
    constructor(data) {
      this.data = data;
    }
    beforeRemove() {
    }
    remove() {
      elementRemove.call(this.el);
    }
    firstNode() {
      return this.el;
    }
    moveBeforeDOMNode(node) {
      nodeInsertBefore2.call(this.parentEl, this.el, node);
    }
    moveBeforeVNode(other, afterNode) {
      nodeInsertBefore2.call(this.parentEl, this.el, other ? other.el : afterNode);
    }
    toString() {
      const div = document.createElement("div");
      stringifying++;
      try {
        this.mount(div, null);
      } finally {
        stringifying--;
      }
      return div.innerHTML;
    }
    mount(parent, afterNode) {
      const el = nodeCloneNode.call(template, true);
      nodeInsertBefore2.call(parent, el, afterNode);
      this.el = el;
      this.parentEl = parent;
    }
    patch(other, withBeforeRemove) {
    }
  }
  if (isDynamic) {
    Block.prototype.mount = function mount3(parent, afterNode) {
      const el = nodeCloneNode.call(template, true);
      const refs = new Array(refN);
      this.refs = refs;
      refs[0] = el;
      for (let i = 0; i < colN; i++) {
        const packed = colPacked[i];
        refs[packed & 32767] = GETTERS[packed >> 30 & 1].call(refs[packed >> 15 & 32767]);
      }
      if (locN) {
        const data = this.data;
        for (let i = 0; i < locN; i++) {
          locSetters[i].call(refs[locRefIdxs[i]], data[i]);
        }
      }
      if (childN) {
        const children2 = this.children;
        for (let i = 0; i < childN; i++) {
          const child = children2[i];
          if (child) {
            const info = childInfos[i];
            const afterRefIdx = info >> 16 & 32767;
            const afterNode2 = afterRefIdx ? refs[afterRefIdx] : null;
            child.isOnlyChild = !!(info & 1 << 15);
            child.mount(refs[info & 32767], afterNode2);
          }
        }
      }
      nodeInsertBefore2.call(parent, el, afterNode);
      this.el = el;
      this.parentEl = parent;
      if (cbRefs.length && !stringifying) {
        const data = this.data;
        const refs2 = this.refs;
        for (let cbRef of cbRefs) {
          const fn = data[cbRef];
          fn(refs2[locRefIdxs[cbRef]], null);
        }
      }
    };
    Block.prototype.patch = function patch2(other, withBeforeRemove) {
      if (this === other) {
        return;
      }
      const refs = this.refs;
      if (locN) {
        const data1 = this.data;
        const data2 = other.data;
        for (let i = 0; i < locN; i++) {
          const val1 = data1[i];
          const val2 = data2[i];
          if (val1 !== val2) {
            locUpdaters[i].call(refs[locRefIdxs[i]], val2, val1);
          }
        }
        this.data = data2;
      }
      if (childN) {
        let children1 = this.children;
        const children2 = other.children;
        for (let i = 0; i < childN; i++) {
          const child1 = children1[i];
          const child2 = children2[i];
          if (child1) {
            if (child2) {
              child1.patch(child2, withBeforeRemove);
            } else {
              if (withBeforeRemove) {
                child1.beforeRemove();
              }
              child1.remove();
              children1[i] = void 0;
            }
          } else if (child2) {
            const info = childInfos[i];
            const afterRefIdx = info >> 16 & 32767;
            const afterNode = afterRefIdx ? refs[afterRefIdx] : null;
            child2.isOnlyChild = !!(info & 1 << 15);
            child2.mount(refs[info & 32767], afterNode);
            children1[i] = child2;
          }
        }
      }
    };
    Block.prototype.remove = function remove2() {
      elementRemove.call(this.el);
      if (cbRefs.length) {
        const data = this.data;
        const refs = this.refs;
        for (let cbRef of cbRefs) {
          const fn = data[cbRef];
          fn(null, refs[locRefIdxs[cbRef]]);
        }
      }
    };
  }
  return Block;
}
function updateRef(fn, oldFn) {
  oldFn(null, this);
  fn(this, null);
}
function setText(value) {
  characterDataSetData.call(this, toText(value));
}

// ../owl-runtime/src/blockdom/list.ts
var VList = class {
  children;
  anchor;
  parentEl;
  isOnlyChild;
  constructor(children) {
    this.children = children;
  }
  mount(parent, afterNode) {
    const children = this.children;
    const _anchor = document.createTextNode("");
    this.anchor = _anchor;
    nodeInsertBefore.call(parent, _anchor, afterNode);
    const l = children.length;
    if (l) {
      const mount3 = children[0].mount;
      for (let i = 0; i < l; i++) {
        mount3.call(children[i], parent, _anchor);
      }
    }
    this.parentEl = parent;
  }
  moveBeforeDOMNode(node) {
    const children = this.children;
    for (let i = 0, l = children.length; i < l; i++) {
      children[i].moveBeforeDOMNode(node);
    }
    nodeInsertBefore.call(this.parentEl, this.anchor, node);
  }
  moveBeforeVNode(other, afterNode) {
    if (other) {
      const next = other.children[0];
      afterNode = (next ? next.firstNode() : other.anchor) || null;
    }
    const children = this.children;
    for (let i = 0, l = children.length; i < l; i++) {
      children[i].moveBeforeVNode(null, afterNode);
    }
    nodeInsertBefore.call(this.parentEl, this.anchor, afterNode);
  }
  patch(other, withBeforeRemove) {
    if (this === other) {
      return;
    }
    const ch1 = this.children;
    const ch2 = other.children;
    if (ch2.length === 0 && ch1.length === 0) {
      return;
    }
    this.children = ch2;
    const proto = ch2[0] || ch1[0];
    const {
      mount: cMount,
      patch: cPatch,
      remove: cRemove,
      beforeRemove,
      moveBeforeVNode: cMoveBefore,
      firstNode: cFirstNode
    } = proto;
    const _anchor = this.anchor;
    const isOnlyChild = this.isOnlyChild;
    const parent = this.parentEl;
    if (ch2.length === 0 && isOnlyChild) {
      if (withBeforeRemove) {
        for (let i = 0, l = ch1.length; i < l; i++) {
          beforeRemove.call(ch1[i]);
        }
      }
      nodeSetTextContent.call(parent, "");
      releaseCatchers(parent);
      nodeAppendChild.call(parent, _anchor);
      return;
    }
    let startIdx1 = 0;
    let startIdx2 = 0;
    let startVn1 = ch1[0];
    let startVn2 = ch2[0];
    let endIdx1 = ch1.length - 1;
    let endIdx2 = ch2.length - 1;
    let endVn1 = ch1[endIdx1];
    let endVn2 = ch2[endIdx2];
    let mapping = void 0;
    while (startIdx1 <= endIdx1 && startIdx2 <= endIdx2) {
      if (startVn1 === null) {
        startVn1 = ch1[++startIdx1];
        continue;
      }
      if (endVn1 === null) {
        endVn1 = ch1[--endIdx1];
        continue;
      }
      let startKey1 = startVn1.key;
      let startKey2 = startVn2.key;
      if (startKey1 === startKey2) {
        cPatch.call(startVn1, startVn2, withBeforeRemove);
        ch2[startIdx2] = startVn1;
        startVn1 = ch1[++startIdx1];
        startVn2 = ch2[++startIdx2];
        continue;
      }
      let endKey1 = endVn1.key;
      let endKey2 = endVn2.key;
      if (endKey1 === endKey2) {
        cPatch.call(endVn1, endVn2, withBeforeRemove);
        ch2[endIdx2] = endVn1;
        endVn1 = ch1[--endIdx1];
        endVn2 = ch2[--endIdx2];
        continue;
      }
      if (startKey1 === endKey2) {
        cPatch.call(startVn1, endVn2, withBeforeRemove);
        ch2[endIdx2] = startVn1;
        const nextChild = ch2[endIdx2 + 1];
        cMoveBefore.call(startVn1, nextChild, _anchor);
        startVn1 = ch1[++startIdx1];
        endVn2 = ch2[--endIdx2];
        continue;
      }
      if (endKey1 === startKey2) {
        cPatch.call(endVn1, startVn2, withBeforeRemove);
        ch2[startIdx2] = endVn1;
        const nextChild = ch1[startIdx1];
        cMoveBefore.call(endVn1, nextChild, _anchor);
        endVn1 = ch1[--endIdx1];
        startVn2 = ch2[++startIdx2];
        continue;
      }
      mapping = mapping || createMapping(ch1, startIdx1, endIdx1);
      let idxInOld = mapping.get(startKey2);
      if (idxInOld === void 0 || idxInOld < startIdx1 || idxInOld > endIdx1 || ch1[idxInOld] === null) {
        cMount.call(startVn2, parent, cFirstNode.call(startVn1) || null);
      } else {
        const elmToMove = ch1[idxInOld];
        cMoveBefore.call(elmToMove, startVn1, null);
        cPatch.call(elmToMove, startVn2, withBeforeRemove);
        ch2[startIdx2] = elmToMove;
        ch1[idxInOld] = null;
      }
      startVn2 = ch2[++startIdx2];
    }
    if (startIdx1 <= endIdx1 || startIdx2 <= endIdx2) {
      if (startIdx1 > endIdx1) {
        const nextChild = ch2[endIdx2 + 1];
        const anchor = nextChild ? cFirstNode.call(nextChild) || null : _anchor;
        for (let i = startIdx2; i <= endIdx2; i++) {
          cMount.call(ch2[i], parent, anchor);
        }
      } else {
        for (let i = startIdx1; i <= endIdx1; i++) {
          let ch = ch1[i];
          if (ch) {
            if (withBeforeRemove) {
              beforeRemove.call(ch);
            }
            cRemove.call(ch);
          }
        }
      }
    }
  }
  beforeRemove() {
    const children = this.children;
    const l = children.length;
    if (l) {
      const beforeRemove = children[0].beforeRemove;
      for (let i = 0; i < l; i++) {
        beforeRemove.call(children[i]);
      }
    }
  }
  remove() {
    const { parentEl, anchor } = this;
    if (this.isOnlyChild) {
      nodeSetTextContent.call(parentEl, "");
      releaseCatchers(parentEl);
    } else {
      const children = this.children;
      const l = children.length;
      if (l) {
        const remove2 = children[0].remove;
        for (let i = 0; i < l; i++) {
          remove2.call(children[i]);
        }
      }
      nodeRemoveChild.call(parentEl, anchor);
    }
  }
  firstNode() {
    const child = this.children[0];
    return child ? child.firstNode() : this.anchor;
  }
  toString() {
    return this.children.map((c) => c.toString()).join("");
  }
};
function list(children) {
  return new VList(children);
}
function createMapping(ch1, startIdx1, endIdx1) {
  const mapping = /* @__PURE__ */ new Map();
  for (let i = startIdx1; i <= endIdx1; i++) {
    mapping.set(ch1[i].key, i);
  }
  return mapping;
}

// ../owl-runtime/src/blockdom/html.ts
var VHtml = class {
  html;
  parentEl;
  content = [];
  constructor(html2) {
    this.html = String(html2);
  }
  mount(parent, afterNode) {
    this.parentEl = parent;
    const template = document.createElement("template");
    template.innerHTML = this.html;
    this.content = [...template.content.childNodes];
    for (let elem of this.content) {
      nodeInsertBefore.call(parent, elem, afterNode);
    }
    if (!this.content.length) {
      const textNode = document.createTextNode("");
      this.content.push(textNode);
      nodeInsertBefore.call(parent, textNode, afterNode);
    }
  }
  moveBeforeDOMNode(node) {
    const parent = this.parentEl;
    for (let elem of this.content) {
      nodeInsertBefore.call(parent, elem, node);
    }
  }
  moveBeforeVNode(other, afterNode) {
    const target = other ? other.content[0] : afterNode;
    this.moveBeforeDOMNode(target);
  }
  patch(other) {
    if (this === other) {
      return;
    }
    const html2 = other.html;
    if (this.html !== html2) {
      const parent = this.parentEl;
      const afterNode = this.content[0];
      const template = document.createElement("template");
      template.innerHTML = html2;
      const content = [...template.content.childNodes];
      for (let elem of content) {
        nodeInsertBefore.call(parent, elem, afterNode);
      }
      if (!content.length) {
        const textNode = document.createTextNode("");
        content.push(textNode);
        nodeInsertBefore.call(parent, textNode, afterNode);
      }
      this.remove();
      this.content = content;
      this.html = other.html;
    }
  }
  beforeRemove() {
  }
  remove() {
    const parent = this.parentEl;
    for (let elem of this.content) {
      nodeRemoveChild.call(parent, elem);
    }
  }
  firstNode() {
    return this.content[0];
  }
  toString() {
    return this.html;
  }
};
function html(str) {
  return new VHtml(str);
}

// ../owl-runtime/src/blockdom/index.ts
function mount(vnode, fixture, afterNode = null) {
  vnode.mount(fixture, afterNode);
}
function patch(vnode1, vnode2, withBeforeRemove = false) {
  vnode1.patch(vnode2, withBeforeRemove);
}
function remove(vnode, withBeforeRemove = false) {
  if (withBeforeRemove) {
    vnode.beforeRemove();
  }
  vnode.remove();
}

// ../owl-runtime/src/rendering/memo.ts
var collected = null;
function memoPrevious(node, site) {
  return node.previousMemos?.get(site);
}
function memoKeep(node, site, entries) {
  (node.memos ??= /* @__PURE__ */ new Map()).set(site, entries);
  if (collected !== null) {
    collected.sites.push(site);
  }
}
function memoHit(previous, key, deps, node) {
  if (!Array.isArray(deps)) {
    throw new OwlError(`t-memo expects an array of dependencies, got ${typeof deps}`);
  }
  const entry = previous?.get(key);
  if (entry === void 0) {
    return void 0;
  }
  const previousDeps = entry.deps;
  const length = deps.length;
  if (previousDeps.length !== length) {
    return void 0;
  }
  for (let i = 0; i < length; i++) {
    if (!Object.is(previousDeps[i], deps[i])) {
      return void 0;
    }
  }
  const content = entry.content;
  if (content !== null) {
    const committed = node.childMap;
    const children = content.children;
    for (const childKey of children) {
      const child = committed?.get(childKey);
      if (child === void 0 || child.status !== STATUS.MOUNTED || child.forceNextRender) {
        return void 0;
      }
    }
    if (children.length) {
      const childrenMap = node.fiber.childrenMap ||= /* @__PURE__ */ new Map();
      for (const childKey of children) {
        childrenMap.set(childKey, committed.get(childKey));
      }
    }
    const previousSites = node.previousMemos;
    for (const site of content.sites) {
      const entries = previousSites?.get(site);
      if (entries !== void 0) {
        (node.memos ??= /* @__PURE__ */ new Map()).set(site, entries);
      }
    }
    if (collected !== null) {
      collected.children.push(...children);
      collected.sites.push(...content.sites);
    }
  }
  return entry;
}
function memoBegin() {
  const outer = collected;
  collected = { children: [], sites: [] };
  return outer;
}
function memoEnd(outer) {
  const content = collected;
  collected = outer;
  if (outer !== null) {
    outer.children.push(...content.children);
    outer.sites.push(...content.sites);
  }
  return content;
}
function memoCollectChild(key) {
  if (collected !== null) {
    collected.children.push(key);
  }
}
function memoSuspend() {
  const outer = collected;
  collected = null;
  return outer;
}
function memoResume(outer) {
  collected = outer;
}

// ../owl-runtime/src/rendering/scheduler.ts
var requestAnimationFrame;
if (typeof window !== "undefined") {
  requestAnimationFrame = window.requestAnimationFrame.bind(window);
}
var Scheduler = class _Scheduler {
  // capture the value of requestAnimationFrame as soon as possible, to avoid
  // interactions with other code, such as test frameworks that override them
  static requestAnimationFrame = requestAnimationFrame;
  // the schedulers that may hold a task: a node's ancestor may belong to
  // another app, whose render then delays it
  static active = /* @__PURE__ */ new Set();
  tasks = /* @__PURE__ */ new Set();
  requestAnimationFrame;
  frame = 0;
  delayedRenders = [];
  processing = false;
  constructor() {
    this.requestAnimationFrame = _Scheduler.requestAnimationFrame;
  }
  addFiber(fiber) {
    if (debug.scheduler) {
      debugLog(
        "scheduler",
        `schedule ${fiber.root.node.componentName}, ${this.tasks.size + 1} task(s)`
      );
    }
    this.tasks.add(fiber.root);
    _Scheduler.active.add(this);
  }
  /**
   * Process all current tasks. This only applies to the fibers that are ready.
   * Other tasks are left unchanged.
   */
  flush() {
    if (this.delayedRenders.length) {
      let renders = this.delayedRenders;
      this.delayedRenders = [];
      if (debug.scheduler) {
        debugLog(
          "scheduler",
          `resume ${renders.length} delayed render(s)`,
          renders.map((f) => f.node.componentName)
        );
      }
      for (let f of renders) {
        if (f.root && f.node.status !== STATUS.DESTROYED && f.node.fiber === f) {
          f.render();
        }
      }
    }
    this.requestFrame();
  }
  requestFrame() {
    if (this.frame === 0) {
      this.frame = this.requestAnimationFrame(() => this.processTasks());
    }
  }
  processTasks() {
    if (this.processing) {
      return;
    }
    this.processing = true;
    this.frame = 0;
    let failed = false;
    if (debug.scheduler) {
      debugLog("scheduler", `frame, ${this.tasks.size} task(s)`);
    }
    for (let fiber of this.tasks) {
      if (fiber.root !== fiber) {
        this.tasks.delete(fiber);
        continue;
      }
      if (fiber.node.fiber !== fiber) {
        if (debug.scheduler) {
          debugLog("scheduler", `drop ${fiber.node.componentName}: superseded`);
        }
        this.tasks.delete(fiber);
        continue;
      }
      if (fibersInError.has(fiber)) {
        if (debug.scheduler) {
          debugLog("scheduler", `drop ${fiber.node.componentName}: failed`);
        }
        this.tasks.delete(fiber);
        failed = true;
        continue;
      }
      if (fiber.node.status === STATUS.DESTROYED) {
        if (debug.scheduler) {
          debugLog("scheduler", `drop ${fiber.node.componentName}: destroyed`);
        }
        this.tasks.delete(fiber);
        continue;
      }
      if (debug.scheduler && fiber.counter !== 0) {
        debugLog(
          "scheduler",
          `wait ${fiber.node.componentName}: ${fiber.counter} render(s) pending`
        );
      }
      if (fiber.counter === 0) {
        fiber.complete();
        if (fiber.renderState & APPLIED_TO_DOM) {
          this.tasks.delete(fiber);
        }
      }
    }
    for (let task of this.tasks) {
      if (task.node.status === STATUS.DESTROYED) {
        this.tasks.delete(task);
      }
    }
    if (failed) {
      this.flush();
    }
    if (!this.tasks.size) {
      _Scheduler.active.delete(this);
    }
    this.processing = false;
  }
};

// ../owl-runtime/src/rendering/fibers.ts
var MAX_RENDER_ITERATIONS = 1e3;
var APPLIED_TO_DOM = 1;
function makeChildFiber(node, parent) {
  let current = node.fiber;
  if (current) {
    cancelFibers(current.children);
    current.root = null;
  }
  return new Fiber2(node, parent);
}
function makeRootFiber(node) {
  let current = node.fiber;
  if (current) {
    let root = current.root;
    current.renderState += 2;
    if (debug.fiber) {
      debugLog(
        "fiber",
        `re-render ${node.componentName} before its commit (recycle ${current.renderState >> 1})`
      );
    }
    root.locked = true;
    const rendered = current.phase === 0 /* NEW */ ? 0 : 1;
    root.setCounter(root.counter + rendered - cancelFibers(current.children));
    root.locked = false;
    current.children = [];
    current.childrenMap = null;
    current.bdom = null;
    current.phase = 0 /* NEW */;
    if (root instanceof MountFiber && root.prepared) {
      root.prepared = false;
      root.renderState &= ~APPLIED_TO_DOM;
    }
    if (fibersInError.has(current)) {
      fibersInError.delete(current);
      let failedElsewhere = false;
      const failed = root.failed;
      if (failed) {
        failed.delete(current);
        for (const fiber2 of failed) {
          if (fiber2.node.fiber === fiber2) {
            failedElsewhere = true;
            break;
          }
        }
      }
      if (!failedElsewhere) {
        fibersInError.delete(root);
        root.failed = null;
      }
      current.renderState &= ~APPLIED_TO_DOM;
      if (current instanceof RootFiber2) {
        current.mounted = current instanceof MountFiber ? [current] : [];
      }
    }
    return current;
  }
  const fiber = new RootFiber2(node, null);
  if (node.willPatch.length) {
    fiber.willPatch.push(fiber);
  }
  if (node.patched.length) {
    fiber.patched.push(fiber);
  }
  return fiber;
}
function throwOnRender() {
  throw new OwlError("Attempted to render cancelled fiber");
}
var subRootHosts = /* @__PURE__ */ new WeakMap();
function above(node) {
  return node.parent || (node.status === STATUS.MOUNTED ? subRootHosts.get(node) || null : null);
}
function cancelFibers(fibers) {
  let result = 0;
  for (let fiber of fibers) {
    let node = fiber.node;
    fiber.render = throwOnRender;
    if (node.status === STATUS.NEW) {
      node.cancel();
    }
    node.fiber = null;
    if (fiber.phase !== 0 /* NEW */) {
      node.forceNextRender = true;
    } else {
      result++;
      if (node.bdom) {
        node.forceNextRender = true;
      }
    }
    result += cancelFibers(fiber.children);
  }
  return result;
}
var Fiber2 = class {
  node;
  bdom = null;
  root;
  // A Fiber that has been replaced by another has no root
  parent;
  children = [];
  // Packs the "applied to DOM" flag (bit 0, see APPLIED_TO_DOM) together with
  // the number of times this uncommitted fiber has been recycled by
  // makeRootFiber (bits 1 and up). The recycle count climbs without bound only
  // in a render loop (#1968); it shares a slot with the flag so the many
  // fibers that are never recycled don't pay for a dedicated field.
  renderState = 0;
  deep = false;
  phase = 0 /* NEW */;
  childrenMap = null;
  constructor(node, parent) {
    this.node = node;
    this.parent = parent;
    if (parent) {
      this.deep = parent.deep;
      const root = parent.root;
      root.setCounter(root.counter + 1);
      this.root = root;
      parent.children.push(this);
    } else {
      this.root = this;
    }
  }
  render() {
    const scheduler = this.root.node.app.scheduler;
    if (scheduler.tasks.size > 1 || Scheduler.active.size > 1) {
      let prev = this.root.node;
      let current = above(prev);
      while (current) {
        if (current.fiber) {
          let root2 = current.fiber.root;
          if ((root2.counter === 0 || fibersInError.has(root2)) && (!prev.parent || !!current.fiber.childrenMap?.has(prev.parentKey))) {
            current = root2.node;
          } else {
            if (debug.fiber) {
              debugLog(
                "fiber",
                `delay ${this.node.componentName}: ${root2.node.componentName} is rendering`
              );
            }
            root2.node.app.scheduler.delayedRenders.push(this);
            return;
          }
        }
        prev = current;
        current = above(current);
      }
    }
    const node = this.node;
    const root = this.root;
    if (root) {
      if (this.renderState >> 1 > MAX_RENDER_ITERATIONS) {
        handleError({
          node,
          error: new OwlError(
            `Maximum render iterations (${MAX_RENDER_ITERATIONS}) exceeded. Component "${node.componentName}" is stuck in a render loop: rendering it keeps triggering another render before the DOM is updated. A common cause is updating reactive state during render or setup() \u2014 e.g. calling a parent's state setter from a child's setup().`
          )
        });
        return;
      }
      node.signalComputation.state = ComputationState.EXECUTED;
      node.previousMemos = node.memos;
      node.memos = null;
      const outerCollection = memoSuspend();
      this.phase = 1 /* RENDERING */;
      const start = debug.fiber ? debugNow() : -1;
      this.bdom = runTracked(node.signalComputation, () => {
        try {
          return node.renderFn();
        } catch (e) {
          handleError({ node, error: e });
          return null;
        } finally {
          this.phase = 2 /* RENDERED */;
          memoResume(outerCollection);
        }
      });
      const newCounter = root.counter - 1;
      root.counter = newCounter;
      if (debug.fiber) {
        debugLog(
          "fiber",
          `render ${node.componentName}${start < 0 ? "" : ` in ${(debugNow() - start).toFixed(2)} ms`}, ${newCounter} left in ${root.node.componentName}'s pass`
        );
      }
      if (newCounter === 0) {
        if (fibersInError.has(root)) {
          scheduler.requestFrame();
        } else {
          scheduler.flush();
        }
      }
    }
  }
};
var RootFiber2 = class extends Fiber2 {
  counter = 1;
  // the fibers of this pass whose render, onWillStart or onWillUpdateProps
  // failed: the pass stays failed until none of them is current
  failed = null;
  // only add stuff in this if they have registered some hooks
  willPatch = [];
  patched = [];
  mounted = [];
  // A fiber is typically locked when it is completing and the patch has not, or is being applied.
  // i.e.: render triggered in onWillUnmount or in willPatch will be delayed
  locked = false;
  complete() {
    const node = this.node;
    this.locked = true;
    let current = void 0;
    if (debug.fiber) {
      debugLog(
        "fiber",
        `commit ${node.componentName}: ${this.willPatch.length} willPatch, ${this.mounted.length} mounted, ${this.patched.length} patched`
      );
    }
    try {
      for (current of this.willPatch) {
        let node2 = current.node;
        if (node2.fiber === current) {
          const component = node2.component;
          for (let cb of node2.willPatch) {
            cb.call(component);
          }
        }
      }
      current = void 0;
      node._patch();
      this.locked = false;
    } catch (e) {
      for (let fiber of this.mounted) {
        fiber.node.willUnmount = [];
      }
      this.locked = false;
      handleError({ fiber: current || this, error: e });
      return;
    }
    const failed = callCommitHooks(this.mounted, "mounted");
    if (failed !== null) {
      callCommitHooks(this.patched, "patched", failed);
    }
  }
  setCounter(newValue) {
    this.counter = newValue;
    if (newValue === 0) {
      this.node.app.scheduler.flush();
    }
  }
};
var deferredWillUnmount = /* @__PURE__ */ new WeakMap();
function callCommitHooks(fibers, hook, failed = false) {
  const mounting = hook === "mounted";
  let skipped2 = failed ? [] : null;
  let current;
  while (current = fibers.pop()) {
    const node = current.node;
    if (skipped2 && (!(current.renderState & APPLIED_TO_DOM) || fibersInError.has(current))) {
      if (mounting && node.willUnmount.length) {
        deferredWillUnmount.set(node, node.willUnmount);
        node.willUnmount = [];
      }
      skipped2.push(current);
      continue;
    }
    if (!(current.renderState & APPLIED_TO_DOM) || node.status === STATUS.DESTROYED) {
      continue;
    }
    if (mounting) {
      const deferred = deferredWillUnmount.get(node);
      if (deferred) {
        deferredWillUnmount.delete(node);
        node.willUnmount = deferred;
      }
    }
    if (debug.lifecycle && node[hook].length) {
      debugLog("lifecycle", `${hook} ${node.componentName}: ${node[hook].length} hook(s)`);
    }
    try {
      for (let cb of node[hook]) {
        cb();
      }
    } catch (e) {
      skipped2 ||= [];
      const waiting = mounting ? fibers.slice() : [];
      const willUnmount = waiting.map((fiber) => fiber.node.willUnmount);
      for (let fiber of waiting) {
        fiber.node.willUnmount = [];
      }
      handleError({ fiber: current, error: e });
      if (node.app.destroyed) {
        return null;
      }
      for (let i = 0; i < waiting.length; i++) {
        waiting[i].node.willUnmount = willUnmount[i];
      }
    }
  }
  if (!skipped2) {
    return false;
  }
  for (let i = skipped2.length - 1; i >= 0; i--) {
    fibers.push(skipped2[i]);
  }
  return true;
}
var MountFiber = class extends RootFiber2 {
  target;
  position;
  afterNode = null;
  allowDetached = false;
  // true once the render phase finishes (counter reaches 0), false again if
  // the root re-renders before its commit. If target is set at that point, we
  // mount immediately; otherwise we signal readiness via onPrepared and wait
  // for commit() to supply a target.
  prepared = false;
  onPrepared = null;
  constructor(node, target, options = {}) {
    super(node, null);
    this.target = target;
    this.position = options.position || "last-child";
    this.afterNode = options.afterNode ?? null;
    this.allowDetached = options.allowDetached ?? false;
  }
  complete() {
    this.prepared = true;
    if (this.target) {
      this._mount();
    } else {
      this.renderState |= APPLIED_TO_DOM;
      this.onPrepared?.();
    }
  }
  commit(target, options = {}) {
    this.target = target;
    this.position = options.position || "last-child";
    this.afterNode = options.afterNode ?? null;
    this.allowDetached = options.allowDetached ?? false;
    if (this.prepared) {
      this._mount();
    }
  }
  _mount() {
    let current = this;
    if (debug.fiber) {
      debugLog("fiber", `mount ${this.node.componentName}`, this.target);
    }
    try {
      const node = this.node;
      node.childMap = this.childrenMap;
      node.app.constructor.validateTarget(this.target, {
        attached: !this.allowDetached
      });
      if (node.bdom) {
        node.updateDom();
      } else {
        node.bdom = this.bdom;
        if (this.afterNode) {
          mount(node.bdom, this.target, this.afterNode);
        } else if (this.position === "last-child" || this.target.childNodes.length === 0) {
          mount(node.bdom, this.target);
        } else {
          const firstChild = this.target.childNodes[0];
          mount(node.bdom, this.target, firstChild);
        }
      }
      node.fiber = null;
      node.status = STATUS.MOUNTED;
      this.renderState |= APPLIED_TO_DOM;
    } catch (e) {
      handleError({ fiber: current, error: e });
      return;
    }
    callCommitHooks(this.mounted, "mounted");
  }
};

// ../owl-runtime/src/component_node.ts
var NO_HOOKS = Object.freeze([]);
var ComponentNode = class extends Scope {
  fiber = null;
  component;
  bdom = null;
  componentName;
  forceNextRender = false;
  parentKey;
  props;
  defaultProps = null;
  // an own function, callable unbound: Odoo's onWillRender / onRendered
  // (web/core/utils/render_hooks.js) and HOOT wrap it during setup and call the
  // saved original without `this`
  renderFn;
  parent;
  // the child nodes by key, null until the first one. A Map rather than an
  // object: a key is a string built by the render, and a new key on an object
  // is interned in the engine's string table, several times the cost of a Map
  // entry
  childMap = null;
  willUpdateProps = NO_HOOKS;
  // Fired right after `props` is applied to `node.props` on a parent re-render,
  // so reactive prop notifications happen once the new values are observable
  // (after user `onWillUpdateProps` hooks, including async ones, have run).
  propsUpdated = NO_HOOKS;
  willUnmount = NO_HOOKS;
  mounted = NO_HOOKS;
  willPatch = NO_HOOKS;
  patched = NO_HOOKS;
  signalComputation;
  // t-refs bound to an element hosted by this component: a signal mapped to its
  // atom (so the element can be read without subscribing), a set-like ref to
  // the elements this component added to it. Swept by isConnected after each
  // patch and after this subtree is removed, to unbind a ref from a
  // bulk-removed element (slot host, enclosing t-if, cleared list) — see
  // sweepRefs.
  trackedRefs = null;
  refCallbacks = null;
  // the t-memo sites of the render in progress, and of the render before it: a
  // site the current render does not reach is dropped with the previous one
  memos = null;
  previousMemos = null;
  constructor(C, props2, app, parent, parentKey) {
    super(app);
    this.parent = parent;
    this.parentKey = parentKey;
    this.pluginManager = parent ? parent.pluginManager : app.pluginManager;
    this.componentName = C.name;
    this.signalComputation = createComputation(
      () => this.render(false),
      false,
      ComputationState.EXECUTED,
      false,
      // a string per component: built only while its name can be logged
      debug.reactivity || debug.effect ? `render ${C.name}` : ""
    );
    this.signalComputation.tracksElsewhere = true;
    if (debug.lifecycle) {
      debugLog(
        "lifecycle",
        `setup ${C.name}${parent ? ` (child of ${parent.componentName})` : " (root)"}`
      );
    }
    this.props = props2;
    const previousComputation = getCurrentComputation();
    setComputation(void 0);
    scopeStack.push(this);
    this.collectingWillStart = true;
    try {
      const component = new C(this);
      this.component = component;
      this.renderFn = app.getTemplate(C.template).bind(component, { this: component, __owl__: this }, this);
      component.setup();
    } catch (e) {
      this.finalize((cleanupError) => console.error(cleanupError));
      disposeComputation(this.signalComputation);
      throw e;
    } finally {
      this.collectingWillStart = false;
      scopeStack.pop();
      setComputation(previousComputation);
    }
  }
  /**
   * The child nodes by key, as a new plain object.
   */
  get children() {
    return this.childMap ? Object.fromEntries(this.childMap) : {};
  }
  /**
   * Registers a lifecycle callback, last (or first, for the hooks that run in
   * reverse registration order).
   */
  addHook(kind, fn, first = false) {
    const hooks = this[kind];
    if (hooks === NO_HOOKS) {
      this[kind] = [fn];
    } else if (first) {
      hooks.unshift(fn);
    } else {
      hooks.push(fn);
    }
  }
  decorate(f, hookName) {
    const component = this.component;
    const scope = this;
    if (this.app.dev) {
      const name = `${this.componentName}.${hookName}`;
      const wrapper = {
        [name](...args) {
          return f.call(component, scope, ...args);
        }
      };
      return wrapper[name];
    }
    return f.bind(component, scope);
  }
  async initiateRender(fiber) {
    this.fiber = fiber;
    if (this.mounted.length) {
      fiber.root.mounted.push(fiber);
    }
    const component = this.component;
    if (debug.lifecycle) {
      debugLog("lifecycle", `willStart ${this.componentName}: ${this.willStart.length} hook(s)`);
    }
    try {
      await Promise.all(untrack(() => this.willStart.map((f) => f.call(component))));
    } catch (e) {
      handleHookRejection(this, e);
      return;
    }
    if (debug.lifecycle) {
      debugLog("lifecycle", `willStart ${this.componentName} settled`);
    }
    if (this.status === STATUS.NEW && this.fiber === fiber) {
      fiber.render();
    }
  }
  async render(deep) {
    if (this.status >= STATUS.DESTROYED) {
      return;
    }
    let current = this.fiber;
    if (current && (current.root.locked || current.phase === 1 /* RENDERING */)) {
      await Promise.resolve();
      current = this.fiber;
    }
    if (current) {
      if (current.phase === 0 /* NEW */ && !fibersInError.has(current)) {
        if (deep) {
          current.deep = deep;
        }
        return;
      }
      deep = deep || current.deep;
    } else if (!this.bdom) {
      return;
    }
    const fiber = makeRootFiber(this);
    fiber.deep = deep;
    this.fiber = fiber;
    this.app.scheduler.addFiber(fiber);
    await Promise.resolve();
    if (this.status >= STATUS.DESTROYED) {
      return;
    }
    if (this.fiber === fiber && (current || !fiber.parent)) {
      fiber.render();
    }
  }
  cancel() {
    this.parent.childMap?.delete(this.parentKey);
    this._destroy();
  }
  destroy() {
    let shouldRemove = this.status === STATUS.MOUNTED;
    removalDepth++;
    try {
      this._destroy();
    } finally {
      removalDepth--;
      if (shouldRemove) {
        this.bdom.remove();
        sweepRemovedRefs();
      }
    }
  }
  _destroy() {
    const component = this.component;
    let failure = null;
    if (debug.lifecycle) {
      debugLog(
        "lifecycle",
        `destroy ${this.componentName}${this.status === STATUS.MOUNTED ? `, ${this.willUnmount.length} willUnmount` : " (never mounted)"}`
      );
    }
    if (this.status === STATUS.MOUNTED) {
      for (let cb of this.willUnmount) {
        try {
          cb.call(component);
        } catch (error) {
          failure ||= { error };
        }
      }
    }
    if (removalDepth && this.trackedRefs) {
      (removed ||= []).push(this);
    }
    for (const child of this.childMap?.values() || []) {
      try {
        child._destroy();
      } catch (error) {
        failure ||= { error };
      }
    }
    this.finalize((e) => {
      try {
        handleError({ error: e, node: this });
      } catch (error) {
        failure ||= { error };
      }
    });
    disposeComputation(this.signalComputation);
    if (failure) {
      throw failure.error;
    }
  }
  /**
   * Unbind any tracked t-ref from the elements no longer in the document, and
   * stop tracking what is left unbound (its ref callback re-registers it when it
   * binds an element again). `isConnected` is the discriminator: a ref the
   * block's own remove() failed to unbind (bulk removal) points at a detached
   * element and is unbound, while a ref a surviving sibling just took over
   * (t-if/t-else with a shared signal) points at a still-connected element and
   * is left alone.
   *
   * Called after this component's dom settles: at the tail of `_patch` (before
   * user `onPatched`), so an element removed in place is caught, and — for the
   * nodes collected during `_destroy` — after a removed subtree is detached.
   */
  sweepRefs() {
    const refs = this.trackedRefs;
    if (!refs) {
      return;
    }
    for (const [ref2, tracked] of refs) {
      if (tracked instanceof Set) {
        for (const el2 of tracked) {
          if (!el2.isConnected) {
            ref2.delete(el2);
            tracked.delete(el2);
          }
        }
        if (!tracked.size) {
          refs.delete(ref2);
        }
        continue;
      }
      const el = tracked.value;
      if (!el) {
        refs.delete(ref2);
      } else if (!el.isConnected) {
        ref2.set(null);
        refs.delete(ref2);
      }
    }
  }
  /**
   * Finds a child that has dom that is not yet updated, and update it. This
   * method is meant to be used only in the context of repatching the dom after
   * a mounted hook failed and was handled.
   */
  updateDom() {
    if (!this.fiber) {
      return;
    }
    if (this.bdom === this.fiber.bdom) {
      for (const child of this.childMap?.values() || []) {
        child.updateDom();
      }
      this.fiber = null;
    } else {
      this.childMap = this.fiber.childrenMap;
      removalDepth++;
      try {
        this.bdom.patch(this.fiber.bdom, true);
      } finally {
        removalDepth--;
      }
      this.sweepRefs();
      sweepRemovedRefs();
      this.fiber.renderState |= APPLIED_TO_DOM;
      this.fiber = null;
    }
  }
  // ---------------------------------------------------------------------------
  // Block DOM methods
  // ---------------------------------------------------------------------------
  firstNode() {
    const bdom2 = this.bdom;
    return bdom2 ? bdom2.firstNode() : void 0;
  }
  mount(parent, anchor) {
    const bdom2 = this.fiber.bdom;
    this.bdom = bdom2;
    bdom2.mount(parent, anchor);
    this.status = STATUS.MOUNTED;
    this.fiber.renderState |= APPLIED_TO_DOM;
    this.childMap = this.fiber.childrenMap;
    this.fiber = null;
  }
  moveBeforeDOMNode(node) {
    this.bdom.moveBeforeDOMNode(node);
  }
  moveBeforeVNode(other, afterNode) {
    this.bdom.moveBeforeVNode(other ? other.bdom : null, afterNode);
  }
  /**
   * Register a t-ref signal bound to an element this component hosts, so its
   * lifecycle can clear it (see sweepRefs / _destroy). Called each time the ref
   * binds an element; idempotent.
   */
  trackRef(ref2, atom) {
    (this.trackedRefs ||= /* @__PURE__ */ new Map()).set(ref2, atom);
  }
  /**
   * Register an element this component added to a set-like t-ref, or forget it
   * once its block removed it from the ref (`bound` false).
   */
  trackRefElement(ref2, el, bound) {
    const refs = this.trackedRefs ||= /* @__PURE__ */ new Map();
    let els = refs.get(ref2);
    if (bound) {
      if (!els) {
        refs.set(ref2, els = /* @__PURE__ */ new Set());
      }
      els.add(el);
    } else if (els) {
      els.delete(el);
    }
  }
  patch() {
    if (this.fiber && this.fiber.parent) {
      this._patch();
    }
  }
  _patch() {
    const hasChildren = !!this.childMap?.size;
    const fiber = this.fiber;
    this.childMap = fiber.childrenMap;
    removalDepth++;
    try {
      this.bdom.patch(fiber.bdom, hasChildren);
    } finally {
      removalDepth--;
    }
    this.sweepRefs();
    sweepRemovedRefs();
    fiber.renderState |= APPLIED_TO_DOM;
    this.fiber = null;
  }
  beforeRemove() {
    this._destroy();
  }
  remove() {
    this.bdom.remove();
  }
};
var removalDepth = 0;
var removed = null;
function sweepRemovedRefs() {
  if (removalDepth === 0 && removed) {
    const nodes = removed;
    removed = null;
    for (let i = 0; i < nodes.length; i++) {
      nodes[i].sweepRefs();
    }
  }
}
function getComponentScope() {
  const scope = useScope();
  if (!(scope instanceof ComponentNode)) {
    throw new OwlError("Expected to be in a component scope");
  }
  return scope;
}

// ../owl-runtime/src/component.ts
var Component = class {
  static template = "";
  __owl__;
  constructor(node) {
    this.__owl__ = node;
  }
  setup() {
  }
};

// ../owl-runtime/src/utils.ts
function isAttachedToDocument(element, documentElement) {
  let current = element;
  const shadowRoot = documentElement.defaultView.ShadowRoot;
  while (current) {
    if (current === documentElement) {
      return true;
    }
    if (current.parentNode) {
      current = current.parentNode;
    } else if (current instanceof shadowRoot && current.host) {
      current = current.host;
    } else {
      return false;
    }
  }
  return false;
}
function validateTarget(target, { attached = true } = {}) {
  const document2 = target && target.ownerDocument;
  if (document2) {
    if (!document2.defaultView) {
      throw new OwlError(
        "Cannot mount a component: the target document is not attached to a window (defaultView is missing)"
      );
    }
    const { HTMLElement: HTMLElement2, ShadowRoot } = document2.defaultView;
    if (target instanceof HTMLElement2 || target instanceof ShadowRoot) {
      if (attached && !isAttachedToDocument(target, document2)) {
        throw new OwlError("Cannot mount a component on a detached dom node");
      }
      return;
    }
  }
  throw new OwlError("Cannot mount component: the target is not a valid DOM element");
}
function whenReady(fn) {
  return new Promise(function(resolve) {
    if (document.readyState !== "loading") {
      resolve(true);
    } else {
      document.addEventListener("DOMContentLoaded", resolve, false);
    }
  }).then(fn || function() {
  });
}

// ../owl-runtime/src/rendering/template_helpers.ts
var ObjectCreate = Object.create;
function withDefault(value, defaultValue) {
  return value === void 0 || value === null || value === false ? defaultValue : value;
}
function callSlot(ctx, parent, key, name, dynamic, extra, defaultContent) {
  key = key + "__slot_" + name;
  const slots = ctx.__owl__.props.slots || {};
  const { __render, __ctx, __scope } = slots[name] || {};
  const slotScope = ObjectCreate(__ctx || {});
  if (__scope) {
    slotScope[__scope] = extra;
  }
  const slotBDom = __render ? __render(slotScope, parent, key) : null;
  if (defaultContent) {
    let child1 = void 0;
    let child2 = void 0;
    if (slotBDom) {
      child1 = dynamic ? toggler(name, slotBDom) : slotBDom;
    } else {
      child2 = defaultContent(ctx, parent, key);
    }
    return multi([child1, child2]);
  }
  return slotBDom || text("");
}
var objectKeys = /* @__PURE__ */ new WeakMap();
var nextObjectKey = 0;
var ID_MARK = "";
function keyOf(key) {
  if (typeof key === "string") {
    return key.includes(ID_MARK) ? key.replaceAll(ID_MARK, ID_MARK + ID_MARK) : key;
  }
  if (typeof key === "object" && key !== null || typeof key === "function") {
    if (Array.isArray(key)) {
      return keyOf(String(key));
    }
    let id = objectKeys.get(key);
    if (id === void 0) {
      id = ID_MARK + ++nextObjectKey;
      objectKeys.set(key, id);
    }
    return id;
  }
  return "" + key;
}
function withKey(elem, k) {
  elem.key = k;
  return elem;
}
function prepareList(collection) {
  let keys;
  let values;
  if (Array.isArray(collection)) {
    keys = readArrayItems(collection);
    values = keys;
  } else if (collection instanceof Map) {
    keys = [...collection.keys()];
    values = [...collection.values()];
  } else if (Symbol.iterator in Object(collection)) {
    keys = [...collection];
    values = keys;
  } else if (collection && typeof collection === "object") {
    values = Object.values(collection);
    keys = Object.keys(collection);
  } else {
    throw new OwlError(`Invalid loop expression: "${collection}" is not iterable`);
  }
  const n = values.length;
  return [keys, values, n, new Array(n)];
}
function toNumber(val) {
  const n = parseFloat(val);
  return isNaN(n) ? val : n;
}
var LazyValue = class {
  fn;
  ctx;
  component;
  node;
  key;
  constructor(fn, ctx, component, node, key) {
    this.fn = fn;
    this.ctx = ctx;
    this.component = component;
    this.node = node;
    this.key = key;
  }
  evaluate(siteKey = "") {
    return this.fn.call(this.component, this.ctx, this.node, this.key + siteKey);
  }
  toString() {
    return this.evaluate().toString();
  }
};
function safeOutput(value, key = "", site = "", depth = 0, k1, k2, k3) {
  if (value === void 0 || value === null) {
    return toggler("undefined", text(""));
  }
  let safeKey;
  let block;
  if (value instanceof Markup) {
    safeKey = `string_safe`;
    block = html(value);
  } else if (value instanceof LazyValue) {
    safeKey = `lazy_value`;
    let siteKey = key + site;
    if (depth) {
      siteKey += "__" + keyOf(k1);
      if (depth > 1) {
        siteKey += "__" + keyOf(k2);
        if (depth > 2) {
          siteKey += "__" + keyOf(k3);
        }
      }
    }
    block = value.evaluate(siteKey);
  } else {
    safeKey = "string_unsafe";
    block = text(value);
  }
  return toggler(safeKey, block);
}
function safeOutputOr(value, defaultContent, key, site, depth, k1, k2, k3) {
  if (value === void 0 || value === null) {
    return toggler("default", defaultContent());
  }
  return safeOutput(value, key, site, depth, k1, k2, k3);
}
function createRef(ref2, node) {
  if (!ref2) {
    throw new OwlError(`Ref is undefined or null`);
  }
  const callbacks = node.refCallbacks ||= /* @__PURE__ */ new WeakMap();
  let callback = callbacks.get(ref2);
  if (!callback) {
    callback = makeRefCallback(ref2, node);
    callbacks.set(ref2, callback);
  }
  return callback;
}
function makeRefCallback(ref2, node) {
  let add;
  let remove2;
  if (ref2.add && ref2.delete) {
    add = (el) => {
      ref2.add(el);
      node.trackRefElement(ref2, el, true);
    };
    remove2 = (prevEl) => {
      ref2.delete(prevEl);
      node.trackRefElement(ref2, prevEl, false);
    };
  } else if (ref2.set) {
    const atom = ref2[atomSymbol];
    if (atom) {
      add = (el) => {
        ref2.set(el);
        node.trackRef(ref2, atom);
      };
      remove2 = (prevEl) => {
        if (atom.value === prevEl) ref2.set(null);
      };
    } else {
      add = ref2.set.bind(ref2);
      remove2 = () => ref2.set(null);
    }
  } else {
    throw new OwlError(
      `Ref should implement either a 'set' function or 'add' and 'delete' functions`
    );
  }
  return (el, previousEl) => {
    if (previousEl) {
      remove2(previousEl);
    }
    if (el) {
      add(el);
    }
  };
}
function callHandler(fn, ctx, ev) {
  if (typeof fn !== "function") {
    throw new OwlError(
      `Invalid handler expression: the \`t-on\` expression should evaluate to a function, but got '${typeof fn}'. Did you mean to use an arrow function? (e.g. \`t-on-click="() => expr"\`)`
    );
  }
  fn.call(ctx["this"], ev);
}
var propSignals = /* @__PURE__ */ new WeakMap();
function wrapPropSignals(props2, names) {
  const signals = /* @__PURE__ */ Object.create(null);
  for (const name of names) {
    const s = signal(props2[name]);
    s.readonly = computed(s);
    signals[name] = s;
    props2[name] = s.readonly;
  }
  return signals;
}
function updatePropSignals(props2, signals) {
  for (const name in signals) {
    const s = signals[name];
    s.set(props2[name]);
    props2[name] = s.readonly;
  }
}
function modelExpr(value) {
  if (typeof value !== "function" || typeof value.set !== "function") {
    throw new OwlError(
      `Invalid t-model expression: expression should evaluate to a function with a 'set' method defined on it`
    );
  }
  return value;
}
function rerenderChild(node, props2, parentFiber) {
  if (debug.fiber) {
    debugLog("fiber", `render ${node.componentName} again: its pending render was cancelled`);
  }
  node.forceNextRender = false;
  const fiber = makeChildFiber(node, parentFiber);
  node.fiber = fiber;
  const parentRoot = parentFiber.root;
  if (node.willPatch.length) parentRoot.willPatch.push(fiber);
  if (node.patched.length) parentRoot.patched.push(fiber);
  node.props = props2;
  fiber.render();
}
function updateChild(node, props2, parentFiber) {
  if (debug.fiber) {
    debugLog(
      "fiber",
      `update ${node.componentName}: ${parentFiber.deep ? "deep render" : "props changed"}${node.willUpdateProps.length ? `, ${node.willUpdateProps.length} willUpdateProps` : ""}`
    );
  }
  node.forceNextRender = false;
  const hooks = node.willUpdateProps;
  const fiber = makeChildFiber(node, parentFiber);
  node.fiber = fiber;
  const parentRoot = parentFiber.root;
  if (node.willPatch.length) parentRoot.willPatch.push(fiber);
  if (node.patched.length) parentRoot.patched.push(fiber);
  let promises;
  if (hooks.length) {
    let nextProps = props2;
    const defaultProps = node.defaultProps;
    if (defaultProps) {
      nextProps = Object.assign({}, props2);
      for (const k in defaultProps) {
        if (nextProps[k] === void 0) {
          nextProps[k] = defaultProps[k];
        }
      }
    }
    const component = node.component;
    untrack(() => {
      for (const f of hooks) {
        const r = f.call(component, nextProps);
        if (r && typeof r.then === "function") {
          (promises ||= []).push(r);
        }
      }
    });
  }
  if (promises) {
    const p = promises.length === 1 ? promises[0] : Promise.all(promises);
    p.then(
      () => {
        if (fiber !== node.fiber) return;
        node.props = props2;
        for (const view of node.propsUpdated) view.update();
        fiber.render();
      },
      (error) => handleHookRejection(node, error)
    );
  } else {
    node.props = props2;
    for (const view of node.propsUpdated) view.update();
    fiber.render();
  }
}
function createComponent(app, name, isStatic, hasSlotsProp, hasDynamicPropList, propList, signalProps) {
  const isDynamic = !isStatic;
  let arePropsDifferent;
  const hasNoProp = propList.length === 0;
  if (hasSlotsProp) {
    arePropsDifferent = (_1, _2) => true;
  } else if (hasDynamicPropList) {
    arePropsDifferent = function(props1, props2) {
      for (let k in props1) {
        if (props1[k] !== props2[k] || !(k in props2)) {
          return true;
        }
      }
      return Object.keys(props1).length !== Object.keys(props2).length;
    };
  } else if (hasNoProp) {
    arePropsDifferent = (_1, _2) => false;
  } else {
    arePropsDifferent = function(props1, props2) {
      for (let p of propList) {
        if (props1[p] !== props2[p]) {
          return true;
        }
      }
      return false;
    };
  }
  const initiateRender = ComponentNode.prototype.initiateRender;
  return (props2, key, ctx, parent, C) => {
    let node = ctx.childMap?.get(key);
    if (isDynamic && node && node.component.constructor !== C) {
      node = void 0;
    }
    const parentFiber = ctx.fiber;
    let signals;
    if (signalProps) {
      signals = node && propSignals.get(node);
      if (signals) {
        updatePropSignals(props2, signals);
      } else {
        signals = wrapPropSignals(props2, signalProps);
      }
    }
    if (node) {
      if (arePropsDifferent(node.props, props2) || parentFiber.deep) {
        updateChild(node, props2, parentFiber);
      } else if (node.forceNextRender) {
        rerenderChild(node, props2, parentFiber);
      } else if (debug.fiber) {
        debugLog("fiber", `keep ${node.componentName}: props unchanged`);
      }
    } else {
      if (isStatic) {
        const components = parent.constructor.components;
        if (!components) {
          throw new OwlError(
            `Cannot find the definition of component "${name}", missing static components key in parent`
          );
        }
        C = components[name];
        if (!C) {
          throw new OwlError(`Cannot find the definition of component "${name}"`);
        } else if (!(C.prototype instanceof Component)) {
          throw new OwlError(
            `"${name}" is not a Component. It must inherit from the Component class`
          );
        }
      }
      node = new ComponentNode(C, props2, app, ctx, key);
      if (signals) {
        propSignals.set(node, signals);
      }
      (ctx.childMap ||= /* @__PURE__ */ new Map()).set(key, node);
      const fiber = new Fiber2(node, parentFiber);
      if (node.willStart.length) {
        initiateRender.call(node, fiber);
      } else {
        node.fiber = fiber;
        if (node.mounted.length) {
          fiber.root.mounted.push(fiber);
        }
        fiber.render();
      }
    }
    (parentFiber.childrenMap ||= /* @__PURE__ */ new Map()).set(key, node);
    memoCollectChild(key);
    return node;
  };
}
function callTemplate(subTemplate, owner, app, ctx, parent, key) {
  const template = app.getTemplate(subTemplate);
  return toggler(subTemplate, template.call(owner, ctx, parent, key + subTemplate));
}
var INVALID_TAG_NAME = /[\s"'<>\/=&`]/;
function checkTagName(tag) {
  if (tag && (typeof tag !== "string" || INVALID_TAG_NAME.test(tag))) {
    throw new OwlError(`Invalid tag name: '${tag}'`);
  }
  return tag;
}
var helpers = {
  withDefault,
  checkTagName,
  zero: /* @__PURE__ */ Symbol("zero"),
  callSlot,
  withKey,
  keyOf,
  prepareList,
  toNumber,
  LazyValue,
  safeOutput,
  safeOutputOr,
  createCatcher,
  markRaw,
  OwlError,
  createRef,
  modelExpr,
  createComponent,
  callTemplate,
  callHandler,
  memoPrevious,
  memoKeep,
  memoHit,
  memoBegin,
  memoEnd
};

// ../owl-runtime/src/template_set.ts
var bdom = { text, createBlock, list, multi, html, toggler };
var TemplateSet = class _TemplateSet {
  static compiler = null;
  static registerTemplate(name, fn) {
    globalTemplates[name] = fn;
  }
  dev;
  rawTemplates = Object.create(globalTemplates);
  templates = /* @__PURE__ */ Object.create(null);
  getRawTemplate;
  translateFn;
  translatableAttributes;
  customDirectives;
  runtimeUtils;
  hasGlobalValues;
  constructor(config3 = {}) {
    this.dev = config3.dev || false;
    this.translateFn = config3.translateFn;
    this.translatableAttributes = config3.translatableAttributes;
    if (config3.templates) {
      if (config3.templates instanceof Document || typeof config3.templates === "string") {
        this.addTemplates(config3.templates);
      } else {
        for (const name in config3.templates) {
          this.addTemplate(name, config3.templates[name]);
        }
      }
    }
    this.getRawTemplate = config3.getTemplate;
    this.customDirectives = config3.customDirectives || {};
    this.runtimeUtils = { ...helpers, __globals__: config3.globalValues || {} };
    this.hasGlobalValues = Boolean(config3.globalValues && Object.keys(config3.globalValues).length);
  }
  addTemplate(name, template) {
    if (name in this.rawTemplates) {
      if (!this.dev) {
        return;
      }
      const rawTemplate = this.rawTemplates[name];
      if (areTemplatesEqual(rawTemplate, template)) {
        return;
      }
      throw new OwlError(`Template ${name} already defined with different content`);
    }
    this.rawTemplates[name] = template;
  }
  addTemplates(xml2) {
    if (!xml2) {
      return;
    }
    xml2 = xml2 instanceof Document ? xml2 : this._parseXML(xml2);
    for (const template of xml2.querySelectorAll("[t-name]")) {
      const name = template.getAttribute("t-name");
      this.addTemplate(name, template);
    }
  }
  getTemplate(name) {
    const cacheKey = name;
    if (!(cacheKey in this.templates)) {
      const rawTemplate = this.getRawTemplate?.(name) || this.rawTemplates[name];
      if (rawTemplate === void 0) {
        let extraInfo = "";
        const scope = getScope();
        if (scope instanceof ComponentNode) {
          extraInfo = ` (for component "${scope.componentName}")`;
        }
        throw new OwlError(`Missing template: "${name}"${extraInfo}`);
      }
      const isFn = typeof rawTemplate === "function" && !(rawTemplate instanceof Element);
      const start = debug.template ? debugNow() : -1;
      const templateFn = isFn ? rawTemplate : this._compileTemplate(name, rawTemplate);
      if (debug.template) {
        debugLog(
          "template",
          isFn ? `${name}: precompiled` : `${name}: compiled${start < 0 ? "" : ` in ${(debugNow() - start).toFixed(2)} ms`}, ${String(templateFn).length} chars`
        );
      }
      const templates = this.templates;
      this.templates[cacheKey] = function(context, parent) {
        return templates[cacheKey].call(this, context, parent);
      };
      try {
        this.templates[cacheKey] = templateFn(this, bdom, this.runtimeUtils);
      } catch (e) {
        delete this.templates[cacheKey];
        throw e;
      }
    }
    return this.templates[cacheKey];
  }
  _compileTemplate(name, template) {
    if (!_TemplateSet.compiler) {
      throw new OwlError(
        `Unable to compile a template: load the compiler module (@odoo/owl/compiler) or use the full build`
      );
    }
    return _TemplateSet.compiler.compile(template, {
      name,
      dev: this.dev,
      translateFn: this.translateFn,
      translatableAttributes: this.translatableAttributes,
      customDirectives: this.customDirectives,
      hasGlobalValues: this.hasGlobalValues
    });
  }
  _parseXML(xml2) {
    if (!_TemplateSet.compiler) {
      throw new OwlError(
        `Unable to parse XML templates: load the compiler module (@odoo/owl/compiler), use the full build, or pass a Document instance`
      );
    }
    return _TemplateSet.compiler.parseXML(xml2);
  }
};
var globalTemplates = /* @__PURE__ */ Object.create(null);
function xml(...args) {
  const name = `__template__${xml.nextId++}`;
  const value = String.raw(...args);
  globalTemplates[name] = value;
  return name;
}
xml.nextId = 1;
function areTemplatesEqual(t1, t2) {
  if (t1 === t2) {
    return true;
  }
  if (typeof t1 === "function" !== (typeof t2 === "function")) {
    return false;
  }
  const s1 = t1 instanceof Element ? t1.outerHTML : String(t1);
  const s2 = t2 instanceof Element ? t2.outerHTML : String(t2);
  return s1 === s2;
}

// ../owl-runtime/src/app.ts
var hasBeenLogged = false;
var apps = /* @__PURE__ */ new Set();
if (typeof window !== "undefined") {
  window.__OWL_DEVTOOLS__ ||= { apps, Fiber: Fiber2, RootFiber: RootFiber2, toRaw, proxy };
}
var App = class _App extends TemplateSet {
  static validateTarget = validateTarget;
  static apps = apps;
  static version = version;
  name;
  scheduler = new Scheduler();
  roots = /* @__PURE__ */ new Set();
  pluginManager;
  destroyed = false;
  constructor(config3 = {}) {
    super(config3.test ? { ...config3, dev: true } : config3);
    this.name = config3.name || "";
    apps.add(this);
    this.pluginManager = new PluginManager(this, { config: config3.config });
    if (config3.plugins) {
      startPlugins(this.pluginManager, config3.plugins);
    } else {
      this.pluginManager.status = STATUS.MOUNTED;
    }
    if (this.dev && !config3.test && !hasBeenLogged) {
      console.info(`Owl is running in 'dev' mode.`);
      hasBeenLogged = true;
    }
  }
  createRoot(Root, config3 = {}) {
    if (this.destroyed) {
      throw new OwlError("Cannot create a root in a destroyed app");
    }
    if (debug.lifecycle) {
      debugLog("lifecycle", `create root ${Root.name}${this.name ? ` in app ${this.name}` : ""}`);
    }
    const props2 = config3.props || {};
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => {
      resolve = res;
      reject = rej;
    });
    let node;
    let error = null;
    try {
      node = new ComponentNode(Root, props2, this, null, null);
      const subConfig = config3;
      if (subConfig.pluginManager) {
        node.pluginManager = subConfig.pluginManager;
      }
      if (subConfig.onError) {
        const handlers = nodeErrorHandlers.get(node);
        if (handlers) {
          handlers.unshift(subConfig.onError);
        } else {
          nodeErrorHandlers.set(node, [subConfig.onError]);
        }
      }
      if (subConfig.host) {
        subRootHosts.set(node, subConfig.host);
      }
    } catch (e) {
      error = e;
      reject(e);
    }
    let fiber = null;
    let preparedPromise = null;
    let resolvePrepared = null;
    let destroyed = false;
    let mounted = false;
    const prepare = () => {
      if (preparedPromise) {
        return preparedPromise;
      }
      if (destroyed) {
        return preparedPromise = Promise.resolve();
      }
      if (error) {
        return Promise.reject(error);
      }
      fiber = new MountFiber(node, null);
      let handlers = nodeErrorHandlers.get(node);
      if (!handlers) {
        handlers = [];
        nodeErrorHandlers.set(node, handlers);
      }
      handlers.unshift((error2, finalize) => {
        finalize();
        reject(error2);
      });
      const ready = new Promise((res) => {
        resolvePrepared = res;
        fiber.onPrepared = () => res();
      });
      preparedPromise = ready;
      node.addHook("mounted", () => {
        resolve(node.component);
        handlers.shift();
      });
      this.scheduler.addFiber(fiber);
      if (this.pluginManager.status < STATUS.MOUNTED) {
        node.willStart.unshift(() => this.pluginManager.ready);
      }
      if (node.willStart.length) {
        node.initiateRender(fiber);
      } else {
        node.fiber = fiber;
        if (node.mounted.length) {
          fiber.root.mounted.push(fiber);
        }
        try {
          fiber.render();
        } catch (e) {
          reject(e);
        }
      }
      return preparedPromise;
    };
    const mount3 = (target, options) => {
      if (destroyed) {
        return promise;
      }
      if (error) {
        return promise;
      }
      if (mounted) {
        throw new OwlError("This root is already mounted: create another root to mount again");
      }
      _App.validateTarget(target);
      prepare();
      mounted = true;
      fiber.commit(target, options);
      return promise;
    };
    const root = {
      get prepared() {
        return fiber ? fiber.counter === 0 : false;
      },
      get destroyed() {
        return destroyed;
      },
      promise,
      prepare,
      mount: mount3,
      destroy: () => {
        if (destroyed) {
          return;
        }
        destroyed = true;
        this.roots.delete(root);
        node?.destroy();
        resolvePrepared?.();
      }
    };
    this.roots.add(root);
    return root;
  }
  destroy() {
    if (debug.lifecycle) {
      debugLog(
        "lifecycle",
        `destroy app${this.name ? ` ${this.name}` : ""}, ${this.roots.size} root(s)`
      );
    }
    let failure = null;
    for (let root of this.roots) {
      try {
        root.destroy();
      } catch (error) {
        failure ||= { error };
      }
    }
    this.pluginManager.destroy();
    this.scheduler.tasks.clear();
    Scheduler.active.delete(this.scheduler);
    this.scheduler.delayedRenders = [];
    apps.delete(this);
    this.destroyed = true;
    if (failure) {
      throw failure.error;
    }
  }
  _handleError(error) {
    throw error;
  }
};
async function mount2(C, target, config3 = {}) {
  const app = new App(config3);
  if (app.pluginManager.status < STATUS.MOUNTED) {
    await app.pluginManager.ready;
    if (app.destroyed) {
      throw makeAbortError();
    }
  }
  const root = app.createRoot(C, config3);
  return root.mount(target, config3);
}

// ../owl-runtime/src/event_handling.ts
var mainEventHandler = (data, ev, currentTarget) => {
  setCurrentEvent(ev);
  const modifiers = data[2];
  if (modifiers) {
    if (modifiers & EventModifier.PREVENT_ANY) {
      ev.preventDefault();
    }
    if (modifiers & EventModifier.STOP_ANY) {
      ev.stopPropagation();
    }
    if (modifiers & EventModifier.SELF && ev.target !== currentTarget) {
      if (debug.event) {
        debugLog("event", `${ev.type}: skipped by .self, not from its own element`);
      }
      return;
    }
    if (modifiers & EventModifier.PREVENT) {
      ev.preventDefault();
    }
    if (modifiers & EventModifier.STOP) {
      ev.stopPropagation();
    }
  }
  const handler = data[0];
  if (handler !== null) {
    if (typeof handler !== "function") {
      throw new OwlError(`Invalid handler (expected a function, received: '${handler}')`);
    }
    const context = data[1];
    let node = context ? context.__owl__ : null;
    const live = node ? node.status === STATUS.MOUNTED : true;
    if (debug.event) {
      debugLog(
        "event",
        `${ev.type} on ${currentTarget?.nodeName ?? "?"}: ${live ? "handled" : "dropped, component not mounted"} by ${node ? node.componentName : "a handler"}`,
        ev
      );
    }
    if (live) {
      if (data.length > 3) {
        handler(context, ev, data[3]);
      } else {
        handler(context, ev);
      }
    }
  }
};

// ../owl-runtime/src/lifecycle_hooks.ts
function onWillUpdateProps(fn) {
  const scope = getComponentScope();
  function swapped(s, nextProps) {
    return fn.call(this, nextProps, s);
  }
  scope.addHook("willUpdateProps", scope.decorate(swapped, "onWillUpdateProps"));
}
function onMounted(fn) {
  const scope = getComponentScope();
  scope.addHook("mounted", scope.decorate(fn, "onMounted"));
}
function onWillPatch(fn) {
  const scope = getComponentScope();
  scope.addHook("willPatch", scope.decorate(fn, "onWillPatch"), true);
}
function onPatched(fn) {
  const scope = getComponentScope();
  scope.addHook("patched", scope.decorate(fn, "onPatched"));
}
function onWillUnmount(fn) {
  const scope = getComponentScope();
  scope.addHook("willUnmount", scope.decorate(fn, "onWillUnmount"), true);
}
function onError(callback) {
  const scope = getComponentScope();
  let handlers = nodeErrorHandlers.get(scope);
  if (!handlers) {
    handlers = [];
    nodeErrorHandlers.set(scope, handlers);
  }
  handlers.push(callback.bind(scope.component));
}

// ../owl-runtime/src/prop.ts
function staticProp(key, type) {
  const node = getComponentScope();
  const defaultFactory = getDefault(type);
  const propValue = node.props[key];
  const usesDefault = propValue === void 0 && !!defaultFactory;
  const value = usesDefault ? defaultFactory() : propValue === void 0 ? node.defaultProps?.[key] : propValue;
  if (node.app.dev) {
    if (type !== void 0) {
      const message = usesDefault ? `Invalid default value for prop '${key}' in '${node.componentName}'` : `Invalid prop '${key}' in '${node.componentName}'`;
      assertType(usesDefault ? value : propValue, type, message);
    }
    node.addHook("willUpdateProps", (nextProps) => {
      const current = node.props[key] === void 0 ? node.defaultProps?.[key] : node.props[key];
      if (nextProps[key] !== current) {
        throw new OwlError(
          `Prop '${key}' changed in component '${node.componentName}'. Props declared with \`props.static()\` are static and should not change. If the prop is a signal, pass the same signal reference (its inner value may change).`
        );
      }
    });
  }
  return value;
}

// ../owl-runtime/src/types.ts
function componentType() {
  return constructorType(Component);
}
var types2 = {
  ...types,
  component: componentType
};

// ../owl-runtime/src/props.ts
var defaultsVersions = /* @__PURE__ */ new WeakMap();
function makeProps(type) {
  const node = getComponentScope();
  if (!type) {
    const view = new PropsView(node);
    node.addHook("propsUpdated", view);
    return new Proxy(view, viewHandler);
  }
  const { app, componentName } = node;
  let defaults = null;
  if (!Array.isArray(type)) {
    for (const key in type) {
      const factory = getDefault(type[key]);
      if (factory) {
        (defaults ||= {})[key] = factory();
      }
    }
  }
  if (defaults) {
    node.defaultProps = Object.assign(node.defaultProps || {}, defaults);
    defaultsVersions.set(node, (defaultsVersions.get(node) || 0) + 1);
  }
  const keys = Array.isArray(type) ? type : schemaKeys(type);
  const state = new TypedProps(node, defaults);
  const result = new PropsTable();
  for (const key of keys) {
    Reflect.defineProperty(result, key, {
      enumerable: true,
      configurable: true,
      get: propGetters[key] ||= makePropGetter(key)
    });
  }
  new StateStamp(result, state);
  node.addHook("propsUpdated", state);
  if (app.dev) {
    if (defaults) {
      const defaultedShape = {};
      for (const key in type) {
        if (key in defaults) {
          defaultedShape[key] = type[key];
        }
      }
      assertType(
        defaults,
        types2.object(defaultedShape),
        `Invalid component default props (${componentName})`
      );
    }
    const validation = types2.object(type);
    assertType(node.props, validation, `Invalid component props (${componentName})`);
    node.addHook("willUpdateProps", (np) => {
      assertType(np, validation, `Invalid component props (${componentName})`);
    });
  }
  return Object.preventExtensions(result);
}
var schemaKeyLists = /* @__PURE__ */ new WeakMap();
function schemaKeys(type) {
  let keys = schemaKeyLists.get(type);
  if (!keys) {
    keys = Object.keys(type);
    schemaKeyLists.set(type, keys);
  }
  return keys;
}
var TypedProps = class {
  node;
  defaults;
  atoms = new AtomTable();
  constructor(node, defaults) {
    this.node = node;
    this.defaults = defaults;
  }
  // a missing prop resolves to this view's default, else to the default another
  // view of the component declared
  resolve(key) {
    const value = this.node.props[key];
    if (value === void 0) {
      const defaults = this.defaults;
      if (defaults && key in defaults) {
        return defaults[key];
      }
      const declared = this.node.defaultProps;
      if (declared && key in declared) {
        return declared[key];
      }
    }
    return value;
  }
  read(key) {
    let atom = this.atoms[key];
    if (atom === void 0) {
      if (!isObserving()) {
        return this.resolve(key);
      }
      atom = this.atoms[key] = createAtom(this.resolve(key), "prop");
    }
    onReadAtom(atom);
    return atom.value;
  }
  update() {
    writeAtoms(this.atoms, this);
  }
};
function writeAtoms(atoms, view) {
  for (const key in atoms) {
    const atom = atoms[key];
    const value = view.resolve(key);
    if (!Object.is(atom.value, value)) {
      atom.value = value;
      onWriteAtom(atom, true);
    }
  }
}
var ObjectReturner = class {
  constructor(target) {
    return target;
  }
};
var StateStamp = class extends ObjectReturner {
  #state;
  constructor(target, state) {
    super(target);
    this.#state = state;
  }
  // the state of `view`, or of the view it inherits from (a read through
  // `Object.create(props)`)
  static of(view) {
    while (view !== null && typeof view === "object") {
      if (#state in view) {
        return view.#state;
      }
      view = Object.getPrototypeOf(view);
    }
    return void 0;
  }
};
var propGetters = /* @__PURE__ */ Object.create(null);
function makePropGetter(key) {
  return function() {
    const state = StateStamp.of(this);
    if (state === void 0) {
      throw new OwlError(`Cannot read prop "${key}" through an object that is not a props view`);
    }
    return state.read(key);
  };
}
function getKeys(node) {
  const props2 = node.props;
  const keys = [];
  for (const k in props2) {
    if (k.charCodeAt(0) !== 1) {
      keys.push(k);
    }
  }
  for (const k in node.defaultProps) {
    if (!(k in props2)) {
      keys.push(k);
    }
  }
  return keys;
}
var AtomTable = function() {
};
AtomTable.prototype = /* @__PURE__ */ Object.create(null);
var PropsTable = function() {
};
PropsTable.prototype = Object.freeze(/* @__PURE__ */ Object.create(null));
var PropsView = class {
  node;
  atoms = new AtomTable();
  keys = null;
  keyLookup = null;
  keysDefaults = 0;
  keySet = null;
  keysVersion = 0;
  constructor(node) {
    this.node = node;
  }
  resolve(key) {
    const node = this.node;
    const value = node.props[key];
    if (value === void 0) {
      const declared = node.defaultProps;
      if (declared && key in declared) {
        return declared[key];
      }
    }
    return value;
  }
  read(key) {
    let atom = this.atoms[key];
    if (atom === void 0) {
      if (!isObserving()) {
        return this.resolve(key);
      }
      atom = this.atoms[key] = createAtom(this.resolve(key), "prop");
    }
    onReadAtom(atom);
    return atom.value;
  }
  // the key set as a reader sees it: subscribes to its changes
  currentKeys() {
    (this.keySet ||= signal(this.keysVersion))();
    return this.refreshKeys();
  }
  refreshKeys() {
    const defaultsVersion = defaultsVersions.get(this.node) || 0;
    if (!this.keys || this.keysDefaults !== defaultsVersion) {
      this.keys = getKeys(this.node);
      this.keyLookup = null;
      this.keysDefaults = defaultsVersion;
    }
    return this.keys;
  }
  hasKey(key) {
    const keys = this.currentKeys();
    return (this.keyLookup ||= new Set(keys)).has(key);
  }
  update() {
    writeAtoms(this.atoms, this);
    if (!this.keySet) {
      return;
    }
    const previousKeys = this.refreshKeys();
    const nextKeys = getKeys(this.node);
    if (nextKeys.length !== previousKeys.length || nextKeys.some((key, i) => key !== previousKeys[i])) {
      this.keys = nextKeys;
      this.keyLookup = null;
      this.keySet.set(++this.keysVersion);
    }
  }
};
var viewHandler = {
  get: (view, key) => typeof key === "string" ? view.read(key) : void 0,
  has: (view, key) => typeof key === "string" && view.hasKey(key),
  ownKeys: (view) => view.currentKeys(),
  getOwnPropertyDescriptor(view, key) {
    if (typeof key === "string" && view.hasKey(key)) {
      return { value: view.read(key), enumerable: true, configurable: true, writable: false };
    }
    return void 0;
  },
  getPrototypeOf: () => null,
  set: () => false,
  defineProperty: () => false,
  deleteProperty: () => false
};
var useProps = Object.assign(makeProps, { static: staticProp });
var props = useProps;

// ../owl-runtime/src/error_boundary.ts
var ErrorBoundary = class extends Component {
  static template = xml`
    <t t-if="this.props.error()">
      <t t-call-slot="fallback"/>
    </t>
    <t t-else="">
      <t t-call-slot="default"/>
    </t>
  `;
  props = props({ error: types2.signal().optional(() => signal(null)) });
  setup() {
    onError((e) => this.props.error.set(e));
  }
};

// ../owl-runtime/src/hooks.ts
var useApp2 = useApp;

// ../owl-runtime/src/portal.ts
var PortalContent = class extends Component {
  static template = xml`<t t-call-slot="default"/>`;
};
var Portal = class extends Component {
  static template = xml``;
  props = props({
    slots: types2.object(["default"]),
    target: types2.or([
      types2.string(),
      types2.signal(types2.instanceOf(HTMLElement)),
      types2.instanceOf(HTMLElement),
      types2.literal(null)
    ]).optional()
  });
  setup() {
    const portalNode = this.__owl__;
    const app = portalNode.app;
    const portalProps = this.props;
    let root = null;
    let mountedTarget = null;
    let committed = false;
    const tearDown = () => {
      if (root) {
        root.destroy();
        root = null;
        mountedTarget = null;
      }
    };
    const mountInto = (target, position) => {
      tearDown();
      root = app.createRoot(PortalContent, {
        props: {
          get slots() {
            return portalProps.slots;
          }
        },
        // Forward the plugin chain from this Portal (createRoot defaults
        // sub-roots to the app-level plugin manager) so `providePlugins`
        // contributions from ancestors are visible inside the portaled content.
        pluginManager: portalNode.pluginManager,
        // Route errors from the portaled subtree back through Portal's parent
        // chain so consumer `onError` handlers still catch them. Without this,
        // sub-root errors would propagate to app._handleError and tear down
        // the whole app.
        onError: forwardErrorToParent(portalNode),
        // Let the scheduler see through the sub-root boundary, so renders of
        // the portaled content yield to in-flight ancestor renders (e.g. a
        // t-if about to remove this Portal).
        host: portalNode
      });
      mountedTarget = target;
      committed = false;
      if (portalNode.status === STATUS.MOUNTED) {
        commit(position);
      } else {
        root.prepare();
      }
    };
    const commit = (position) => {
      committed = true;
      root.mount(mountedTarget, { position, allowDetached: true });
    };
    useEffect(() => {
      const target = resolveTarget(this.props.target);
      if (!target) {
        return;
      }
      mountInto(target);
      return tearDown;
    });
    onMounted(() => {
      if (root && mountedTarget && !mountedTarget.isConnected && typeof this.props.target === "string") {
        tearDown();
      }
      if (root && !committed) {
        commit();
      }
      if (!root && typeof this.props.target === "string") {
        const target = resolveTarget(this.props.target);
        if (target) {
          mountInto(target, "first-child");
        }
      }
    });
    onWillDestroy(tearDown);
  }
};
function resolveTarget(target) {
  if (typeof target === "function") {
    target = target();
  }
  if (typeof target === "string") {
    return document.querySelector(target);
  }
  if (target instanceof HTMLElement) {
    return target;
  }
  return null;
}

// ../owl-runtime/src/suspense.ts
var SuspenseHost = class extends Component {
  static template = xml`<t t-call-slot="default"/>`;
};
var Suspense = class extends Component {
  static template = xml`
    <t t-if="!this.prepared()">
      <t t-call-slot="fallback"/>
    </t>
  `;
  props = props({ slots: types2.object({ default: types2.any(), fallback: types2.any().optional() }) });
  prepared = signal(false);
  mounted = signal(false);
  subRootMounted = false;
  setup() {
    const suspenseNode = this.__owl__;
    const suspenseProps = this.props;
    const root = suspenseNode.app.createRoot(SuspenseHost, {
      props: {
        get slots() {
          return suspenseProps.slots;
        }
      },
      // Thread the plugin manager so `providePlugins` contributions from
      // ancestors are visible inside the default slot. (createRoot defaults
      // sub-roots to the app-level plugin manager; override here.) Destroy
      // cascade is handled explicitly below via `onWillDestroy`.
      pluginManager: suspenseNode.pluginManager,
      // Route errors from the sub-root back into Suspense's parent chain so
      // consumer `onError` handlers still catch descendant failures.
      onError: forwardErrorToParent(suspenseNode),
      // Let the scheduler see through the sub-root boundary, so renders of
      // the default slot yield to in-flight ancestor renders (e.g. a t-if
      // about to remove this Suspense).
      host: suspenseNode
    });
    root.prepare().then(() => this.prepared.set(true));
    if (root.prepared) {
      this.prepared.set(true);
    }
    onMounted(() => this.mounted.set(true));
    useEffect(() => {
      if (this.subRootMounted || !this.prepared() || !this.mounted()) {
        return;
      }
      this.subRootMounted = true;
      const anchor = suspenseNode.bdom.firstNode();
      root.mount(anchor.parentElement, { afterNode: anchor });
    });
    onWillDestroy(() => root.destroy());
  }
};

// ../owl-runtime/src/plugin_hooks.ts
function providePlugins(pluginConstructors, config3) {
  const node = getComponentScope();
  const manager = new PluginManager(node.app, { parent: node.pluginManager, config: config3 });
  node.pluginManager = manager;
  onWillDestroy(() => manager.destroy());
  startPlugins(manager, pluginConstructors);
  if (manager.status < STATUS.MOUNTED) {
    onWillStart(() => manager.ready);
  }
}

// ../owl-runtime/src/index.ts
config2.mainEventHandler = mainEventHandler;
var blockDom = {
  config: config2,
  // bdom entry points
  mount,
  patch,
  remove,
  // bdom block types
  list,
  multi,
  text,
  toggler,
  createBlock,
  html
};
var __info__ = {
  version: App.version,
  date: "2026-10-05T23:37:45.031Z",
  hash: "740f45dc",
  url: "https://github.com/odoo/owl"
};

// ../owl-compiler/src/inline_expressions.ts
var RESERVED_WORDS = new Set(
  "true,false,NaN,null,undefined,debugger,console,window,in,instanceof,new,function,return,eval,void,__globals__,Math,RegExp,Array,Object,Date,Number,Boolean,String,Symbol,BigInt,Map,Set,JSON,Intl,Error,Infinity,isFinite,isNaN,parseFloat,parseInt,decodeURI,decodeURIComponent,encodeURI,encodeURIComponent".split(",")
);
var WORD_REPLACEMENT = Object.assign(/* @__PURE__ */ Object.create(null), {
  and: "&&",
  or: "||",
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<="
});
var STATIC_TOKEN_MAP = Object.assign(/* @__PURE__ */ Object.create(null), {
  "{": "LEFT_BRACE",
  "}": "RIGHT_BRACE",
  "[": "LEFT_BRACKET",
  "]": "RIGHT_BRACKET",
  ":": "COLON",
  ",": "COMMA",
  "(": "LEFT_PAREN",
  ")": "RIGHT_PAREN"
});
var OPERATORS = "...,.,===,==,++,+,!==,!=,!,||,&&,>=,>,<=,<,??=,??,?.,?,--,-,*,/,%,typeof ,=>,=,;,in ,new ,|,&,^,~".split(
  ","
);
var tokenizeString = function(expr) {
  let s = expr[0];
  let start = s;
  if (s !== "'" && s !== '"' && s !== "`") {
    return false;
  }
  if (start === "`") {
    const end = findTemplateEnd(expr, 0);
    const value = expr.slice(0, end + 1);
    return {
      type: "TEMPLATE_STRING",
      value,
      replace(replacer) {
        return replaceInterpolations(value, replacer);
      }
    };
  }
  let i = 1;
  let cur;
  while (expr[i] && expr[i] !== start) {
    cur = expr[i];
    s += cur;
    if (cur === "\\") {
      i++;
      cur = expr[i];
      if (!cur) {
        throw new OwlError("Invalid expression");
      }
      s += cur;
    }
    i++;
  }
  if (expr[i] !== start) {
    throw new OwlError("Invalid expression");
  }
  s += start;
  return { type: "VALUE", value: s };
};
function findTemplateEnd(str, start) {
  for (let i = start + 1; i < str.length; i++) {
    if (str[i] === "\\") {
      i++;
    } else if (str[i] === "`") {
      return i;
    } else if (str.startsWith("${", i)) {
      i = findClosingBrace(str, i + 2);
    }
  }
  throw new OwlError("Invalid expression");
}
function replaceInterpolations(template, replacer) {
  let result = "";
  let i = 0;
  while (i < template.length) {
    if (template[i] === "\\") {
      result += template.slice(i, i + 2);
      i += 2;
    } else if (template.startsWith("${", i)) {
      const end = findClosingBrace(template, i + 2);
      result += "${" + replacer(template.slice(i + 2, end)) + "}";
      i = end + 1;
    } else {
      result += template[i++];
    }
  }
  return result;
}
function findClosingBrace(str, start) {
  let depth = 0;
  for (let i = start; i < str.length; i++) {
    const char = str[i];
    if (char === "'" || char === '"') {
      for (i++; i < str.length && str[i] !== char; i++) {
        if (str[i] === "\\") {
          i++;
        }
      }
    } else if (char === "`") {
      i = findTemplateEnd(str, i);
    } else if (char === "{") {
      depth++;
    } else if (char === "}") {
      if (!depth) {
        return i;
      }
      depth--;
    }
  }
  throw new OwlError("Invalid expression");
}
var NUMBER_RE = /^(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d[\d_]*)?)n?/;
var tokenizeNumber = function(expr) {
  const match = NUMBER_RE.exec(expr);
  return match ? { type: "VALUE", value: match[0] } : false;
};
var SYMBOL_RE = /^[\p{ID_Start}_$][\p{ID_Continue}$\u200C\u200D]*/u;
var IDENTIFIER_CHAR_RE = /[\p{ID_Continue}$\u200C\u200D]/u;
var OBJECT_KEY_END_RE = /^\s*[:,}]/;
var tokenizeSymbol = function(expr, previous) {
  const match = SYMBOL_RE.exec(expr);
  if (!match) {
    return false;
  }
  const s = match[0];
  const isKey = (previous?.type === "LEFT_BRACE" || previous?.type === "COMMA") && OBJECT_KEY_END_RE.test(expr.slice(s.length));
  if (s in WORD_REPLACEMENT && !isKey) {
    return { type: "OPERATOR", value: WORD_REPLACEMENT[s], size: s.length };
  }
  return { type: "SYMBOL", value: s };
};
var OPERAND_PREFIXES = /* @__PURE__ */ new Set([
  "OPERATOR",
  "LEFT_BRACE",
  "LEFT_BRACKET",
  "LEFT_PAREN",
  "COMMA",
  "COLON"
]);
var OPERAND_KEYWORDS = /* @__PURE__ */ new Set(["void", "return"]);
var tokenizeRegExp = function(expr, previous, beforePrevious) {
  const afterKeyword = previous?.type === "SYMBOL" && OPERAND_KEYWORDS.has(previous.value) && beforePrevious?.value !== "." && beforePrevious?.value !== "?.";
  if (expr[0] !== "/" || previous && !afterKeyword && (!OPERAND_PREFIXES.has(previous.type) || previous.value === "++" || previous.value === "--")) {
    return false;
  }
  let inClass = false;
  let i = 1;
  for (; expr[i] !== "/" || inClass; i++) {
    const char = expr[i];
    if (!char || char === "\n") {
      throw new OwlError("Invalid expression");
    }
    if (char === "\\") {
      i++;
    } else if (char === "[") {
      inClass = true;
    } else if (char === "]") {
      inClass = false;
    }
  }
  const flags = /^[a-z]*/.exec(expr.slice(i + 1))[0];
  return { type: "VALUE", value: expr.slice(0, i + 1 + flags.length) };
};
var tokenizeStatic = function(expr) {
  const char = expr[0];
  if (char && char in STATIC_TOKEN_MAP) {
    return { type: STATIC_TOKEN_MAP[char], value: char };
  }
  return false;
};
var tokenizeProperty = function(expr) {
  const match = SYMBOL_RE.exec(expr);
  return match ? { type: "SYMBOL", value: match[0] } : false;
};
var tokenizeOperator = function(expr) {
  for (let op of OPERATORS) {
    if (op === "?." && /\d/.test(expr[2])) {
      continue;
    }
    if (op.endsWith(" ")) {
      const word = op.slice(0, -1);
      const next = expr[word.length] || "";
      if (expr.startsWith(word) && !IDENTIFIER_CHAR_RE.test(next)) {
        return next === " " ? { type: "OPERATOR", value: op } : { type: "OPERATOR", value: op, size: word.length };
      }
    } else if (expr.startsWith(op)) {
      return { type: "OPERATOR", value: op };
    }
  }
  return false;
};
var TOKENIZERS = [
  tokenizeString,
  tokenizeRegExp,
  tokenizeNumber,
  tokenizeOperator,
  tokenizeSymbol,
  tokenizeStatic
];
var PROPERTY_TOKENIZERS = [tokenizeProperty, ...TOKENIZERS];
function tokenize(expr) {
  const result = [];
  let token = true;
  let error;
  let current = expr;
  try {
    while (token) {
      current = current.trim();
      if (current) {
        const previous = result[result.length - 1];
        const isProperty = previous?.value === "." || previous?.value === "?.";
        for (let tokenizer of isProperty ? PROPERTY_TOKENIZERS : TOKENIZERS) {
          token = tokenizer(current, previous, result[result.length - 2]);
          if (token) {
            result.push(token);
            current = current.slice(token.size || token.value.length);
            break;
          }
        }
      } else {
        token = false;
      }
    }
  } catch (e) {
    error = e;
  }
  if (current.length || error) {
    throw new OwlError(`Tokenizer error: could not tokenize \`${expr}\``);
  }
  return result;
}
var isLeftSeparator = (token) => token && (token.type === "LEFT_BRACE" || token.type === "COMMA");
var isRightSeparator = (token) => token && (token.type === "RIGHT_BRACE" || token.type === "COMMA");
var paddedValues = /* @__PURE__ */ new Map([
  ["in ", " in "],
  ["instanceof", " instanceof "],
  ["void", "void "]
]);
function render(tokens) {
  let code = "";
  for (const t of tokens) {
    const value = t.isKeyword ? t.value + " " : paddedValues.get(t.value) || t.value;
    const last = code[code.length - 1];
    if ((last === "+" || last === "-") && value[0] === last || last && IDENTIFIER_CHAR_RE.test(last) && IDENTIFIER_CHAR_RE.test(value[0])) {
      code += " ";
    }
    code += value;
  }
  return code;
}
var LEFT_GROUPS = /* @__PURE__ */ new Set(["LEFT_BRACE", "LEFT_BRACKET", "LEFT_PAREN"]);
var RIGHT_GROUPS = /* @__PURE__ */ new Set(["RIGHT_BRACE", "RIGHT_BRACKET", "RIGHT_PAREN"]);
function bindArrowParams(tokens, end, scope) {
  let depth = 0;
  let start = end;
  for (; start >= 0; start--) {
    const type = tokens[start].type;
    if (RIGHT_GROUPS.has(type)) {
      depth++;
    } else if (LEFT_GROUPS.has(type) && !--depth) {
      break;
    }
  }
  const levels = [{ inDefault: false, base: false }];
  for (let k = start + 1; k < end; k++) {
    const t = tokens[k];
    const level = levels[levels.length - 1];
    if (LEFT_GROUPS.has(t.type)) {
      levels.push({ inDefault: level.inDefault, base: level.inDefault });
    } else if (RIGHT_GROUPS.has(t.type)) {
      levels.pop();
    } else if (t.type === "COMMA") {
      level.inDefault = level.base;
    } else if (t.type === "OPERATOR" && t.value === "=") {
      level.inDefault = true;
    } else if (t.type === "SYMBOL" && t.varName && !level.inDefault) {
      scope.add(t.varName);
    }
  }
  for (let k = start + 1; k < end; k++) {
    const t = tokens[k];
    if (t.type === "SYMBOL" && t.varName && scope.has(t.varName)) {
      t.value = `_${t.varName}`;
      t.isLocal = true;
    }
  }
  return start;
}
var DECLARATION_KEYWORDS = /* @__PURE__ */ new Set(["const", "let", "var"]);
function bindBlockDeclarations(tokens, start, scope) {
  let depth = 0;
  for (let k = start + 1; k < tokens.length && depth >= 0; k++) {
    const t = tokens[k];
    if (LEFT_GROUPS.has(t.type)) {
      depth++;
    } else if (RIGHT_GROUPS.has(t.type)) {
      depth--;
    } else if (!depth && t.type === "SYMBOL" && DECLARATION_KEYWORDS.has(t.value) && (tokens[k + 1]?.type === "SYMBOL" || tokens[k + 1]?.type === "LEFT_BRACE" || tokens[k + 1]?.type === "LEFT_BRACKET")) {
      t.isKeyword = true;
      k = bindDeclarators(tokens, k + 1, scope);
    }
  }
}
function bindDeclarators(tokens, start, scope) {
  let depth = 0;
  let inValue = false;
  let k = start;
  for (; k < tokens.length; k++) {
    const t = tokens[k];
    if (LEFT_GROUPS.has(t.type)) {
      if (!depth && !inValue) {
        k = bindPattern(tokens, k, scope);
      } else {
        depth++;
      }
    } else if (RIGHT_GROUPS.has(t.type)) {
      if (!depth--) {
        return k - 1;
      }
    } else if (depth) {
      continue;
    } else if (t.type === "COMMA") {
      inValue = false;
    } else if (t.type === "OPERATOR" && t.value === "=") {
      inValue = true;
    } else if (t.type === "OPERATOR" && t.value === ";") {
      return k;
    } else if (t.type === "SYMBOL" && !inValue) {
      scope.add(t.value);
    }
  }
  return k;
}
function bindPattern(tokens, start, scope) {
  const levels = [];
  let k = start;
  for (; k < tokens.length; k++) {
    const t = tokens[k];
    const level = levels[levels.length - 1];
    if (LEFT_GROUPS.has(t.type)) {
      const prev = tokens[k - 1].type;
      const inExpr = !!level && (level.inExpr || level.isObject && (prev === "LEFT_BRACE" || prev === "COMMA"));
      levels.push({ inExpr, base: inExpr, isObject: t.type === "LEFT_BRACE" });
    } else if (RIGHT_GROUPS.has(t.type)) {
      levels.pop();
      if (!levels.length) {
        return k;
      }
    } else if (t.type === "COMMA") {
      level.inExpr = level.base;
    } else if (t.type === "OPERATOR" && t.value === "=") {
      level.inExpr = true;
    } else if (t.type === "SYMBOL" && !level.inExpr && tokens[k + 1]?.type !== "COLON" && tokens[k - 1].value !== "." && tokens[k - 1].value !== "?.") {
      scope.add(t.value);
    }
  }
  return k;
}
function isAsyncArrow(tokens, i) {
  const prev = tokens[i - 1];
  if (prev?.type === "OPERATOR" && (prev.value === "." || prev.value === "?.")) {
    return false;
  }
  let next = i + 1;
  if (tokens[next]?.type === "LEFT_PAREN") {
    let depth = 0;
    for (; next < tokens.length; next++) {
      const type = tokens[next].type;
      if (LEFT_GROUPS.has(type)) {
        depth++;
      } else if (RIGHT_GROUPS.has(type) && !--depth) {
        break;
      }
    }
  } else if (tokens[next]?.type !== "SYMBOL") {
    return false;
  }
  const arrow = tokens[next + 1];
  return arrow?.type === "OPERATOR" && arrow.value === "=>";
}
function collectVariables(tokens, start) {
  const vars = /* @__PURE__ */ new Set();
  for (let i = start; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.varName && !t.isLocal) {
      vars.add(t.varName);
    }
    for (const v of t.templateVars || []) {
      vars.add(v);
    }
  }
  return [...vars];
}
function processExpr(expr, seededLocals, inAsyncArrow = false) {
  const scopeStack2 = [];
  if (seededLocals?.size || inAsyncArrow) {
    scopeStack2.push({
      vars: seededLocals || /* @__PURE__ */ new Set(),
      depth: -Infinity,
      ternaries: 0,
      isAsync: inAsyncArrow
    });
  }
  const tokens = tokenize(expr);
  let i = 0;
  const stack = [];
  let topLevelArrowIndex = -1;
  let topLevelParams = null;
  function isLocal(name) {
    return scopeStack2.some((s) => s.vars.has(name));
  }
  function innermostScopeAtDepth() {
    const scope = scopeStack2[scopeStack2.length - 1];
    return scope && scope.depth === stack.length ? scope : null;
  }
  while (i < tokens.length) {
    let token = tokens[i];
    let prevToken = tokens[i - 1];
    let nextToken = tokens[i + 1];
    let groupType = stack[stack.length - 1];
    switch (token.type) {
      case "LEFT_BRACE":
        if (prevToken?.value === "=>") {
          stack.push("BLOCK");
          const scope = scopeStack2[scopeStack2.length - 1];
          if (scope) {
            bindBlockDeclarations(tokens, i, scope.vars);
          }
        } else {
          stack.push(token.type);
        }
        break;
      case "LEFT_BRACKET":
      case "LEFT_PAREN":
        stack.push(token.type);
        break;
      case "RIGHT_BRACE":
      case "RIGHT_BRACKET":
      case "RIGHT_PAREN":
        stack.pop();
        while (scopeStack2.length > 0 && stack.length < scopeStack2[scopeStack2.length - 1].depth) {
          scopeStack2.pop();
        }
        break;
      case "COMMA":
        while (innermostScopeAtDepth()) {
          scopeStack2.pop();
        }
        break;
      case "COLON": {
        let scope;
        while (scope = innermostScopeAtDepth()) {
          if (scope.ternaries) {
            scope.ternaries--;
            break;
          }
          scopeStack2.pop();
        }
        break;
      }
      case "OPERATOR":
        if (token.value === ";") {
          while (innermostScopeAtDepth()) {
            scopeStack2.pop();
          }
        } else if (token.value === "?") {
          const scope = innermostScopeAtDepth();
          if (scope) {
            scope.ternaries++;
          }
        }
        break;
    }
    if (token.type === "SYMBOL") {
      if (token.value === "async") {
        token.isKeyword = isAsyncArrow(tokens, i);
      } else if (token.value === "await") {
        token.isKeyword = !!scopeStack2[scopeStack2.length - 1]?.isAsync;
      }
    }
    let isVar = token.type === "SYMBOL" && !token.isKeyword && !RESERVED_WORDS.has(token.value);
    if (isVar) {
      if (prevToken) {
        if (groupType === "LEFT_BRACE" && isLeftSeparator(prevToken) && (isRightSeparator(nextToken) || nextToken?.type === "OPERATOR" && nextToken.value === "=")) {
          tokens.splice(i + 1, 0, { type: "COLON", value: ":" }, { ...token });
          nextToken = tokens[i + 1];
        }
        if (prevToken.type === "OPERATOR" && (prevToken.value === "." || prevToken.value === "?.")) {
          isVar = false;
        } else if (prevToken.type === "LEFT_BRACE" || prevToken.type === "COMMA") {
          if (nextToken && nextToken.type === "COLON") {
            isVar = false;
          }
        }
      }
    }
    if (token.type === "TEMPLATE_STRING") {
      const currentLocals = /* @__PURE__ */ new Set();
      for (const scope of scopeStack2) {
        for (const v of scope.vars) currentLocals.add(v);
      }
      const templateVars = [];
      token.value = token.replace((expr2) => {
        const isAsync = !!scopeStack2[scopeStack2.length - 1]?.isAsync;
        const processed = processExpr(expr2, currentLocals, isAsync);
        templateVars.push(...processed.variables);
        return processed.expr;
      });
      token.templateVars = templateVars;
    }
    if (nextToken && nextToken.type === "OPERATOR" && nextToken.value === "=>") {
      const newScope = /* @__PURE__ */ new Set();
      let paramStart = i;
      let params = [i, i + 1];
      if (token.type === "RIGHT_PAREN") {
        paramStart = bindArrowParams(tokens, i, newScope);
        params = [paramStart + 1, i];
      } else {
        newScope.add(token.value);
      }
      const isAsync = !!tokens[paramStart - 1]?.isKeyword;
      if (paramStart === 0 || paramStart === 1 && isAsync) {
        topLevelArrowIndex = i + 1;
        topLevelParams = params;
      }
      scopeStack2.push({ vars: newScope, depth: stack.length, ternaries: 0, isAsync });
    }
    if (isVar) {
      token.varName = token.value;
      if (!isLocal(token.value)) {
        token.originalValue = token.value;
        token.value = `ctx['${token.value}']`;
      } else {
        token.value = `_${token.value}`;
        token.isLocal = true;
      }
    }
    i++;
  }
  const freeVariables = topLevelArrowIndex === -1 ? null : collectVariables(tokens, topLevelArrowIndex + 1).filter((v) => v !== "this");
  const arrow = topLevelArrowIndex === -1 ? null : {
    isAsync: !!tokens[0].isKeyword,
    params: render(tokens.slice(...topLevelParams)),
    body: render(tokens.slice(topLevelArrowIndex + 1))
  };
  return {
    expr: render(tokens),
    freeVariables,
    variables: collectVariables(tokens, 0),
    arrow
  };
}
function compileExpr(expr, seededLocals) {
  return processExpr(expr, seededLocals).expr;
}
var INTERP_REGEXP = /\{\{.*?\}\}|\#\{.*?\}/g;
var HAS_INTERP_REGEXP = /\{\{.*?\}\}|\#\{.*?\}/;
function isInterpolated(s) {
  return HAS_INTERP_REGEXP.test(s);
}
function escapeTemplateString(str) {
  return str.replace(/\\/g, "\\\\").replace(/`/g, "\\`").replace(/\$\{/g, "\\${");
}
function replaceDynamicParts(s, replacer) {
  let matches = s.match(INTERP_REGEXP);
  if (matches && matches[0].length === s.length) {
    return `(${replacer(s.slice(2, matches[0][0] === "{" ? -2 : -1))})`;
  }
  let r = "";
  let last = 0;
  for (const match of s.matchAll(INTERP_REGEXP)) {
    const part = match[0];
    r += escapeTemplateString(s.slice(last, match.index));
    r += "${" + replacer(part.slice(2, part[0] === "{" ? -2 : -1)) + "}";
    last = match.index + part.length;
  }
  return "`" + r + escapeTemplateString(s.slice(last)) + "`";
}
function interpolate(s) {
  return replaceDynamicParts(s, compileExpr);
}

// ../owl-compiler/src/parse_xml.ts
function parseXML(xml2) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml2, "text/xml");
  if (doc.getElementsByTagName("parsererror").length) {
    let msg = "Invalid XML in template.";
    const parsererrorText = doc.getElementsByTagName("parsererror")[0].textContent;
    if (parsererrorText) {
      msg += "\nThe parser has produced the following error message:\n" + parsererrorText;
      const re = /\d+/g;
      const firstMatch = re.exec(parsererrorText);
      if (firstMatch) {
        const lineNumber = Number(firstMatch[0]);
        const line = xml2.split("\n")[lineNumber - 1];
        const secondMatch = re.exec(parsererrorText);
        if (line && secondMatch) {
          const column = Number(secondMatch[0]);
          if (column >= 1 && column <= line.length) {
            msg += `
The error might be located at xml line ${lineNumber} column ${column}
${line}
${"-".repeat(column - 1)}^`;
          }
        }
      }
    }
    throw new OwlError(msg);
  }
  return doc;
}

// ../owl-compiler/src/parser.ts
var ASTType = {
  Text: 0,
  DomNode: 2,
  Multi: 3,
  TIf: 4,
  TSet: 5,
  TCall: 6,
  TOut: 7,
  TForEach: 8,
  TKey: 9,
  TComponent: 10,
  TDebug: 11,
  TLog: 12,
  TCallSlot: 13,
  TCallBlock: 14,
  TTranslation: 15,
  TTranslationContext: 16
};
var ForEachNoFlag = {
  First: 1,
  Last: 2,
  Index: 4,
  Value: 8
};
var NO_DIRECTIVES = {};
var cache2 = /* @__PURE__ */ new WeakMap();
function parse(xml2, customDir) {
  const ctx = {
    inPreTag: false,
    customDirectives: customDir
  };
  if (typeof xml2 === "string") {
    const elem = parseXML(`<t>${xml2}</t>`).firstChild;
    return _parse(elem, ctx);
  }
  const directivesKey = customDir || NO_DIRECTIVES;
  let astCache = cache2.get(directivesKey);
  if (!astCache) {
    astCache = /* @__PURE__ */ new WeakMap();
    cache2.set(directivesKey, astCache);
  }
  let ast = astCache.get(xml2);
  if (!ast) {
    ast = _parse(xml2.cloneNode(true), ctx);
    astCache.set(xml2, ast);
  }
  return ast;
}
function _parse(xml2, ctx) {
  normalizeXML(xml2);
  return parseNode(xml2, ctx) || { type: ASTType.Text, value: "" };
}
function parseNode(node, ctx) {
  if (!(node instanceof Element)) {
    return parseTextCommentNode(node, ctx);
  }
  return parseTCustom(node, ctx) || parseTDebugLog(node, ctx) || parseTForEach(node, ctx) || parseTIf(node, ctx) || parseTTranslation(node, ctx) || parseTTranslationContext(node, ctx) || parseTKey(node, ctx) || parseTCall(node, ctx) || parseTCallBlock(node, ctx) || parseTOutNode(node, ctx) || parseTCallSlot(node, ctx) || parseComponent(node, ctx) || parseDOMNode(node, ctx) || parseTSetNode(node, ctx) || parseTNode(node, ctx);
}
function isTranslationContext(attribute) {
  return attribute === "t-translation-context" || attribute.startsWith("t-translation-context-");
}
function unsupportedDirectiveError(directive, where) {
  return new OwlError(`Unsupported directive '${directive}' on ${where}`);
}
function tRefError(node) {
  return new OwlError(
    `Directive 't-ref' can only be used on DOM nodes (used on a <${node.tagName}>)`
  );
}
function parseTNode(node, ctx) {
  if (node.tagName !== "t") {
    return null;
  }
  if (node.hasAttribute("t-ref")) {
    throw tRefError(node);
  }
  return parseChildNodes(node, ctx);
}
var lineBreakRE = /[\r\n]/;
var htmlWhitespaceOnlyRE = /^[ \t\n\r\f]*$/;
function parseTextCommentNode(node, ctx) {
  if (node.nodeType === Node.TEXT_NODE) {
    let value = node.textContent || "";
    if (!ctx.inPreTag && lineBreakRE.test(value) && htmlWhitespaceOnlyRE.test(value)) {
      return null;
    }
    return { type: ASTType.Text, value };
  }
  return null;
}
function parseTCustom(node, ctx) {
  if (!ctx.customDirectives) {
    return null;
  }
  const nodeAttrsNames = node.getAttributeNames();
  for (let attr of nodeAttrsNames) {
    if (attr === "t-custom" || attr === "t-custom-") {
      throw new OwlError("Missing custom directive name with t-custom directive");
    }
    if (attr.startsWith("t-custom-")) {
      const directiveName = attr.split(".")[0].slice(9);
      const customDirective = ctx.customDirectives[directiveName];
      if (!customDirective) {
        throw new OwlError(`Custom directive "${directiveName}" is not defined`);
      }
      const value = node.getAttribute(attr);
      const modifiers = attr.split(".").slice(1);
      node.removeAttribute(attr);
      try {
        customDirective(node, value, modifiers);
      } catch (error) {
        throw new OwlError(
          `Custom directive "${directiveName}" throw the following error: ${error}`
        );
      }
      return parseNode(node, ctx);
    }
  }
  return null;
}
function parseTDebugLog(node, ctx) {
  if (node.hasAttribute("t-debug")) {
    node.removeAttribute("t-debug");
    const content = parseNode(node, ctx);
    const ast = {
      type: ASTType.TDebug,
      content
    };
    if (content?.hasNoRepresentation) {
      ast.hasNoRepresentation = true;
    }
    return ast;
  }
  if (node.hasAttribute("t-log")) {
    const expr = node.getAttribute("t-log");
    node.removeAttribute("t-log");
    const content = parseNode(node, ctx);
    const ast = {
      type: ASTType.TLog,
      expr,
      content
    };
    if (content?.hasNoRepresentation) {
      ast.hasNoRepresentation = true;
    }
    return ast;
  }
  return null;
}
var ROOT_SVG_TAGS = /* @__PURE__ */ new Set(["svg", "g", "path"]);
var ATT_DIRECTIVE_RE = /^t-att(f?-.+)?$/;
var T_MODEL_MODIFIERS = /* @__PURE__ */ new Set(["lazy", "trim", "number", "proxy"]);
var SLOT_HIDING_DIRECTIVES = /* @__PURE__ */ new Set([
  "t-if",
  "t-elif",
  "t-else",
  "t-foreach",
  "t-out",
  "t-esc",
  "t-call",
  "t-call-block",
  "t-call-slot",
  "t-slot",
  "t-set"
]);
function parseDOMNode(node, ctx) {
  const { tagName } = node;
  const dynamicTag = node.getAttribute("t-tag");
  node.removeAttribute("t-tag");
  if (tagName === "t" && !dynamicTag) {
    return null;
  }
  if (tagName.startsWith("block-")) {
    throw new OwlError(`Invalid tag name: '${tagName}'`);
  }
  ctx = Object.assign({}, ctx);
  if (tagName === "pre") {
    ctx.inPreTag = true;
  }
  let ns = !ctx.nameSpace && ROOT_SVG_TAGS.has(tagName) ? "http://www.w3.org/2000/svg" : null;
  const ref2 = node.getAttribute("t-ref");
  node.removeAttribute("t-ref");
  const nodeAttrsNames = node.getAttributeNames();
  let attrs = null;
  let attrsTranslationCtx = null;
  let on = null;
  let model = null;
  for (let attr of nodeAttrsNames) {
    const value = node.getAttribute(attr);
    if (attr === "t-on" || attr === "t-on-") {
      throw new OwlError("Missing event name with t-on directive");
    }
    if (attr.startsWith("t-on-")) {
      on = on || {};
      on[attr.slice(5)] = value;
    } else if (attr === "t-model" || attr.startsWith("t-model.")) {
      if (!["input", "select", "textarea"].includes(tagName)) {
        throw new OwlError(
          "The t-model directive only works with <input>, <textarea> and <select>"
        );
      }
      const typeAttr = node.getAttribute("type");
      const isInput = tagName === "input";
      const isSelect = tagName === "select";
      const isCheckboxInput = isInput && typeAttr === "checkbox";
      const isRadioInput = isInput && typeAttr === "radio";
      const modifiers = attr.split(".").slice(1);
      for (const modifier of modifiers) {
        if (!T_MODEL_MODIFIERS.has(modifier)) {
          throw new OwlError(`Unknown t-model modifier: '${modifier}'`);
        }
      }
      const hasTrimMod = modifiers.includes("trim");
      const hasLazyMod = hasTrimMod || modifiers.includes("lazy");
      const hasNumberMod = modifiers.includes("number");
      const hasProxyMod = modifiers.includes("proxy");
      const eventType = isRadioInput ? "click" : isSelect || hasLazyMod ? "change" : "input";
      model = {
        expr: value,
        targetAttr: isCheckboxInput ? "checked" : "value",
        specialInitTargetAttr: isRadioInput ? "checked" : null,
        eventType,
        hasDynamicChildren: false,
        shouldTrim: hasTrimMod,
        shouldNumberize: hasNumberMod,
        isProxy: hasProxyMod
      };
      if (isSelect) {
        ctx = Object.assign({}, ctx);
        ctx.tModelInfo = model;
      }
    } else if (attr.startsWith("block-")) {
      throw new OwlError(`Invalid attribute: '${attr}'`);
    } else if (attr === "xmlns") {
      ns = value;
    } else if (attr.startsWith("t-translation-context-")) {
      const attrName = attr.slice(22);
      attrsTranslationCtx = attrsTranslationCtx || {};
      attrsTranslationCtx[attrName] = value;
    } else if (attr !== "t-name") {
      if (attr.startsWith("t-") && !ATT_DIRECTIVE_RE.test(attr)) {
        throw new OwlError(`Unknown QWeb directive: '${attr}'`);
      }
      const tModel = ctx.tModelInfo;
      if (tModel && ["t-att-value", "t-attf-value"].includes(attr)) {
        tModel.hasDynamicChildren = true;
      }
      attrs = attrs || {};
      attrs[attr] = value;
    }
  }
  if (ns) {
    ctx.nameSpace = ns;
  }
  const children = parseChildren(node, ctx);
  return {
    type: ASTType.DomNode,
    tag: tagName,
    dynamicTag,
    attrs,
    attrsTranslationCtx,
    on,
    ref: ref2,
    content: children,
    model,
    ns
  };
}
function parseTOutNode(node, ctx) {
  if (!node.hasAttribute("t-out") && !node.hasAttribute("t-esc")) {
    return null;
  }
  if (node.hasAttribute("t-esc")) {
    console.warn(
      `t-esc has been deprecated in favor of t-out. If the value to render is not wrapped by the "markup" function, it will be escaped`
    );
  }
  const expr = node.getAttribute("t-out") || node.getAttribute("t-esc");
  node.removeAttribute("t-out");
  node.removeAttribute("t-esc");
  const tOut = { type: ASTType.TOut, expr, body: null };
  if (node.tagName === "t" && !node.hasAttribute("t-tag")) {
    if (node.hasAttribute("t-ref")) {
      throw tRefError(node);
    }
    const directive = node.getAttributeNames().find((a) => a.startsWith("t-") && a !== "t-name" && !isTranslationContext(a));
    if (directive) {
      throw unsupportedDirectiveError(directive, "a <t> with t-out");
    }
    const body = parseChildren(node, ctx);
    tOut.body = body.length ? body : null;
    return tOut;
  }
  const ref2 = node.getAttribute("t-ref");
  node.removeAttribute("t-ref");
  const ast = parseNode(node, ctx);
  if (ast?.type !== ASTType.DomNode) {
    throw new OwlError(`t-out cannot be used on a <${node.tagName}> with this combination`);
  }
  tOut.body = ast.content.length ? ast.content : null;
  return {
    ...ast,
    ref: ref2,
    content: [tOut]
  };
}
function parseTForEach(node, ctx) {
  if (!node.hasAttribute("t-foreach")) {
    return null;
  }
  const html2 = node.outerHTML;
  const collection = node.getAttribute("t-foreach");
  node.removeAttribute("t-foreach");
  const elem = node.getAttribute("t-as");
  if (!elem) {
    throw new OwlError(
      `Directive t-foreach should always be used with t-as (expression: t-foreach="${collection}")`
    );
  }
  node.removeAttribute("t-as");
  const key = node.getAttribute("t-key");
  if (!key) {
    throw new OwlError(
      `"Directive t-foreach should always be used with a t-key!" (expression: t-foreach="${collection}" t-as="${elem}")`
    );
  }
  node.removeAttribute("t-key");
  const memo = node.getAttribute("t-memo");
  node.removeAttribute("t-memo");
  const body = parseNode(node, ctx);
  if (!body) {
    return null;
  }
  if (memo !== null) {
    const directive = findDirective(body, UNVISITABLE);
    if (body.hasNoRepresentation || directive) {
      throw new OwlError(
        `t-memo needs an item made of elements, text, t-out and components only (expression: t-foreach="${collection}" t-memo="${memo}"${directive ? `, found ${directive}` : ""})`
      );
    }
  }
  const hasNoTCall = !/\st-call="/.test(html2);
  let noFlags = 0;
  if (hasNoTCall && !html2.includes(`${elem}_first`)) noFlags |= ForEachNoFlag.First;
  if (hasNoTCall && !html2.includes(`${elem}_last`)) noFlags |= ForEachNoFlag.Last;
  if (hasNoTCall && !html2.includes(`${elem}_index`)) noFlags |= ForEachNoFlag.Index;
  if (hasNoTCall && !html2.includes(`${elem}_value`)) noFlags |= ForEachNoFlag.Value;
  const ast = {
    type: ASTType.TForEach,
    collection,
    elem,
    body,
    key,
    noFlags
  };
  if (memo !== null) {
    ast.memo = memo;
    if (findDirective(body, COMPONENT) || hasMemoizedLoop(body)) {
      ast.memoContent = true;
    }
  }
  if (body.hasNoRepresentation) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
var UNVISITABLE = {
  [ASTType.TCall]: "t-call",
  [ASTType.TCallSlot]: "t-slot",
  [ASTType.TCallBlock]: "t-call-block"
};
var COMPONENT = { [ASTType.TComponent]: "a component" };
function findDirective(value, directives) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found2 = findDirective(item, directives);
      if (found2) {
        return found2;
      }
    }
    return null;
  }
  if (!value || typeof value !== "object") {
    return null;
  }
  const found = typeof value.type === "number" && directives[value.type];
  if (found) {
    return found;
  }
  for (const key in value) {
    const inner = findDirective(value[key], directives);
    if (inner) {
      return inner;
    }
  }
  return null;
}
function hasMemoizedLoop(value) {
  if (Array.isArray(value)) {
    return value.some(hasMemoizedLoop);
  }
  if (!value || typeof value !== "object") {
    return false;
  }
  if (value.type === ASTType.TForEach && value.memo !== void 0) {
    return true;
  }
  for (const key in value) {
    if (hasMemoizedLoop(value[key])) {
      return true;
    }
  }
  return false;
}
function parseTKey(node, ctx) {
  if (!node.hasAttribute("t-key")) {
    return null;
  }
  const key = node.getAttribute("t-key");
  node.removeAttribute("t-key");
  const content = parseNode(node, ctx);
  if (!content) {
    return null;
  }
  const ast = {
    type: ASTType.TKey,
    expr: key,
    content
  };
  if (content.hasNoRepresentation) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
function parseTCall(node, ctx) {
  if (!node.hasAttribute("t-call")) {
    return null;
  }
  if (node.tagName !== "t") {
    throw new OwlError(
      `Directive 't-call' can only be used on <t> nodes (used on a <${node.tagName}>)`
    );
  }
  const subTemplate = node.getAttribute("t-call");
  const context = node.getAttribute("t-call-context");
  node.removeAttribute("t-call");
  node.removeAttribute("t-call-context");
  let attrs = null;
  let attrsTranslationCtx = null;
  for (let attributeName of node.getAttributeNames()) {
    const value = node.getAttribute(attributeName);
    if (attributeName.startsWith("t-translation-context-")) {
      const attrName = attributeName.slice(22);
      attrsTranslationCtx = attrsTranslationCtx || {};
      attrsTranslationCtx[attrName] = value;
    } else if (attributeName.startsWith("t-")) {
      throw unsupportedDirectiveError(attributeName, "a t-call node");
    } else {
      attrs = attrs || {};
      attrs[attributeName] = value;
    }
  }
  const body = parseChildNodes(node, ctx);
  return {
    type: ASTType.TCall,
    name: subTemplate,
    attrs,
    attrsTranslationCtx,
    body,
    context
  };
}
function parseTCallBlock(node, ctx) {
  if (!node.hasAttribute("t-call-block")) {
    return null;
  }
  const name = node.getAttribute("t-call-block");
  const directive = node.getAttributeNames().find((a) => a.startsWith("t-") && a !== "t-call-block" && !isTranslationContext(a));
  if (directive) {
    throw unsupportedDirectiveError(directive, "a t-call-block node");
  }
  return {
    type: ASTType.TCallBlock,
    name
  };
}
function parseTIf(node, ctx) {
  if (!node.hasAttribute("t-if")) {
    return null;
  }
  const condition = node.getAttribute("t-if");
  node.removeAttribute("t-if");
  const content = parseNode(node, ctx) || { type: ASTType.Text, value: "" };
  let nextElement = node.nextElementSibling;
  const tElifs = [];
  while (nextElement && nextElement.hasAttribute("t-elif")) {
    const condition2 = nextElement.getAttribute("t-elif");
    nextElement.removeAttribute("t-elif");
    const tElif = parseNode(nextElement, ctx) || { type: ASTType.Text, value: "" };
    const next = nextElement.nextElementSibling;
    nextElement.remove();
    nextElement = next;
    tElifs.push({ condition: condition2, content: tElif });
  }
  let tElse = null;
  if (nextElement && nextElement.hasAttribute("t-else")) {
    nextElement.removeAttribute("t-else");
    tElse = parseNode(nextElement, ctx);
    nextElement.remove();
  }
  return {
    type: ASTType.TIf,
    condition,
    content,
    tElif: tElifs.length ? tElifs : null,
    tElse
  };
}
function parseTSetNode(node, ctx) {
  if (!node.hasAttribute("t-set")) {
    return null;
  }
  const name = node.getAttribute("t-set");
  const value = node.getAttribute("t-value") || null;
  const isText = [...node.childNodes].every(
    (n) => n.nodeType === Node.TEXT_NODE || n.nodeType === Node.COMMENT_NODE
  );
  let defaultValue = null;
  let body = null;
  if (isText) {
    defaultValue = node.textContent || null;
  } else {
    const content = parseChildren(node, ctx);
    body = content.length ? content : null;
  }
  return { type: ASTType.TSet, name, value, defaultValue, body, hasNoRepresentation: true };
}
var directiveErrorMap = /* @__PURE__ */ new Map([
  [
    "t-ref",
    "t-ref is no longer supported on components. Consider exposing only the public part of the component's API through a callback prop."
  ],
  ["t-att", "t-att makes no sense on component: props are already treated as expressions"],
  [
    "t-attf",
    "t-attf is not supported on components: use template strings for string interpolation in props"
  ]
]);
function parseComponent(node, ctx) {
  let name = node.tagName;
  const firstLetter = name[0];
  let isDynamic = node.hasAttribute("t-component");
  if (isDynamic && name !== "t") {
    throw new OwlError(
      `Directive 't-component' can only be used on <t> nodes (used on a <${name}>)`
    );
  }
  if (!(firstLetter === firstLetter.toUpperCase() || isDynamic)) {
    return null;
  }
  if (isDynamic) {
    name = node.getAttribute("t-component");
    node.removeAttribute("t-component");
  }
  const dynamicProps = node.getAttribute("t-props");
  node.removeAttribute("t-props");
  const defaultSlotScope = node.getAttribute("t-slot-scope");
  node.removeAttribute("t-slot-scope");
  let on = null;
  let props2 = null;
  let propsTranslationCtx = null;
  for (let name2 of node.getAttributeNames()) {
    const value = node.getAttribute(name2);
    if (name2.startsWith("t-translation-context-")) {
      const attrName = name2.slice(22);
      propsTranslationCtx = propsTranslationCtx || {};
      propsTranslationCtx[attrName] = value;
    } else if (name2.startsWith("t-")) {
      if (name2.startsWith("t-on-")) {
        on = on || {};
        on[name2.slice(5)] = value;
      } else {
        const message = directiveErrorMap.get(name2.split("-").slice(0, 2).join("-"));
        throw new OwlError(message || `unsupported directive on Component: ${name2}`);
      }
    } else {
      props2 = props2 || {};
      props2[name2] = value;
    }
  }
  let slots = null;
  if (node.hasChildNodes()) {
    const clone = node.cloneNode(true);
    const slotNodes = Array.from(clone.querySelectorAll("[t-set-slot]"));
    for (let slotNode of slotNodes) {
      if (slotNode.tagName !== "t") {
        throw new OwlError(
          `Directive 't-set-slot' can only be used on <t> nodes (used on a <${slotNode.tagName}>)`
        );
      }
      const name2 = slotNode.getAttribute("t-set-slot");
      let el = slotNode.parentElement;
      let isInSubComponent = false;
      let directiveAbove = null;
      while (el && el !== clone) {
        if (el.hasAttribute("t-component") || el.tagName[0] === el.tagName[0].toUpperCase()) {
          isInSubComponent = true;
          break;
        }
        const directive = el.getAttributeNames().find((a) => SLOT_HIDING_DIRECTIVES.has(a));
        if (directive && !directiveAbove) {
          directiveAbove = `${directive} on a <${el.tagName}>`;
        }
        el = el.parentElement;
      }
      if (isInSubComponent || !el) {
        continue;
      }
      if (directiveAbove) {
        throw new OwlError(
          `Directive 't-set-slot' cannot be used under a directive (${directiveAbove}) inside a component`
        );
      }
      slotNode.removeAttribute("t-set-slot");
      slotNode.remove();
      let on2 = null;
      let attrs = null;
      let attrsTranslationCtx = null;
      let scope = null;
      const isT = slotNode.tagName === "t";
      for (let attributeName of slotNode.getAttributeNames()) {
        const value = slotNode.getAttribute(attributeName);
        if (attributeName === "t-slot-scope") {
          scope = value;
        } else if (attributeName.startsWith("t-translation-context-")) {
          const attrName = attributeName.slice(22);
          attrsTranslationCtx = attrsTranslationCtx || {};
          attrsTranslationCtx[attrName] = value;
        } else if (attributeName.startsWith("t-on-")) {
          on2 = on2 || {};
          on2[attributeName.slice(5)] = value;
        } else {
          continue;
        }
        if (isT) {
          slotNode.removeAttribute(attributeName);
        }
      }
      const slotAst = parseNode(slotNode, ctx);
      for (let attributeName of slotNode.getAttributeNames()) {
        if (attributeName === "t-slot-scope" || attributeName.startsWith("t-translation-context-") || attributeName.startsWith("t-on-")) {
          continue;
        }
        attrs = attrs || {};
        attrs[attributeName] = slotNode.getAttribute(attributeName);
      }
      slots = slots || {};
      slots[name2] = { content: slotAst, on: on2, attrs, attrsTranslationCtx, scope };
    }
    const defaultContent = parseChildNodes(clone, ctx);
    slots = slots || {};
    if (defaultContent && !slots.default) {
      slots.default = {
        content: defaultContent,
        on: null,
        attrs: null,
        attrsTranslationCtx: null,
        scope: defaultSlotScope
      };
    }
  }
  return {
    type: ASTType.TComponent,
    name,
    isDynamic,
    dynamicProps,
    props: props2,
    propsTranslationCtx,
    slots,
    on
  };
}
function parseTCallSlot(node, ctx) {
  if (!node.hasAttribute("t-call-slot") && !node.hasAttribute("t-slot")) {
    return null;
  }
  if (node.hasAttribute("t-slot")) {
    console.warn(`t-slot has been renamed t-call-slot.`);
  }
  const name = node.getAttribute("t-call-slot") || node.getAttribute("t-slot");
  node.removeAttribute("t-call-slot");
  node.removeAttribute("t-slot");
  let attrs = null;
  let attrsTranslationCtx = null;
  let on = null;
  for (let attributeName of node.getAttributeNames()) {
    const value = node.getAttribute(attributeName);
    if (attributeName.startsWith("t-on-")) {
      on = on || {};
      on[attributeName.slice(5)] = value;
    } else if (attributeName.startsWith("t-translation-context-")) {
      const attrName = attributeName.slice(22);
      attrsTranslationCtx = attrsTranslationCtx || {};
      attrsTranslationCtx[attrName] = value;
    } else if (attributeName.startsWith("t-") && attributeName !== "t-props") {
      throw unsupportedDirectiveError(attributeName, "a t-call-slot node");
    } else {
      attrs = attrs || {};
      attrs[attributeName] = value;
    }
  }
  return {
    type: ASTType.TCallSlot,
    name,
    attrs,
    attrsTranslationCtx,
    on,
    defaultContent: parseChildNodes(node, ctx)
  };
}
function wrapInTTranslationAST(r) {
  const ast = { type: ASTType.TTranslation, content: r };
  if (r?.hasNoRepresentation) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
function parseTTranslation(node, ctx) {
  if (node.getAttribute("t-translation") !== "off") {
    return null;
  }
  node.removeAttribute("t-translation");
  const result = parseNode(node, ctx);
  if (result?.type === ASTType.Multi) {
    const children = result.content.map(wrapInTTranslationAST);
    return makeASTMulti(children);
  }
  return wrapInTTranslationAST(result);
}
function wrapInTTranslationContextAST(r, translationCtx) {
  const ast = {
    type: ASTType.TTranslationContext,
    content: r,
    translationCtx
  };
  if (r?.hasNoRepresentation) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
function parseTTranslationContext(node, ctx) {
  const translationCtx = node.getAttribute("t-translation-context");
  if (!translationCtx) {
    return null;
  }
  node.removeAttribute("t-translation-context");
  const result = parseNode(node, ctx);
  if (result?.type === ASTType.Multi) {
    const children = result.content.map((c) => wrapInTTranslationContextAST(c, translationCtx));
    return makeASTMulti(children);
  }
  return wrapInTTranslationContextAST(result, translationCtx);
}
function parseChildren(node, ctx) {
  const children = [];
  for (let child of node.childNodes) {
    const childAst = parseNode(child, ctx);
    if (childAst) {
      if (childAst.type === ASTType.Multi) {
        children.push(...childAst.content);
      } else {
        children.push(childAst);
      }
    }
  }
  return children;
}
function makeASTMulti(children) {
  const ast = { type: ASTType.Multi, content: children };
  if (children.every((c) => c.hasNoRepresentation)) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
function parseChildNodes(node, ctx) {
  const children = parseChildren(node, ctx);
  switch (children.length) {
    case 0:
      return null;
    case 1:
      return children[0];
    default:
      return makeASTMulti(children);
  }
}
function normalizeTIf(el) {
  let tbranch = el.querySelectorAll("[t-elif], [t-else]");
  for (let i = 0, ilen = tbranch.length; i < ilen; i++) {
    let node = tbranch[i];
    let prevElem = node.previousElementSibling;
    let pattr = (name) => prevElem.hasAttribute(name);
    let nattr = (name) => +node.hasAttribute(name);
    if (prevElem && (pattr("t-if") || pattr("t-elif"))) {
      if (pattr("t-foreach")) {
        throw new OwlError(
          "t-if cannot stay at the same level as t-foreach when using t-elif or t-else"
        );
      }
      const elseIf = node.hasAttribute("t-else") && node.hasAttribute("t-if");
      if (!(elseIf && !node.hasAttribute("t-elif")) && ["t-if", "t-elif", "t-else"].map(nattr).reduce(function(a, b) {
        return a + b;
      }) > 1) {
        throw new OwlError("Only one conditional branching directive is allowed per node");
      }
      let textNode;
      while ((textNode = node.previousSibling) !== prevElem) {
        if (textNode.nodeValue.trim().length && textNode.nodeType !== 8) {
          throw new OwlError("text is not allowed between branching directives");
        }
        textNode.remove();
      }
    } else {
      throw new OwlError(
        "t-elif and t-else directives must be preceded by a t-if or t-elif directive"
      );
    }
  }
}
function normalizeTOut(el) {
  const elements = [...el.querySelectorAll(`[t-out], [t-esc]`)].filter(
    (el2) => el2.tagName[0] === el2.tagName[0].toUpperCase() || el2.hasAttribute("t-component")
  );
  for (const el2 of elements) {
    if (el2.childNodes.length) {
      throw new OwlError(`Cannot have t-out on a component that already has content`);
    }
    const directive = el2.hasAttribute("t-out") ? "t-out" : "t-esc";
    const value = el2.getAttribute(directive);
    el2.removeAttribute(directive);
    const t = el2.ownerDocument.createElement("t");
    t.setAttribute(directive, value);
    el2.appendChild(t);
  }
}
function normalizeXML(el) {
  normalizeTIf(el);
  normalizeTOut(el);
}

// ../owl-compiler/src/code_generator.ts
var zero = /* @__PURE__ */ Symbol("zero");
var MAX_LAZY_LOOP_KEYS = 3;
var whitespaceRE = /[ \t\n\r\f]+/g;
var xmlDoc;
if (typeof document !== "undefined") {
  xmlDoc = document.implementation.createDocument(null, null, null);
}
var MODS = /* @__PURE__ */ new Set(["stop", "capture", "prevent", "self", "synthetic", "passive"]);
function isProp(tag, key) {
  switch (tag) {
    case "input":
      return key === "checked" || key === "indeterminate" || key === "value" || key === "readonly" || key === "readOnly" || key === "disabled";
    case "option":
      return key === "selected" || key === "disabled";
    case "textarea":
      return key === "value" || key === "readonly" || key === "readOnly" || key === "disabled";
    case "select":
      return key === "value" || key === "disabled";
    case "button":
    case "optgroup":
      return key === "disabled";
  }
  return false;
}
function toStringExpression(str) {
  return `\`${escapeTemplateString(str)}\``;
}
var BlockDescription = class {
  varName;
  blockName;
  dynamicTagName = null;
  isRoot = false;
  hasDynamicChildren = false;
  children = [];
  data = [];
  dom;
  currentDom;
  target;
  type;
  parentVar = "";
  id;
  generateId;
  constructor(id, target, type, generateId) {
    this.id = id;
    this.generateId = generateId;
    this.varName = "b" + this.id;
    this.blockName = "block" + this.id;
    this.target = target;
    this.type = type;
  }
  insertData(str, prefix = "d") {
    const id = this.generateId(prefix);
    this.target.addLine(`let ${id} = ${str};`);
    return this.data.push(id) - 1;
  }
  insert(dom) {
    if (this.currentDom) {
      this.currentDom.appendChild(dom);
    } else {
      this.dom = dom;
    }
  }
  generateExpr(expr) {
    if (this.type === "block") {
      const hasChildren = this.children.length;
      let params = this.data.length ? `[${this.data.join(", ")}]` : hasChildren ? "[]" : "";
      if (hasChildren) {
        params += ", [" + this.children.map((c) => c.varName).join(", ") + "]";
      }
      if (this.dynamicTagName) {
        return `toggler(${this.dynamicTagName}, ${this.blockName}(${this.dynamicTagName})(${params}))`;
      }
      return `${this.blockName}(${params})`;
    } else if (this.type === "list") {
      return `list(c_block${this.id})`;
    }
    return expr;
  }
  asXmlString() {
    const t = xmlDoc.createElement("t");
    t.appendChild(this.dom);
    return t.innerHTML;
  }
};
function createContext2(parentCtx, params) {
  return Object.assign(
    {
      block: null,
      index: 0,
      forceNewBlock: true,
      translate: parentCtx.translate,
      translationCtx: parentCtx.translationCtx,
      tKeyExpr: null,
      nameSpace: parentCtx.nameSpace,
      tModelSelectedExpr: parentCtx.tModelSelectedExpr,
      inPreTag: parentCtx.inPreTag
    },
    params
  );
}
var CodeTarget = class {
  name;
  indentLevel = 0;
  loopLevel = 0;
  loopCtxVars = [];
  // loop levels whose key is concatenated into a string key: they get a
  // `skey<level>` that tells object keys apart
  stringKeyLevels = /* @__PURE__ */ new Set();
  tSetVars = /* @__PURE__ */ new Map();
  // the loop levels whose item is memoized: a memo hit skips the item's body
  memoLevels = [];
  code = [];
  hasRoot = false;
  deferReturn = false;
  needsScopeProtection = false;
  on;
  constructor(name, on) {
    this.name = name;
    this.on = on || null;
  }
  addLine(line, idx) {
    const prefix = new Array(this.indentLevel + 2).join("  ");
    if (idx === void 0) {
      this.code.push(prefix + line);
    } else {
      this.code.splice(idx, 0, prefix + line);
    }
  }
  generateCode() {
    let result = [];
    result.push(`function ${this.name}(ctx, node, key = "") {`);
    if (this.needsScopeProtection) {
      result.push(`  ctx = Object.create(ctx);`);
    }
    for (let line of this.code) {
      result.push(line);
    }
    if (!this.hasRoot) {
      result.push(`return text('');`);
    }
    result.push(`}`);
    return result.join("\n  ");
  }
  currentKey(ctx) {
    if (!this.loopLevel) {
      return ctx.tKeyExpr ? `${ctx.tKeyExpr} + key` : "key";
    }
    if (ctx.tKeyExpr) {
      return `${ctx.tKeyExpr} + ${this.stringKey(this.loopLevel)}`;
    }
    return `key${this.loopLevel}`;
  }
  stringKey(level) {
    this.stringKeyLevels.add(level);
    return `skey${level}`;
  }
};
var TRANSLATABLE_ATTRS = [
  "alt",
  "aria-label",
  "aria-placeholder",
  "aria-roledescription",
  "aria-valuetext",
  "label",
  "placeholder",
  "title"
];
var translationRE = /^(\s*)([\s\S]+?)(\s*)$/;
var CodeGenerator = class {
  blocks = [];
  isDebug = false;
  targets = [];
  target = new CodeTarget("template");
  templateName;
  dev;
  translateFn;
  translatableAttributes = TRANSLATABLE_ATTRS;
  ast;
  staticDefs = [];
  hoistedHandlers = /* @__PURE__ */ new Map();
  slotNames = /* @__PURE__ */ new Set();
  helpers = /* @__PURE__ */ new Set();
  // per generator, so that generating a template (a translateFn may compile
  // another) never shifts the names of the one in progress
  nextBlockId = 1;
  nextDataIds = {};
  generateId = (prefix = "") => {
    const n = (this.nextDataIds[prefix] || 0) + 1;
    this.nextDataIds[prefix] = n;
    return prefix + n;
  };
  constructor(ast, options) {
    this.translateFn = options.translateFn || ((s) => s);
    if (options.translatableAttributes) {
      const attrs = new Set(TRANSLATABLE_ATTRS);
      for (let attr of options.translatableAttributes) {
        if (attr.startsWith("-")) {
          attrs.delete(attr.slice(1));
        } else {
          attrs.add(attr);
        }
      }
      this.translatableAttributes = [...attrs];
    }
    this.dev = options.dev || false;
    this.ast = ast;
    this.templateName = options.name;
    if (options.name) {
      const name = options.name.replace(/[^a-zA-Z0-9_$]/g, "_");
      this.target.name = options.name.startsWith("__") ? name : `template_${name}`;
    }
    if (options.hasGlobalValues) {
      this.helpers.add("__globals__");
    }
  }
  generateCode() {
    const ast = this.ast;
    this.isDebug = ast.type === ASTType.TDebug;
    this.compileAST(ast, {
      block: null,
      index: 0,
      forceNewBlock: false,
      translate: true,
      translationCtx: "",
      tKeyExpr: null
    });
    let mainCode = [`  let { text, createBlock, list, multi, html, toggler } = bdom;`];
    if (this.helpers.size) {
      mainCode.push(`let { ${[...this.helpers].join(", ")} } = helpers;`);
    }
    if (this.templateName) {
      const name = JSON.stringify(this.templateName).replace(/[\u2028\u2029]/g, " ");
      mainCode.push(`// Template name: ${name}`);
    }
    for (let { id, expr } of this.staticDefs) {
      mainCode.push(`const ${id} = ${expr};`);
    }
    if (this.blocks.length) {
      mainCode.push(``);
      for (let block of this.blocks) {
        let xmlString = toStringExpression(block.asXmlString());
        if (block.dynamicTagName) {
          const name = block.dom.nodeName;
          const tag = `\${tag || '${name}'}`;
          const close = `</${name}>\``;
          xmlString = `\`<${tag}` + xmlString.slice(`\`<${name}`.length);
          if (xmlString.endsWith(close)) {
            xmlString = xmlString.slice(0, -close.length) + `</${tag}>\``;
          }
          mainCode.push(`let ${block.blockName} = tag => createBlock(${xmlString});`);
        } else {
          mainCode.push(`let ${block.blockName} = createBlock(${xmlString});`);
        }
      }
    }
    if (this.targets.length) {
      for (let fn of this.targets) {
        mainCode.push("");
        mainCode = mainCode.concat(fn.generateCode());
      }
    }
    mainCode.push("");
    mainCode = mainCode.concat("return " + this.target.generateCode());
    const code = mainCode.join("\n  ");
    if (this.isDebug) {
      const msg = `[Owl Debug]
${code}`;
      console.log(msg);
    }
    return code;
  }
  compileInNewTarget(prefix, ast, ctx, on) {
    const name = this.generateId(prefix);
    const initialTarget = this.target;
    const target = new CodeTarget(name, on);
    this.targets.push(target);
    this.target = target;
    this.compileAST(ast, createContext2(ctx, { tModelSelectedExpr: void 0 }));
    this.target = initialTarget;
    return name;
  }
  addLine(line, idx) {
    this.target.addLine(line, idx);
  }
  define(varName, expr) {
    this.addLine(`const ${varName} = ${expr};`);
  }
  insertAnchor(block) {
    const tag = `block-child-${block.children.length}`;
    const anchor = xmlDoc.createElement(tag);
    block.insert(anchor);
  }
  createBlock(parentBlock, type) {
    const hasRoot = this.target.hasRoot;
    const block = new BlockDescription(this.nextBlockId++, this.target, type, this.generateId);
    if (!hasRoot) {
      this.target.hasRoot = true;
      block.isRoot = true;
    }
    if (parentBlock) {
      if (parentBlock.type === "block") {
        this.insertAnchor(parentBlock);
      }
      parentBlock.children.push(block);
      if (parentBlock.type === "list") {
        block.parentVar = `c_block${parentBlock.id}`;
      }
    }
    return block;
  }
  // a dom block or a list builds its own expression
  insertBlock(block, ctx, expression) {
    let blockExpr = block.generateExpr(expression);
    if (block.parentVar) {
      let key = this.target.currentKey(ctx);
      this.helpers.add("withKey");
      this.addLine(`${block.parentVar}[${ctx.index}] = withKey(${blockExpr}, ${key});`);
      return;
    }
    if (ctx.tKeyExpr) {
      blockExpr = `toggler(${ctx.tKeyExpr}, ${blockExpr})`;
    }
    if (block.isRoot && !this.target.deferReturn) {
      this.emitRootReturn(blockExpr);
    } else {
      this.define(block.varName, blockExpr);
    }
  }
  emitRootReturn(expr) {
    if (this.target.on) {
      expr = this.wrapWithEventCatcher(expr, this.target.on);
    }
    this.addLine(`return ${expr};`);
  }
  translate(str, translationCtx) {
    if (!str.trim()) {
      return str;
    }
    const match = translationRE.exec(str);
    return match[1] + this.translateFn(match[2], translationCtx) + match[3];
  }
  /**
   * @returns the newly created block name, if any
   */
  compileAST(ast, ctx) {
    switch (ast.type) {
      case ASTType.Text:
        return this.compileText(ast, ctx);
      case ASTType.DomNode:
        return this.compileTDomNode(ast, ctx);
      case ASTType.TOut:
        return this.compileTOut(ast, ctx);
      case ASTType.TIf:
        return this.compileTIf(ast, ctx);
      case ASTType.TForEach:
        return this.compileTForeach(ast, ctx);
      case ASTType.TKey:
        return this.compileTKey(ast, ctx);
      case ASTType.Multi:
        return this.compileMulti(ast, ctx);
      case ASTType.TCall:
        return this.compileTCall(ast, ctx);
      case ASTType.TCallBlock:
        return this.compileTCallBlock(ast, ctx);
      case ASTType.TSet:
        return this.compileTSet(ast, ctx);
      case ASTType.TComponent:
        return this.compileComponent(ast, ctx);
      case ASTType.TDebug:
        return this.compileDebug(ast, ctx);
      case ASTType.TLog:
        return this.compileLog(ast, ctx);
      case ASTType.TCallSlot:
        return this.compileTCallSlot(ast, ctx);
      case ASTType.TTranslation:
        return this.compileTTranslation(ast, ctx);
      case ASTType.TTranslationContext:
        return this.compileTTranslationContext(ast, ctx);
    }
  }
  compileDebug(ast, ctx) {
    this.addLine(`debugger;`);
    if (ast.content) {
      return this.compileAST(ast.content, ctx);
    }
    return null;
  }
  compileLog(ast, ctx) {
    this.addLine(`console.log(${compileExpr(ast.expr)});`);
    if (ast.content) {
      return this.compileAST(ast.content, ctx);
    }
    return null;
  }
  compileText(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    let value = ast.value;
    if (value && ctx.translate !== false) {
      value = this.translate(value, ctx.translationCtx);
    }
    if (!ctx.inPreTag) {
      value = value.replace(whitespaceRE, " ");
    }
    if (!block || forceNewBlock) {
      block = this.createBlock(block, "text");
      this.insertBlock(block, ctx, `text(${toStringExpression(value)})`);
    } else {
      block.insert(xmlDoc.createTextNode(value));
    }
    return block.varName;
  }
  generateHandlerCode(rawEvent, handler) {
    const modifiers = rawEvent.split(".").slice(1);
    const selfIndex = modifiers.indexOf("self");
    let mask = 0;
    modifiers.forEach((m, i) => {
      if (!MODS.has(m)) {
        throw new OwlError(`Unknown event modifier: '${m}'`);
      }
      const beforeSelf = i < selfIndex;
      if (m === "self") {
        mask |= EventModifier.SELF;
      } else if (m === "prevent") {
        mask |= beforeSelf ? EventModifier.PREVENT_ANY : EventModifier.PREVENT;
      } else if (m === "stop") {
        mask |= beforeSelf ? EventModifier.STOP_ANY : EventModifier.STOP;
      }
    });
    const modifiersCode = mask ? `, ${mask}` : "";
    const { expr: compiled, arrow } = processExpr(handler);
    if (!compiled.trim()) {
      return `[null, ctx${modifiersCode}]`;
    }
    let hoistedExpr;
    if (arrow) {
      const params = arrow.params ? `ctx,${arrow.params}` : "ctx";
      hoistedExpr = `${arrow.isAsync ? "async " : ""}(${params})=>${arrow.body}`;
    } else {
      this.helpers.add("callHandler");
      hoistedExpr = `(ctx, ev) => callHandler(${compiled}, ctx, ev)`;
    }
    return `[${this.hoistHandler(hoistedExpr)}, ctx${modifiersCode}]`;
  }
  // handlers are static functions of (context, event): one per distinct code
  hoistHandler(expr) {
    let id = this.hoistedHandlers.get(expr);
    if (!id) {
      id = this.generateId("hdlr_fn");
      this.hoistedHandlers.set(expr, id);
      this.staticDefs.push({ id, expr });
    }
    return id;
  }
  compileTDomNode(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    const isNewBlock = !block || forceNewBlock || ast.dynamicTag !== null || ast.ns;
    let codeIdx = this.target.code.length;
    if (isNewBlock) {
      block = this.createBlock(block, "block");
      this.blocks.push(block);
      if (ast.dynamicTag) {
        const tagExpr = this.generateId("tag");
        this.helpers.add("checkTagName");
        this.define(tagExpr, `checkTagName(${compileExpr(ast.dynamicTag)})`);
        block.dynamicTagName = tagExpr;
      }
    }
    const attrs = {};
    let valueVar = null;
    for (let key in ast.attrs) {
      let expr, attrName;
      if (key.startsWith("t-att")) {
        const isFormat = key.startsWith("t-attf");
        attrName = isFormat ? key.slice(7) : key === "t-att" ? null : key.slice(6);
        expr = isFormat ? interpolate(ast.attrs[key]) : compileExpr(ast.attrs[key]);
        if (attrName && isProp(ast.tag, attrName)) {
          if (attrName === "readonly") {
            attrName = "readOnly";
          }
          if (attrName === "value") {
            const valueId = this.generateId("v");
            this.define(valueId, expr);
            valueVar = valueId;
            expr = `new String(${valueId} === 0 ? 0 : ${valueId} || "")`;
          } else {
            expr = `new Boolean(${expr})`;
          }
          const idx = block.insertData(expr, "prop");
          attrs[`block-property-${idx}`] = attrName;
        } else {
          const idx = block.insertData(expr, "attr");
          if (key === "t-att") {
            attrs[`block-attributes`] = String(idx);
          } else {
            attrs[`block-attribute-${idx}`] = attrName;
          }
          if (attrName === "value") {
            valueVar = block.data[idx];
          }
        }
      } else if (ctx.translate && this.translatableAttributes.includes(key)) {
        const attrTranslationCtx = ast.attrsTranslationCtx?.[key] || ctx.translationCtx;
        attrs[key] = this.translate(ast.attrs[key], attrTranslationCtx);
      } else {
        expr = JSON.stringify(ast.attrs[key]);
        attrName = key;
        attrs[key] = ast.attrs[key];
      }
      if (attrName === "value" && ctx.tModelSelectedExpr) {
        const value = key.startsWith("t-att") ? valueVar : expr;
        let selectedId = block.insertData(`${ctx.tModelSelectedExpr} === ${value}`, "attr");
        attrs[`block-attribute-${selectedId}`] = "selected";
      }
    }
    let tModelSelectedExpr;
    if (ast.model) {
      const {
        hasDynamicChildren,
        expr,
        eventType,
        shouldNumberize,
        shouldTrim,
        targetAttr,
        specialInitTargetAttr,
        isProxy
      } = ast.model;
      let readExpr;
      let handlerData;
      let valueCode = `ev.target.${targetAttr}`;
      valueCode = shouldTrim ? `${valueCode}.trim()` : valueCode;
      if (shouldNumberize) {
        this.helpers.add("toNumber");
        valueCode = `toNumber(${valueCode})`;
      }
      let handlerId;
      if (isProxy) {
        readExpr = compileExpr(expr);
        handlerId = this.hoistHandler(`(ctx, ev) => { ${readExpr} = ${valueCode}; }`);
        handlerData = `[${handlerId}, ctx]`;
      } else {
        const exprId = this.generateId("expr");
        this.helpers.add("modelExpr");
        this.define(exprId, `modelExpr(${compileExpr(expr)})`);
        readExpr = `${exprId}()`;
        handlerId = this.hoistHandler(`(ctx, ev, model) => model.set(${valueCode})`);
        handlerData = `[${handlerId}, ctx, 0, ${exprId}]`;
      }
      let idx;
      if (specialInitTargetAttr) {
        const targetExpr = targetAttr in attrs ? JSON.stringify(attrs[targetAttr]) : valueVar || "false";
        idx = block.insertData(`${readExpr} === ${targetExpr}`, "prop");
        attrs[`block-property-${idx}`] = specialInitTargetAttr;
      } else if (hasDynamicChildren) {
        const bValueId = this.generateId("bValue");
        tModelSelectedExpr = `${bValueId}`;
        this.define(tModelSelectedExpr, readExpr);
      } else {
        idx = block.insertData(readExpr, "prop");
        attrs[`block-property-${idx}`] = targetAttr;
      }
      idx = block.insertData(handlerData, "hdlr");
      attrs[`block-handler-${idx}`] = eventType;
    }
    for (let ev in ast.on) {
      const name = this.generateHandlerCode(ev, ast.on[ev]);
      const idx = block.insertData(name, "hdlr");
      attrs[`block-handler-${idx}`] = ev;
    }
    if (ast.ref) {
      const refExpr = compileExpr(ast.ref);
      this.helpers.add("createRef");
      const setRefStr = `createRef(${refExpr}, node)`;
      const idx = block.insertData(setRefStr, "ref");
      attrs["block-ref"] = String(idx);
    }
    const nameSpace = ast.ns || ctx.nameSpace;
    const dom = nameSpace ? xmlDoc.createElementNS(nameSpace, ast.tag) : xmlDoc.createElement(ast.tag);
    for (const [attr, val] of Object.entries(attrs)) {
      if (!(attr === "class" && val === "")) {
        dom.setAttribute(attr, val);
      }
    }
    block.insert(dom);
    if (ast.content.length) {
      const initialDom = block.currentDom;
      block.currentDom = dom;
      const children = ast.content;
      for (let i = 0; i < children.length; i++) {
        const child = ast.content[i];
        const subCtx = createContext2(ctx, {
          block,
          forceNewBlock: false,
          tKeyExpr: ctx.tKeyExpr,
          nameSpace,
          tModelSelectedExpr: tModelSelectedExpr || ctx.tModelSelectedExpr,
          inPreTag: ctx.inPreTag || ast.tag === "pre"
        });
        this.compileAST(child, subCtx);
      }
      block.currentDom = initialDom;
    }
    if (isNewBlock) {
      this.insertBlock(block, ctx);
      if (block.children.length && block.hasDynamicChildren) {
        this.hoistChildDeclarations(block, codeIdx);
      }
    }
    return block.varName;
  }
  hoistChildDeclarations(block, codeIdx) {
    const code = this.target.code;
    const children = block.children.slice();
    let current = children.shift();
    for (let i = codeIdx; current && i < code.length; i++) {
      if (code[i].trimStart().startsWith(`const ${current.varName} `)) {
        code[i] = code[i].replace(`const ${current.varName}`, current.varName);
        current = children.shift();
      }
    }
    this.addLine(`let ${block.children.map((c) => c.varName).join(", ")};`, codeIdx);
  }
  compileZero(ast, ctx) {
    this.helpers.add("zero");
    const isMultiple = this.slotNames.has(zero);
    this.slotNames.add(zero);
    const key = this.scopeKey(ctx, isMultiple);
    let defaultContent = `text("")`;
    if (ast.body) {
      const bodyAst = { type: ASTType.Multi, content: ast.body };
      const name = this.compileInNewTarget("defaultContent", bodyAst, ctx);
      defaultContent = `${name}.call(this, ctx, node, ${key})`;
    }
    return `ctx[zero] ? ctx[zero](node, ${key}) : ${defaultContent}`;
  }
  compileTOut(ast, ctx) {
    let { block } = ctx;
    block = this.createBlock(block, "html");
    let blockStr;
    if (ast.expr === "0") {
      blockStr = this.compileZero(ast, ctx);
    } else {
      const site = this.generateId("__");
      const keyExpr = ctx.tKeyExpr ? `${ctx.tKeyExpr} + key` : "key";
      const level = this.target.loopLevel;
      let keyArgs;
      if (level <= MAX_LAZY_LOOP_KEYS) {
        if (this.dev) {
          for (let i = 1; i <= level; i++) {
            this.target.stringKey(i);
          }
        }
        const loopKeys = Array.from({ length: level }, (_, i) => `, key${i + 1}`).join("");
        keyArgs = `${keyExpr}, "${site}"${level ? `, ${level}${loopKeys}` : ""}`;
      } else {
        keyArgs = `${this.scopeKey(ctx, false, site)}, ""`;
      }
      const expr = compileExpr(ast.expr);
      if (ast.body) {
        const bodyAst = { type: ASTType.Multi, content: ast.body };
        const name = this.compileInNewTarget("defaultContent", bodyAst, ctx);
        const key = this.scopeKey(ctx, false, site);
        this.helpers.add("safeOutputOr");
        blockStr = `safeOutputOr(${expr}, () => ${name}.call(this, ctx, node, ${key}), ${keyArgs})`;
      } else {
        this.helpers.add("safeOutput");
        blockStr = `safeOutput(${expr}, ${keyArgs})`;
      }
    }
    this.insertBlock(block, ctx, blockStr);
    return block.varName;
  }
  compileTIfBranch(content, block, ctx) {
    this.target.indentLevel++;
    this.compileAST(content, createContext2(ctx, { block, index: ctx.index }));
    this.target.indentLevel--;
  }
  compileTIf(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    const codeIdx = this.target.code.length;
    const isNewBlock = !block || block.type !== "multi" && forceNewBlock;
    if (block) {
      block.hasDynamicChildren = true;
    }
    block = isNewBlock ? this.createBlock(block, "multi") : block;
    this.addLine(`if (${compileExpr(ast.condition)}) {`);
    this.compileTIfBranch(ast.content, block, ctx);
    if (ast.tElif) {
      for (let clause of ast.tElif) {
        this.addLine(`} else if (${compileExpr(clause.condition)}) {`);
        this.compileTIfBranch(clause.content, block, ctx);
      }
    }
    if (ast.tElse) {
      this.addLine(`} else {`);
      this.compileTIfBranch(ast.tElse, block, ctx);
    }
    this.addLine("}");
    if (isNewBlock) {
      if (block.children.length) {
        this.hoistChildDeclarations(block, codeIdx);
      }
      const args = block.children.map((c) => c.varName).join(", ");
      this.insertBlock(block, ctx, `multi([${args}])`);
    }
    return block.varName;
  }
  compileTForeach(ast, ctx) {
    const block = ast.hasNoRepresentation ? null : this.createBlock(ctx.block, "list");
    const id = block ? block.id : this.generateId("_");
    let memo = null;
    if (ast.memo !== void 0 && block) {
      memo = this.generateId("memo");
      this.helpers.add("memoPrevious");
      this.helpers.add("memoKeep");
      this.helpers.add("memoHit");
      this.define(`${memo}_site`, this.scopeKey(ctx, true));
      this.define(`${memo}_previous`, `memoPrevious(node, ${memo}_site)`);
      this.define(`${memo}_next`, `new Map()`);
    }
    this.target.loopLevel++;
    const loopVar = `i${this.target.loopLevel}`;
    const ctxVar = this.generateId("ctx");
    this.addLine(`const ${ctxVar} = ctx;`);
    this.target.loopCtxVars.push(ctxVar);
    const vals = `v_block${id}`;
    const keys = `k_block${id}`;
    const l = `l_block${id}`;
    const lists = block ? [keys, vals, l, `c_block${id}`] : [keys, vals, l];
    this.helpers.add("prepareList");
    this.define(`[${lists.join(", ")}]`, `prepareList(${compileExpr(ast.collection)})`);
    if (this.dev) {
      this.define(`keys${id}`, `new Set()`);
    }
    this.addLine(`for (let ${loopVar} = 0; ${loopVar} < ${l}; ${loopVar}++) {`);
    this.target.indentLevel++;
    this.addLine(`let ctx = Object.create(${ctxVar});`);
    const loopVarName = (suffix) => JSON.stringify(ast.elem + suffix);
    this.addLine(`ctx[${loopVarName("")}] = ${keys}[${loopVar}];`);
    if (!(ast.noFlags & ForEachNoFlag.First)) {
      this.addLine(`ctx[${loopVarName("_first")}] = ${loopVar} === 0;`);
    }
    if (!(ast.noFlags & ForEachNoFlag.Last)) {
      this.addLine(`ctx[${loopVarName("_last")}] = ${loopVar} === ${keys}.length - 1;`);
    }
    if (!(ast.noFlags & ForEachNoFlag.Index)) {
      this.addLine(`ctx[${loopVarName("_index")}] = ${loopVar};`);
    }
    if (!(ast.noFlags & ForEachNoFlag.Value)) {
      this.addLine(`ctx[${loopVarName("_value")}] = ${vals}[${loopVar}];`);
    }
    const level = this.target.loopLevel;
    this.define(`key${level}`, compileExpr(ast.key));
    const keyIdx = this.target.code.length;
    const subCtx = createContext2(ctx, { block, index: loopVar });
    if (memo) {
      this.target.memoLevels.push(level);
    }
    this.compileAST(ast.body, subCtx);
    if (memo) {
      this.target.memoLevels.pop();
    }
    const keyLines = [];
    let uniqueKey = `key${level}`;
    if (this.target.stringKeyLevels.delete(level)) {
      this.helpers.add("keyOf");
      keyLines.push(`const skey${level} = keyOf(key${level});`);
      uniqueKey = `skey${level}`;
    }
    if (this.dev) {
      this.helpers.add("OwlError");
      keyLines.push(
        `if (keys${id}.has(${uniqueKey})) { throw new OwlError(\`Got duplicate key in t-foreach: \${key${level}}\`)}`,
        `keys${id}.add(${uniqueKey});`
      );
    }
    if (memo) {
      const vnodes = `c_block${id}`;
      const entry = (content) => `{ deps: deps${level}, vnodes: ${vnodes}, index: ${loopVar}, content: ${content} }`;
      keyLines.push(
        `const deps${level} = ${compileExpr(ast.memo)};`,
        `const hit${level} = memoHit(${memo}_previous, ${uniqueKey}, deps${level}, node);`,
        `if (hit${level} !== undefined) {`,
        `  ${vnodes}[${loopVar}] = hit${level}.vnodes[hit${level}.index];`,
        `  ${memo}_next.set(${uniqueKey}, ${entry(`hit${level}.content`)});`,
        `  continue;`,
        `}`
      );
      if (ast.memoContent) {
        this.helpers.add("memoBegin");
        this.helpers.add("memoEnd");
        keyLines.push(`const outer${level} = memoBegin();`);
        this.addLine(`${memo}_next.set(${uniqueKey}, ${entry(`memoEnd(outer${level})`)});`);
      } else {
        this.addLine(`${memo}_next.set(${uniqueKey}, ${entry("null")});`);
      }
    }
    keyLines.forEach((line, i) => this.addLine(line, keyIdx + i));
    this.target.indentLevel--;
    this.target.loopLevel--;
    this.target.loopCtxVars.pop();
    for (const [name, level2] of this.target.tSetVars) {
      if (level2 > this.target.loopLevel) {
        this.target.tSetVars.delete(name);
      }
    }
    this.addLine(`}`);
    if (memo) {
      this.addLine(`memoKeep(node, ${memo}_site, ${memo}_next);`);
    }
    if (!block) {
      return null;
    }
    this.insertBlock(block, ctx);
    return block.varName;
  }
  compileTKey(ast, ctx) {
    const tKeyExpr = this.generateId("tKey_");
    this.helpers.add("keyOf");
    this.define(tKeyExpr, `keyOf(${compileExpr(ast.expr)})`);
    ctx = createContext2(ctx, {
      tKeyExpr,
      block: ctx.block,
      index: ctx.index
    });
    return this.compileAST(ast.content, ctx);
  }
  compileMulti(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    const isNewBlock = !block || forceNewBlock;
    let codeIdx = this.target.code.length;
    if (isNewBlock) {
      const n = ast.content.filter((c) => !c.hasNoRepresentation).length;
      let result = null;
      if (n <= 1) {
        const shouldDefer = !this.target.hasRoot && n === 1 && ast.content[ast.content.length - 1].hasNoRepresentation;
        if (shouldDefer) {
          this.target.deferReturn = true;
        }
        for (let child of ast.content) {
          const blockName = this.compileAST(child, ctx);
          result = result || blockName;
        }
        if (shouldDefer) {
          this.target.deferReturn = false;
          this.emitRootReturn(result);
        }
        return result;
      }
      block = this.createBlock(block, "multi");
    }
    let index = 0;
    for (let i = 0, l = ast.content.length; i < l; i++) {
      const child = ast.content[i];
      const forceNewBlock2 = !child.hasNoRepresentation;
      const subCtx = createContext2(ctx, {
        block,
        index,
        forceNewBlock: forceNewBlock2
      });
      this.compileAST(child, subCtx);
      if (forceNewBlock2) {
        index++;
      }
    }
    if (isNewBlock) {
      if (block.hasDynamicChildren && block.children.length) {
        this.hoistChildDeclarations(block, codeIdx);
      }
      const args = block.children.map((c) => c.varName).join(", ");
      this.insertBlock(block, ctx, `multi([${args}])`);
    }
    return block.varName;
  }
  compileTCall(ast, ctx) {
    let { block } = ctx;
    const attrs = ast.attrs ? this.formatPropObject(ast.attrs, ast.attrsTranslationCtx, ctx) : [];
    const isDynamic = isInterpolated(ast.name);
    const subTemplate = isDynamic ? interpolate(ast.name) : toStringExpression(ast.name);
    block = this.createBlock(block, "multi");
    if (ast.body) {
      const name = this.compileInNewTarget("callBody", ast.body, ctx);
      const zeroStr = this.generateId("lazyBlock");
      this.define(zeroStr, `${name}.bind(this, ctx)`);
      this.helpers.add("zero");
      attrs.push(`[zero]: ${zeroStr}`);
    } else if (!ast.context) {
      this.helpers.add("zero");
      attrs.push(`[zero]: null`);
    }
    let ctxExpr;
    const ctxString = `{${attrs.join(", ")}}`;
    if (ast.context) {
      const dynCtxVar = this.generateId("ctx");
      this.addLine(`const ${dynCtxVar} = ${compileExpr(ast.context)};`);
      const extra = attrs.length ? `, ${ctxString}` : "";
      ctxExpr = `Object.assign({}, ${dynCtxVar}, {this: ${dynCtxVar}}${extra})`;
    } else {
      ctxExpr = `Object.assign(Object.create(ctx), ${ctxString})`;
    }
    const key = this.scopeKey(ctx, true);
    this.helpers.add("callTemplate");
    this.insertBlock(
      block,
      ctx,
      `callTemplate(${subTemplate}, this, app, ${ctxExpr}, node, ${key})`
    );
    return block.varName;
  }
  compileTCallBlock(ast, ctx) {
    let { block } = ctx;
    block = this.createBlock(block, "multi");
    this.insertBlock(block, ctx, compileExpr(ast.name));
    return block.varName;
  }
  compileTSet(ast, ctx) {
    let value;
    if (ast.body) {
      this.helpers.add("LazyValue");
      const bodyAst = { type: ASTType.Multi, content: ast.body };
      const name2 = this.compileInNewTarget("value", bodyAst, ctx);
      value = `new LazyValue(${name2}, ctx, this, node, ${this.scopeKey(ctx)})`;
    } else if (ast.defaultValue) {
      value = toStringExpression(
        ctx.translate ? this.translate(ast.defaultValue, ctx.translationCtx) : ast.defaultValue
      );
    } else {
      value = ast.value ? compileExpr(ast.value) : "null";
    }
    if (ast.value && (ast.body || ast.defaultValue)) {
      this.helpers.add("withDefault");
      value = `withDefault(${compileExpr(ast.value)}, ${value})`;
    }
    const name = JSON.stringify(ast.name);
    const level = this.target.loopLevel;
    const defLevel = this.target.tSetVars.get(ast.name);
    if (defLevel !== void 0 && level > defLevel) {
      if (this.target.memoLevels.some((memoLevel) => memoLevel > defLevel)) {
        throw new OwlError(
          `t-set="${ast.name}" inside a t-memo item writes a variable of an enclosing scope, and a memo hit would skip the write`
        );
      }
      this.addLine(`${this.target.loopCtxVars[defLevel]}[${name}] = ${value};`);
    } else {
      if (!level) {
        this.target.needsScopeProtection = true;
      }
      this.addLine(`ctx[${name}] = ${value};`);
      this.target.tSetVars.set(ast.name, level);
    }
    return null;
  }
  scopeKey(ctx, unique = false, site = "") {
    let suffix = unique ? this.generateId("__") : site;
    for (let i = 1; i <= this.target.loopLevel; i++) {
      suffix += `__\${${this.target.stringKey(i)}}`;
    }
    const key = suffix ? `key + \`${suffix}\`` : "key";
    return ctx.tKeyExpr ? `${ctx.tKeyExpr} + ${key}` : key;
  }
  /**
   * Formats a prop name and value into a string suitable to be inserted in the
   * generated code. For example:
   *
   * Name              Value            Result
   * ---------------------------------------------------------
   * "number"          "state"          "number: ctx['state']"
   * "something"       ""               "something: undefined"
   * "some-prop"       "state"          "'some-prop': ctx['state']"
   * "onClick.bind"    "onClick"        "onClick: bind(ctx, ctx['onClick'])"
   */
  formatProp(name, value, attrsTranslationCtx, ctx) {
    if (name.endsWith(".translate")) {
      const attrTranslationCtx = attrsTranslationCtx?.[name] || ctx.translationCtx;
      value = toStringExpression(ctx.translate ? this.translate(value, attrTranslationCtx) : value);
    } else {
      value = compileExpr(value);
    }
    if (name.includes(".")) {
      let [_name, suffix] = name.split(".");
      name = _name;
      switch (suffix) {
        case "bind":
          value = `(${value}).bind(this)`;
          break;
        case "alike":
        case "translate":
          break;
        default:
          throw new OwlError(`Invalid prop suffix: ${suffix}`);
      }
    }
    name = /^[a-z_]+$/i.test(name) ? name : `'${name}'`;
    return `${name}: ${value || void 0}`;
  }
  formatPropObject(obj, attrsTranslationCtx, ctx) {
    return Object.entries(obj).map(([k, v]) => this.formatProp(k, v, attrsTranslationCtx, ctx));
  }
  getPropString(props2, dynProps) {
    let propString = `{${props2.join(",")}}`;
    if (dynProps) {
      propString = `Object.assign({}, ${compileExpr(dynProps)}${props2.length ? ", " + propString : ""})`;
    }
    return propString;
  }
  compileComponent(ast, ctx) {
    let { block } = ctx;
    const hasSlotsProp = "slots" in (ast.props || {});
    const props2 = [];
    const propList = [];
    const signalProps = [];
    for (let p in ast.props || {}) {
      let [name, suffix] = p.split(".");
      if (suffix === "signal") {
        const propName2 = /^[a-z_]+$/i.test(name) ? name : `'${name}'`;
        props2.push(`${propName2}: ${compileExpr(ast.props[p]) || void 0}`);
        signalProps.push(JSON.stringify(name));
        continue;
      }
      if (suffix) {
        props2.push(this.formatProp(p, ast.props[p], ast.propsTranslationCtx, ctx));
        continue;
      }
      const { expr: compiledValue, freeVariables } = processExpr(ast.props[p]);
      const propName = /^[a-z_]+$/i.test(name) ? name : `'${name}'`;
      props2.push(`${propName}: ${compiledValue || void 0}`);
      if (freeVariables) {
        for (const varName of freeVariables) {
          const syntheticKey = `${name}.${varName}`;
          propList.push(`"${syntheticKey}"`);
          props2.push(`"${syntheticKey}": ctx['${varName}']`);
        }
      } else {
        propList.push(`"${name}"`);
      }
    }
    let slotDef = "";
    if (ast.slots) {
      let slotStr = [];
      for (let slotName in ast.slots) {
        const slotAst = ast.slots[slotName];
        const params = [];
        if (slotAst.content) {
          const name = this.compileInNewTarget("slot", slotAst.content, ctx, slotAst.on);
          params.push(`__render: ${name}.bind(this), __ctx: ctx`);
        }
        const scope = ast.slots[slotName].scope;
        if (scope) {
          params.push(`__scope: ${JSON.stringify(scope)}`);
        }
        if (ast.slots[slotName].attrs) {
          params.push(
            ...this.formatPropObject(
              ast.slots[slotName].attrs,
              ast.slots[slotName].attrsTranslationCtx,
              ctx
            )
          );
        }
        const slotInfo = `{${params.join(", ")}}`;
        slotStr.push(`${JSON.stringify(slotName)}: ${slotInfo}`);
      }
      slotDef = `{${slotStr.join(", ")}}`;
    }
    if (slotDef && !(ast.dynamicProps || hasSlotsProp)) {
      this.helpers.add("markRaw");
      props2.push(`slots: markRaw(${slotDef})`);
    }
    let propString = this.getPropString(props2, ast.dynamicProps);
    let propVar;
    if (slotDef && (ast.dynamicProps || hasSlotsProp) || this.dev) {
      propVar = this.generateId("props");
      this.define(propVar, propString);
      propString = propVar;
    }
    if (slotDef && (ast.dynamicProps || hasSlotsProp)) {
      this.helpers.add("markRaw");
      this.addLine(`${propVar}.slots = markRaw(Object.assign(${slotDef}, ${propVar}.slots))`);
    }
    let expr;
    if (ast.isDynamic) {
      expr = this.generateId("Comp");
      this.define(expr, compileExpr(ast.name));
    } else {
      expr = `\`${ast.name}\``;
    }
    let keyArg = this.scopeKey(ctx, true);
    let id = this.generateId("comp");
    this.helpers.add("createComponent");
    this.staticDefs.push({
      id,
      expr: `createComponent(app, ${ast.isDynamic ? null : expr}, ${!ast.isDynamic}, ${!!ast.slots}, ${!!ast.dynamicProps}, [${propList}]${signalProps.length ? `, [${signalProps}]` : ""})`
    });
    if (ast.isDynamic) {
      keyArg = `(${expr}).name + ${keyArg}`;
    }
    let blockExpr = `${id}(${propString}, ${keyArg}, node, this, ${ast.isDynamic ? expr : null})`;
    if (ast.isDynamic) {
      blockExpr = `toggler(${expr}, ${blockExpr})`;
    }
    if (ast.on) {
      blockExpr = this.wrapWithEventCatcher(blockExpr, ast.on);
    }
    block = this.createBlock(block, "multi");
    this.insertBlock(block, ctx, blockExpr);
    return block.varName;
  }
  wrapWithEventCatcher(expr, on) {
    this.helpers.add("createCatcher");
    let name = this.generateId("catcher");
    let spec = {};
    let handlers = [];
    for (let ev in on) {
      let handlerId = this.generateId("hdlr");
      let idx = handlers.push(handlerId) - 1;
      spec[ev] = idx;
      const handler = this.generateHandlerCode(ev, on[ev]);
      this.define(handlerId, handler);
    }
    this.staticDefs.push({ id: name, expr: `createCatcher(${JSON.stringify(spec)})` });
    return `${name}(${expr}, [${handlers.join(",")}])`;
  }
  compileTCallSlot(ast, ctx) {
    this.helpers.add("callSlot");
    let { block } = ctx;
    let blockString;
    let slotName;
    let dynamic = false;
    let isMultiple = false;
    if (isInterpolated(ast.name)) {
      dynamic = true;
      isMultiple = true;
      slotName = interpolate(ast.name);
    } else {
      slotName = JSON.stringify(ast.name);
      isMultiple = isMultiple || this.slotNames.has(ast.name);
      this.slotNames.add(ast.name);
    }
    const attrs = { ...ast.attrs };
    const dynProps = attrs["t-props"];
    delete attrs["t-props"];
    const key = this.scopeKey(ctx, isMultiple);
    const props2 = ast.attrs ? this.formatPropObject(attrs, ast.attrsTranslationCtx, ctx) : [];
    const scope = this.getPropString(props2, dynProps);
    if (ast.defaultContent) {
      const name = this.compileInNewTarget("defaultContent", ast.defaultContent, ctx);
      blockString = `callSlot(ctx, node, ${key}, ${slotName}, ${dynamic}, ${scope}, ${name}.bind(this))`;
    } else {
      if (dynamic) {
        let name = this.generateId("slot");
        this.define(name, slotName);
        blockString = `toggler(${name}, callSlot(ctx, node, ${key}, ${name}, ${dynamic}, ${scope}))`;
      } else {
        blockString = `callSlot(ctx, node, ${key}, ${slotName}, ${dynamic}, ${scope})`;
      }
    }
    if (ast.on) {
      blockString = this.wrapWithEventCatcher(blockString, ast.on);
    }
    block = this.createBlock(block, "multi");
    this.insertBlock(block, ctx, blockString);
    return block.varName;
  }
  compileTTranslation(ast, ctx) {
    if (ast.content) {
      return this.compileAST(ast.content, Object.assign({}, ctx, { translate: false }));
    }
    return null;
  }
  compileTTranslationContext(ast, ctx) {
    if (ast.content) {
      return this.compileAST(
        ast.content,
        Object.assign({}, ctx, { translationCtx: ast.translationCtx })
      );
    }
    return null;
  }
};

// ../owl-compiler/src/index.ts
function compile(template, options = {
  hasGlobalValues: false
}) {
  const ast = parse(template, options.customDirectives);
  const codeGenerator = new CodeGenerator(ast, options);
  const code = codeGenerator.generateCode();
  try {
    return new Function("app, bdom, helpers", code);
  } catch (originalError) {
    const { name } = options;
    const nameStr = name ? `template "${name}"` : "anonymous template";
    const err = new OwlError(
      `Failed to compile ${nameStr}: ${originalError.message}

generated code:
function(app, bdom, helpers) {
${code}
}`
    );
    err.cause = originalError;
    throw err;
  }
}

// src/index.ts
TemplateSet.compiler = { compile, parseXML };
export {
  App,
  Component,
  DEBUG_CHANNELS,
  ErrorBoundary,
  EventBus,
  OwlError,
  Plugin,
  Portal,
  Registry,
  Resource,
  Scope,
  Suspense,
  TemplateSet,
  __info__,
  applyDefaults,
  assertType,
  asyncComputed,
  batched,
  blockDom,
  computed,
  config,
  effect,
  getDefault,
  getScope,
  globalTemplates,
  htmlEscape,
  immediateEffect,
  isAbortError,
  markRaw,
  markup,
  mount2 as mount,
  observe,
  onError,
  onMounted,
  onPatched,
  onWillDestroy,
  onWillPatch,
  onWillStart,
  onWillUnmount,
  onWillUpdateProps,
  plugin,
  props,
  providePlugins,
  proxy,
  selector,
  setDebug,
  setDebugSink,
  shallowEqual,
  signal,
  status,
  types2 as t,
  toRaw,
  types2 as types,
  untrack,
  useApp2 as useApp,
  useConfig,
  useEffect,
  useListener,
  useOnChange,
  usePlugin,
  useProps,
  useScope,
  validateType,
  whenReady,
  xml
};
