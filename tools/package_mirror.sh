#!/usr/bin/env bash
set -euo pipefail

mkdir -p dist
zip -9 -r dist/mirror.zip mirror
