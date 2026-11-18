# Feedback audio fixtures (spec 025, T041)

Used by `tests/unit/test_feedback_validation.py` and `tests/integration/test_feedback.py`.
"libmagic says" is `magic.from_buffer(data, mime=True)` with python-magic-bin on Windows
(bundled libmagic); the Docker image uses Debian's libmagic, so the validator accepts aliases
and the unit test re-asserts these values to catch a change on either platform.

| File | Origin | libmagic says | Stored as |
|---|---|---|---|
| `recorded-chrome.webm` | Real Chrome 156 `MediaRecorder`, `audio/webm;codecs=opus`, 1.2 s tone | `video/webm` | `audio/webm` |
| `recorded-chrome.mp4` | Real Chrome 156 `MediaRecorder`, `audio/mp4;codecs=mp4a.40.2` (AAC), 1.2 s tone; ftyp brand `isom` | `video/mp4` | `audio/mp4` |
| `recorded-safari-style.mp4` | The Chrome MP4 with ftyp major brand patched to `mp42` (stand-in for Safari output, not recorded in Safari) | `video/mp4` | `audio/mp4` |
| `voice.m4a` | The Chrome MP4 with ftyp major brand patched to `M4A ` (iTunes / iOS voice memo brand) | `audio/x-m4a` | `audio/mp4` |
| `silence.mp3` | Hand-built: ID3v2.3 header plus 8 silent MPEG-1 Layer III frames (no encoder was available) | `audio/mpeg` | `audio/mpeg` |
| `tone.wav` | Python `wave`, 0.25 s, 8 kHz mono 16-bit sine | `audio/x-wav` | `audio/wav` |
| `renamed-fake.mp3` | Plain text with an audio extension | `text/plain` | rejected (415) |

Findings that drive `validation.py`:

* Audio-only WebM and audio-only MP4 from `MediaRecorder` are reported as **video**/webm and
  **video**/mp4, so those two container types are accepted only after the container is
  inspected for audio-only content (MP4: every `hdlr` handler is `soun`, at least one;
  WebM: an audio codec id and no video codec id).
* Not covered: Firefox (`MediaRecorder` defaults to `audio/ogg`, which the spec does not
  allow) and a real Safari recording. Neither could be produced in this environment.
