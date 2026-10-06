#!/usr/bin/env bash
# Record the meeting room and upload the audio to a conversation in Odoo.
#
# Usage:
#   record-room.sh <conversation_id> [topic]
#
# Environment (put them in ~/.config/conversation-room.env, chmod 600):
#   ODOO_URL           https://agromarin.mx
#   ROOM_DEVICE_ID     identifier of the device.device in the "Meeting Room" category
#   ROOM_DEVICE_TOKEN  its Bearer token
#   ROOM_SOURCE        Pulse/PipeWire source name (default: the system default)
#   SKIP_AUDIO_PREFLIGHT=1  skip the checks when re-launching after a fix
#   LIVE=1             also stream 15-second chunks to the live panel while recording
#
# The full take is encoded as Opus (a few MB per hour) so any meeting fits the
# device's upload limit; live chunks stay WAV, 15 seconds each.
#
# The script refuses to start until the moderator confirms: the 2026-07-31
# leaders' meeting recorded 22 minutes of an empty room because the capture
# began as soon as the preflight passed.
set -euo pipefail

CONVERSATION_ID="${1:-}"
TOPIC="${2:-reunion}"
ENV_FILE="${HOME}/.config/conversation-room.env"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
: "${ODOO_URL:?ODOO_URL is not set}"
: "${ROOM_DEVICE_ID:?ROOM_DEVICE_ID is not set}"
: "${ROOM_DEVICE_TOKEN:?ROOM_DEVICE_TOKEN is not set}"
[ -n "$CONVERSATION_ID" ] || { echo "usage: record-room.sh <conversation_id> [topic]"; exit 2; }

OUT_DIR="${HOME}/Odoo/meets/${TOPIC}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
TAKE="${OUT_DIR}/${TOPIC}-${STAMP}.ogg"
CHUNK_SECONDS=15
SOURCE_ARGS=()
[ -n "${ROOM_SOURCE:-}" ] && SOURCE_ARGS=(-i "$ROOM_SOURCE") || SOURCE_ARGS=(-i default)
export ODOO_URL ROOM_DEVICE_ID ROOM_DEVICE_TOKEN CONVERSATION_ID

preflight() {
    command -v ffmpeg >/dev/null || { echo "ffmpeg is missing"; exit 1; }
    ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libopus || { echo "ffmpeg lacks the libopus encoder"; exit 1; }
    local free_gb
    free_gb=$(df -BG --output=avail "$OUT_DIR" | tail -1 | tr -dc '0-9')
    [ "$free_gb" -ge 2 ] || { echo "less than 2 GB free in $OUT_DIR"; exit 1; }
    echo "Say the test phrase now (5 seconds)..."
    local probe="${OUT_DIR}/.preflight.wav"
    ffmpeg -loglevel error -y -f pulse "${SOURCE_ARGS[@]}" -t 5 "$probe"
    local level
    level=$(ffmpeg -i "$probe" -af volumedetect -f null - 2>&1 | sed -n 's/.*mean_volume: \(-\?[0-9.]*\) dB.*/\1/p')
    rm -f "$probe"
    echo "Mean level: ${level:-?} dB"
    awk -v l="${level:--999}" 'BEGIN { exit (l > -80) ? 0 : 1 }' || {
        echo "No signal: microphone muted (red LED?), wrong source, or nobody spoke."; exit 1; }
}

# upload_chunk <wav> <start_s>: exit status is the server's answer, so a failed
# chunk is retried on the next pass instead of being skipped.
upload_chunk() {
    python3 - "$1" "$2" <<'PY'
import base64, json, os, sys, urllib.request
wav, start = sys.argv[1:3]
body = json.dumps({"audio_b64": base64.b64encode(open(wav, "rb").read()).decode(),
                   "start_s": int(start), "duration_s": int(os.environ["CHUNK_SECONDS"]),
                   "mimetype": "audio/wav"}).encode()
req = urllib.request.Request(
    f"{os.environ['ODOO_URL'].rstrip('/')}/conversation/{os.environ['ROOM_DEVICE_ID']}/{os.environ['CONVERSATION_ID']}/chunk",
    data=body, method="POST",
    headers={"Authorization": f"Bearer {os.environ['ROOM_DEVICE_TOKEN']}", "Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=120).read()
PY
}
export CHUNK_SECONDS

[ "${SKIP_AUDIO_PREFLIGHT:-0}" = "1" ] || preflight

read -r -p "Audio OK. Start recording now? [y/N] " answer
[ "$answer" = "y" ] || [ "$answer" = "Y" ] || { echo "Not started."; exit 0; }

echo "Recording to $TAKE — press Ctrl+C when the meeting ends."
trap 'echo; echo "Stopping..."' INT
if [ "${LIVE:-0}" = "1" ]; then
    # One ffmpeg writes the full take and, in parallel, chunk files; the
    # uploader ships them strictly in order, each with its offset.
    CHUNK_DIR="${OUT_DIR}/.chunks-${STAMP}"; mkdir -p "$CHUNK_DIR"
    (
        next=0
        while sleep 5; do
            chunk="$CHUNK_DIR/chunk-${next}.wav"
            [ -e "$chunk" ] || continue
            # a chunk is finished once the next one has started, or once ffmpeg
            # is gone (the last one closes when recording stops)
            [ -e "$CHUNK_DIR/chunk-$((next + 1)).wav" ] || ! kill -0 "$FFMPEG" 2>/dev/null || continue
            if upload_chunk "$chunk" "$((next * CHUNK_SECONDS))"; then
                next=$((next + 1))
            else
                echo "chunk $next not accepted; retrying" >&2
            fi
        done
    ) &
    UPLOADER=$!
    # Output options bind to the output that follows them: each output names
    # its own channel and rate.
    ffmpeg -loglevel error -f pulse "${SOURCE_ARGS[@]}" \
        -map 0:a -ac 1 -ar 16000 -c:a libopus -b:a 24k "$TAKE" \
        -map 0:a -ac 1 -ar 16000 -f segment -segment_time "$CHUNK_SECONDS" -reset_timestamps 1 "$CHUNK_DIR/chunk-%d.wav" &
    FFMPEG=$!
    export FFMPEG
    wait "$FFMPEG" || true
    sleep 12  # two uploader passes: the last chunk ships once ffmpeg is gone
    kill "$UPLOADER" 2>/dev/null || true
else
    ffmpeg -loglevel error -f pulse "${SOURCE_ARGS[@]}" -map 0:a -ac 1 -ar 16000 -c:a libopus -b:a 24k "$TAKE" || true
fi
trap - INT
[ -s "$TAKE" ] || { echo "No audio was recorded."; exit 1; }

echo "Uploading to conversation ${CONVERSATION_ID}..."
python3 - "$TAKE" <<'PY'
import base64, json, os, sys, urllib.request
take = sys.argv[1]
body = json.dumps({
    "audio_b64": base64.b64encode(open(take, "rb").read()).decode(),
    "file_name": take.rsplit("/", 1)[-1],
    "mimetype": "audio/ogg",
}).encode()
req = urllib.request.Request(
    f"{os.environ['ODOO_URL'].rstrip('/')}/conversation/{os.environ['ROOM_DEVICE_ID']}/{os.environ['CONVERSATION_ID']}/audio",
    data=body, method="POST",
    headers={"Authorization": f"Bearer {os.environ['ROOM_DEVICE_TOKEN']}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=600) as response:
    print(response.read().decode())
PY
echo "Done. The local copy stays in $TAKE."
