#!/usr/bin/env bash
# Rebuild ol.esm.js from upstream OpenLayers.
#
# The npm package ships no single-file ESM bundle -- it is ~1100 separate
# modules -- and its `dist/ol.js` is a legacy global build, which is what
# geoengine used until 10.10.0. So the bundle is built here, from `entry.js`:
# esbuild tree-shakes everything that entry does not reach, which is why the
# shipped file is a fraction of the full dist (677 KB against 1043 KB at
# 10.10.0, for the 62 symbols geoengine actually uses).
#
# The esbuild version is PINNED, for the same reason the zxing-library build in
# web/static/lib pins it: esbuild's output formatting changes between releases,
# so an unpinned rebuild yields a large diff that is entirely cosmetic and hides
# the real one.
#
# Usage:  ./build.sh [version]        # default: the version in versions.json
set -euo pipefail

cd "$(dirname "$0")"

OL_VERSION="${1:-10.10.0}"
ESBUILD_VERSION="0.25.0"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

cp entry.js "$workdir/"
cd "$workdir"
npm install --silent --no-package-lock "ol@${OL_VERSION}"

npx "esbuild@${ESBUILD_VERSION}" entry.js \
    --bundle \
    --format=esm \
    --target=es2023 \
    --minify \
    --sourcemap \
    --legal-comments=inline \
    --banner:js="/*! OpenLayers ${OL_VERSION} | BSD-2-Clause | https://openlayers.org
 * Tree-shaken build over geoengine's entry.js -- see build.sh in this directory.
 * Not a pristine upstream file: it carries only the symbols entry.js exports. */" \
    --outfile=ol.esm.js

cd - >/dev/null
cp "$workdir/ol.esm.js" "$workdir/ol.esm.js.map" .
cp "$workdir/node_modules/ol/LICENSE.md" LICENSE.md

echo "Rebuilt ol.esm.js at ${OL_VERSION} ($(stat -c%s ol.esm.js) bytes)."
echo "Update ../versions.json in the same commit."
