#!/usr/bin/env bash
set -euo pipefail

mkdir -p dist
rm -f dist/mirror.zip
zip -9 -q -r dist/mirror.zip mirror
