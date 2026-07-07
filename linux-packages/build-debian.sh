#!/usr/bin/env bash
# Aurora Music — Debian/Ubuntu/Kali .deb builder
# Usage: bash linux-packages/build-debian.sh
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cp "$ROOT/packaging/build_deb.sh" /tmp/aurora-deb-build.sh
cd "$ROOT" && bash packaging/build_deb.sh
