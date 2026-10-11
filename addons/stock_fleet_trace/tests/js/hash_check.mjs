import { hashEvent } from "../../static/driver/canonical.js";

const chunks = [];
for await (const chunk of process.stdin) {
    chunks.push(chunk);
}
const events = JSON.parse(Buffer.concat(chunks).toString("utf8"));
const out = [];
for (const event of events) {
    out.push({ wire: JSON.stringify(event), hash: await hashEvent(event) });
}
process.stdout.write(JSON.stringify(out));
