#!/usr/bin/env bash
# Rebuild chroma.esm.js from upstream chroma-js.
#
# chroma-js is native ESM (`"type": "module"`, `exports["."].import`), but ships
# as a source tree rather than one file, so it is bundled here for the same
# reason OpenLayers is: an import-map external must resolve to a single URL.
#
# The full entry point is deliberate. chroma-js also publishes a `./light`
# subpath that drops the colour-brewer palettes, and geoengine's choropleth
# path calls `chroma.scale("RdYlBu")` (geoengine_model.js), which is one of
# them -- the light build would fail at runtime, not at build time.
#
# esbuild is pinned; see ../ol/build.sh for why.
#
# Usage:  ./build.sh [version]
set -euo pipefail

cd "$(dirname "$0")"

CHROMA_VERSION="${1:-3.2.0}"
ESBUILD_VERSION="0.25.0"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

printf 'export {default} from "chroma-js";\n' > "$workdir/entry.js"
cd "$workdir"
npm install --silent --no-package-lock "chroma-js@${CHROMA_VERSION}"

npx "esbuild@${ESBUILD_VERSION}" entry.js \
    --bundle \
    --format=esm \
    --target=es2023 \
    --minify \
    --legal-comments=inline \
    --banner:js="/*! chroma-js ${CHROMA_VERSION} | BSD-3-Clause AND Apache-2.0 | https://gka.github.io/chroma.js/
 * Single-file ES-module build of the package's default entry point. */" \
    --outfile=chroma.esm.js

cd - >/dev/null
cp "$workdir/chroma.esm.js" .
cp "$workdir/node_modules/chroma-js/LICENSE" .

echo "Rebuilt chroma.esm.js at ${CHROMA_VERSION} ($(stat -c%s chroma.esm.js) bytes)."
echo "Update ../versions.json in the same commit."
