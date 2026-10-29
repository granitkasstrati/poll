#!/bin/sh
# render.sh <out.png> [layers] [width]  - quick PNG of the board for review
D=$(dirname "$0")/..
L=${2:-F.Cu,B.Cu,F.SilkS,F.CrtYd,Edge.Cuts}
T=$(mktemp --suffix=.svg)
kicad-cli pcb export svg --exclude-drawing-sheet --page-size-mode 2 -l "$L" -o "$T" "$D/gdc1.kicad_pcb" >/dev/null 2>&1
rsvg-convert -w "${3:-2000}" -b white "$T" -o "$1"
rm -f "$T"
