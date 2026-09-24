#!/bin/bash
# Remap the Wacom tablet's active area to a single monitor output (xrandr
# name, e.g. eDP-1-0 or HDMI-0) and focus the GoodNotes window there.
#
# Uses xinput's "Coordinate Transformation Matrix" directly instead of
# `xsetwacom --set ... MapToOutput`: on this machine's hybrid NVIDIA+AMD
# PRIME setup, xsetwacom can't resolve either output by name ("Unable to
# find an output") because its RandR output lookup doesn't span providers.
# The matrix approach queries geometry straight from `xrandr --query`, which
# sees both outputs fine, and computes the same per-output scale/offset
# xsetwacom's MapToOutput would have applied.
#
# Invoked by GNOME custom keyboard shortcuts (see install.sh): two dedicated
# per-monitor shortcuts pass an explicit output name; a third "toggle"
# shortcut passes no argument (or "toggle") and flips between eDP-1-0 and
# HDMI-0 based on the stylus's current Y-offset. Device type names
# ("stylus"/"eraser") are used instead of numeric xinput IDs since IDs shift
# across replugs.
set -euo pipefail

export DISPLAY="${DISPLAY:-:1}"
export XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"

OUTPUT="${1:-toggle}"
if [ "$OUTPUT" = "toggle" ]; then
    stylus_id="$(xinput list --id-only "Wacom One by Wacom M Pen stylus" 2>/dev/null | head -1)"
    cur_oy="$(xinput list-props "$stylus_id" 2>/dev/null | grep "Coordinate Transformation Matrix" | awk -F'[,:]' '{print $7}' | tr -d ' ')"
    # eDP-1-0 (laptop) sits at Y-offset 0.5 in the stacked layout; anything
    # else (including HDMI-0's 0, or no matrix set yet) toggles to it.
    if [ "$cur_oy" = "0.500000" ]; then
        OUTPUT="HDMI-0"
    else
        OUTPUT="eDP-1-0"
    fi
fi

read -r SCREEN_W SCREEN_H < <(xrandr --query | head -1 | grep -oP 'current \K[0-9]+ x [0-9]+' | tr -d 'x')

GEOM="$(xrandr --query | awk -v out="$OUTPUT" '$1 == out && $2 == "connected" { for (i=3;i<=NF;i++) if ($i ~ /^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/) { print $i; exit } }')"
if [ -z "$GEOM" ]; then
    GEOM="$(xrandr --query | awk -v out="$OUTPUT" '$1 == out && $2 == "connected" && $3 ~ /^primary$/ { for (i=4;i<=NF;i++) if ($i ~ /^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+/) { print $i; exit } }')"
fi
if [ -z "$GEOM" ]; then
    echo "wacom-switch-monitor: output '$OUTPUT' not found or not connected" >&2
    exit 1
fi

W="${GEOM%%x*}"
REST="${GEOM#*x}"
H="${REST%%+*}"
REST="${REST#*+}"
X="${REST%%+*}"
Y="${REST#*+}"

SX=$(awk -v w="$W" -v sw="$SCREEN_W" 'BEGIN { printf "%.6f", w/sw }')
SY=$(awk -v h="$H" -v sh="$SCREEN_H" 'BEGIN { printf "%.6f", h/sh }')
OX=$(awk -v x="$X" -v sw="$SCREEN_W" 'BEGIN { printf "%.6f", x/sw }')
OY=$(awk -v y="$Y" -v sh="$SCREEN_H" 'BEGIN { printf "%.6f", y/sh }')

xinput list --id-only "Wacom One by Wacom M Pen stylus" 2>/dev/null | while read -r id; do
    xinput set-prop "$id" "Coordinate Transformation Matrix" "$SX" 0 "$OX" 0 "$SY" "$OY" 0 0 1
done
xinput list --id-only "Wacom One by Wacom M Pen eraser" 2>/dev/null | while read -r id; do
    xinput set-prop "$id" "Coordinate Transformation Matrix" "$SX" 0 "$OX" 0 "$SY" "$OY" 0 0 1
done

win="$(xdotool search --name "GoodNotes" | head -1 || true)"
if [ -n "$win" ]; then
    xdotool windowactivate "$win"
fi
