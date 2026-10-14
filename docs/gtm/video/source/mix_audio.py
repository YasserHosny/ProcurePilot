"""Trim the five cues and mix each clip's audio: music segment + beat-locked cues, normalised to -14 LUFS."""
import subprocess
from pathlib import Path

S = Path("/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad")
FF = str(S / "pylib-ff/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2")
SFX = S / "audio/sfx"
CUT = SFX / "cut"
OUT = S / "render/audio"
MUSIC = S / "audio/dayfox-antalya-beaches-119047.mp3"
CUT.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
B = 0.5341  # one beat at 112.35 BPM

# name -> (file, start, duration, fade-out)
cues = {
    "tick": ("humordome-soft-ui-pop-light-minimal-click-451232.mp3", 0.02, 0.13, 0.04),
    "swish": ("biww-short-swoosh-whoosh-sound-561933.mp3", 0.11, 0.30, 0.08),
    "pop": ("dragon-studio-clean-minimal-pop-467466.mp3", 0.14, 0.18, 0.05),
    "whoosh": ("sdanezis-soft-luxury-air-whoosh-8-592506.mp3", 0.0, 0.86, 0.2),
    "chime": ("universfield-positive-notification-351299.mp3", 0.0, 0.9, 0.3),
}


def run(args):
    subprocess.run([FF, "-hide_banner", "-v", "error", "-y", *args], check=True)


for name, (f, ss, t, fo) in cues.items():
    run(["-ss", str(ss), "-t", str(t), "-i", str(SFX / f),
         "-af", f"afade=t=out:st={t - fo}:d={fo}", "-ar", "48000", "-ac", "2", str(CUT / f"{name}.wav")])

GAIN = {"tick": -6, "swish": -4, "pop": 0, "whoosh": -6, "chime": -3}


def mix(out, music_start, length, events, fade_out=None, dip=None):
    """events: list of (cue, time_s). dip: (start, end) seconds where music drops a further 3 dB."""
    inputs = ["-ss", f"{music_start:.3f}", "-t", f"{length:.3f}", "-i", str(MUSIC)]
    for cue, _ in events:
        inputs += ["-i", str(CUT / f"{cue}.wav")]
    music = "[0:a]aresample=48000,volume=-4dB"
    if dip:
        music += f",volume=enable='between(t,{dip[0]},{dip[1]})':volume=-3dB"
    if fade_out:
        music += f",afade=t=out:st={length - fade_out}:d={fade_out}"
    parts = [music + "[m]"]
    labels = ["[m]"]
    for i, (cue, at) in enumerate(events, start=1):
        ms = max(0, int(round(at * 1000)))
        parts.append(f"[{i}:a]volume={GAIN[cue]}dB,adelay={ms}|{ms}[c{i}]")
        labels.append(f"[c{i}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,"
                 f"apad,atrim=0:{length},loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    run([*inputs, "-filter_complex", ";".join(parts), "-map", "[a]", "-ar", "48000", "-c:a", "pcm_s16le", str(OUT / out)])


def sting_events(scale):
    s = scale
    return [("tick", 1 * B * s), ("tick", 1.5 * B * s), ("swish", 1.9 * B * s),
            ("pop", 3 * B * s - 0.02), ("whoosh", 3.5 * B * s), ("chime", 5 * B * s)]


# 16:9 — sting starts on the track beat at 2:50.25, end card follows seamlessly
mix("sting-16x9.wav", 170.25, 4.5, sting_events(1.0), dip=(1.45, 2.1))
mix("endcard-16x9.wav", 174.75, 5.5, [], fade_out=1.5)
# 9:16 fast — sting on the beat at 2:53.52 (two-thirds speed: pop on beat 2)
mix("sting-9x16-fast.wav", 173.52, 3.0, sting_events(2 / 3), dip=(0.95, 1.45))
mix("endcard-9x16.wav", 176.52, 5.5, [], fade_out=1.5)
print("mixed:", sorted(p.name for p in OUT.iterdir()))

# Combined outros (sting + end card) mixed as one piece so the level is continuous across the cut
mix("outro-16x9.wav", 170.25, 10.0, sting_events(1.0), fade_out=1.5, dip=(1.45, 2.1))
mix("outro-9x16.wav", 173.52, 8.5, sting_events(2 / 3), fade_out=1.5, dip=(0.95, 1.45))
print("mixed outros")
