#!/bin/bash
# Assemble the film.
#
# One beat is one narration file and one visual, and the visual is cut to the
# narration's length rather than the other way round. Padding narration to fit
# footage is exactly how dead air gets shipped.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p clips out

W=1920
H=1080

# beat | visual sources, comma separated, split evenly across the beat
MANIFEST="
01_notice|sources/01_notice_head.png
02_expiry|sources/02_notice_expired.png
03_price|sources/03_facade.png
04_meter|sources/04_press_head.png,sources/05_press_quote.png
06_city|casts/01_city.cast
07_absence|../docs/frames/reveal-1.png
08_read|../docs/frames/reveal-2.png
09_engine|../docs/frames/reveal-3.png
10_pass|casts/03_pass.cast
11_holds|casts/03_pass.cast
12_prose|casts/05_prose.cast
13_question|casts/06_question.cast
14_console|../console/shots/queue-1440.png
15_draft|casts/07_draft.cast
16_gate|../docs/frames/reveal-4.png
17_veto|casts/08_veto.cast
18_unattended|casts/09_unattended.cast
19_close|cards/10_close.png
"

render_cast() {
  local cast="$1" gif="$2"
  [ -f "$gif" ] && return
  agg --theme monokai --font-size 20 --idle-time-limit 1 \
      --last-frame-duration 2 --fps-cap 30 "$cast" "$gif" >/dev/null 2>&1
}

# A still or a short gif becomes a clip of exactly DURATION seconds by cloning
# its last frame. Everything is scaled into the same 1920x1080 box first, so
# concat never sees a resolution change.
make_clip() {
  local src="$1" duration="$2" out="$3"
  ffmpeg -y -loglevel error \
    $([ "${src##*.}" = "png" ] || [ "${src##*.}" = "jpg" ] && echo "-loop 1 -t $duration") \
    -i "$src" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x0a0e14,setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=${duration}" \
    -t "$duration" -an -c:v libx264 -pix_fmt yuv420p -preset veryfast "$out"
}

segments=()
for row in $MANIFEST; do
  beat="${row%%|*}"
  sources="${row##*|}"
  narration="narration/${beat}.wav"
  [ -f "$narration" ] || { echo "missing $narration"; exit 1; }
  total=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$narration")

  IFS=',' read -ra parts <<< "$sources"
  share=$(echo "scale=3; $total / ${#parts[@]}" | bc)

  i=0
  pieces=()
  for src in "${parts[@]}"; do
    if [ "${src##*.}" = "cast" ]; then
      gif="clips/$(basename "${src%.cast}").gif"
      render_cast "$src" "$gif"
      src="$gif"
    fi
    piece="clips/${beat}_${i}.mp4"
    make_clip "$src" "$share" "$piece"
    pieces+=("$piece")
    i=$((i + 1))
  done

  # video for this beat, then marry it to its own narration line
  if [ "${#pieces[@]}" -gt 1 ]; then
    printf "file '%s'\n" "${pieces[@]/#/$PWD/}" > "clips/${beat}.txt"
    ffmpeg -y -loglevel error -f concat -safe 0 -i "clips/${beat}.txt" -c copy "clips/${beat}_v.mp4"
  else
    cp "${pieces[0]}" "clips/${beat}_v.mp4"
  fi

  ffmpeg -y -loglevel error -i "clips/${beat}_v.mp4" -i "$narration" \
    -c:v copy -c:a aac -b:a 192k -shortest "clips/${beat}_av.mp4"
  segments+=("clips/${beat}_av.mp4")
  echo "  ${beat}  ${total}s"
done

printf "file '%s'\n" "${segments[@]/#/$PWD/}" > clips/all.txt
ffmpeg -y -loglevel error -f concat -safe 0 -i clips/all.txt \
  -c:v libx264 -pix_fmt yuv420p -preset medium -crf 20 -c:a aac -b:a 192k out/lapse.mp4

echo
echo "runtime: $(ffprobe -v error -show_entries format=duration -of csv=p=0 out/lapse.mp4)s"
echo "silence check (any gap over 1.5s is a defect):"
ffmpeg -i out/lapse.mp4 -af silencedetect=noise=-35dB:d=1.5 -f null - 2>&1 | grep -i "silence_duration" || echo "  none"
