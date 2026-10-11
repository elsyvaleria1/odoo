const VERSION = "__SFT_DRIVER_VERSION__";
const CACHE = `sft-driver-${VERSION}`;
const PAGE = "/stock_fleet_trace/driver";
const PAGE_TIMEOUT = 4000;
const SHELL = [
    PAGE,
    "/stock_fleet_trace/driver/manifest.webmanifest",
    "/stock_fleet_trace/static/driver/app.js",
    "/stock_fleet_trace/static/driver/canonical.js",
    "/stock_fleet_trace/static/driver/db.js",
    "/stock_fleet_trace/static/driver/driver.css",
    "/web/static/img/odoo-icon-192x192.png",
    "/web/static/img/odoo-icon-512x512.png",
];

function cacheable(response) {
    return response && response.ok && !response.redirected && response.type === "basic";
}

async function fetchAndStore(cache, url) {
    const response = await fetch(url, { cache: "reload", credentials: "same-origin" });
    if (cacheable(response)) {
        await cache.put(url, response.clone());
    }
    return response;
}

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE)
            .then((cache) =>
                Promise.all(
                    SHELL.map(async (url) => {
                        const response = await fetch(url, {
                            cache: "reload",
                            credentials: "same-origin",
                        });
                        if (!cacheable(response)) {
                            throw new Error(`Cannot cache ${url}`);
                        }
                        await cache.put(url, response);
                    }),
                ),
            )
            .then(() => self.skipWaiting()),
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(
                    keys
                        .filter((key) => key.startsWith("sft-driver-") && key !== CACHE)
                        .map((key) => caches.delete(key)),
                ),
            )
            .then(() => self.clients.claim()),
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") {
        return;
    }
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }
    const isPage = url.pathname === PAGE || url.pathname === `${PAGE}/`;
    if (!isPage && !SHELL.includes(url.pathname)) {
        return;
    }
    const key = isPage ? PAGE : url.pathname;
    event.respondWith(
        caches.open(CACHE).then(async (cache) => {
            if (isPage) {
                try {
                    const response = await Promise.race([
                        fetchAndStore(cache, key),
                        new Promise((resolve, reject) =>
                            setTimeout(() => reject(new Error("slow")), PAGE_TIMEOUT),
                        ),
                    ]);
                    if (cacheable(response)) {
                        return response;
                    }
                } catch {}
                return (
                    (await cache.match(key, { ignoreSearch: true })) || fetch(request)
                );
            }
            const cached = await cache.match(key, { ignoreSearch: true });
            return cached || fetchAndStore(cache, key);
        }),
    );
});
