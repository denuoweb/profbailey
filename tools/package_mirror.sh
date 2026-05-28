#!/usr/bin/env bash
set -euo pipefail

mkdir -p dist
zip -9 -q -r dist/mirror.zip mirror
