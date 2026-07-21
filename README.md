# Clipcara

A-B loop audio player. Open a file, mark points A and B, and the selection
repeats. Intended for transcription and phrase practice.

Playback uses Qt Multimedia. The waveform is decoded with libsndfile
(wav, flac, ogg, mp3). Formats libsndfile cannot decode (m4a, aac, wma)
still play but show no waveform.

## Install

    python -m venv .venv
    .venv/bin/pip install .
    .venv/bin/clipcara [file]

## Usage

Click the timeline to seek. Drag to select a loop region. Double-click to
select a four-second region around the cursor. Marking a new In at or after
the current Out clears the Out, and vice versa.

Scroll on the timeline to zoom around the cursor; horizontal scroll pans.
Zoomed views are re-decoded at higher resolution. A bar along the bottom
edge shows where the view sits in the file.

Save Loop stores the current A-B region under a name; saved loops are
listed per file in the dropdown and persist across sessions. Export
writes the A-B region to a WAV file.

| Key | Action |
|-----|--------|
| Space | Play / pause |
| S | Stop |
| Left / Right | Skip 15 s back / forward |
| Up / Down | Volume |
| I / O | Mark A / B at the playhead |
| , / . | Nudge A by 50 ms |
| < / > | Nudge B by 50 ms |
| L | Toggle loop |
| Esc | Clear marks |
| Z | Zoom to A-B selection |
| F | Zoom out to full file |
| E | Export A-B region |
| [ / ] | Playback speed down / up |
| 1 | Reset speed to 1.00x |
| Ctrl+O | Open file |

## Packaging

Briefcase builds a native application (macOS .app; Linux AppImage, deb,
or Flatpak) from the same source:

    .venv/bin/pip install briefcase
    .venv/bin/briefcase build
    .venv/bin/briefcase run

## Tests

    .venv/bin/pip install ".[test]"
    .venv/bin/pytest

## License

GPL-3.0. See LICENSE.
