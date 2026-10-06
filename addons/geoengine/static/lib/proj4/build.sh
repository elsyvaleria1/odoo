#!/usr/bin/env bash
# Rebuild proj4.esm.js from upstream proj4js.
#
# OpenLayers resolves EPSG:4326, EPSG:3857 and the UTM zones by itself; any
# other CRS (EPSG:6372, Mexico's official LCC, for one) needs a proj4
# definition registered through ol/proj/proj4's register(). proj4 is loaded
# only by a map that needs such a CRS (geo_libs.registerProjections), so it is
# its own import-map external rather than part of the OpenLayers bundle.
#
# The package ships a UMD dist and an ESM source tree; it is bundled into one
# file for the same reason as ../ol and ../chroma-js: an import-map external
# must resolve to a single URL.
#
# esbuild is pinned; see ../ol/build.sh for why.
#
# Usage:  ./build.sh [version]
set -euo pipefail

cd "$(dirname "$0")"

PROJ4_VERSION="${1:-2.22.0}"
ESBUILD_VERSION="0.25.0"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

printf 'export {default} from "proj4";\n' > "$workdir/entry.js"
cd "$workdir"
npm install --silent --no-package-lock "proj4@${PROJ4_VERSION}"
cp node_modules/proj4/LICENSE.md "$OLDPWD/LICENSE.md"

npx "esbuild@${ESBUILD_VERSION}" entry.js \
    --bundle \
    --format=esm \
    --target=es2023 \
    --minify \
    --legal-comments=inline \
    --banner:js="/*! proj4js ${PROJ4_VERSION} | MIT | https://github.com/proj4js/proj4js
 * Single-file ES-module build of the package's default entry point. */" \
    --outfile=proj4.esm.js

mv proj4.esm.js "$OLDPWD/"
