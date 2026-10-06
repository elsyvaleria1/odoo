// Hash offline events the way the driver screen does, for test_driver_screen.
// Reads a JSON list of events on stdin and writes, for each, the JSON the phone
// would send and the event_hash it would compute.
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
