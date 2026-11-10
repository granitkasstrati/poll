#!/usr/bin/env bash
# Concatenate the sources into one self-contained page: index.html
set -euo pipefail
cd "$(dirname "$0")/src"
{
  cat head.html c1.html c2.html c3.html c4.html tail.html
  for f in shell cmds awk world missions ui; do printf '<script>\n'; cat "$f.js"; printf '</script>\n'; done
} > ../index.html
echo "built index.html ($(wc -c < ../index.html) bytes)"
