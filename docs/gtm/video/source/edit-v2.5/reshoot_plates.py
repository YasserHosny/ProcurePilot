"""PPS-84 re-shoot: extract plates from the masked Arabic re-shoot clips into each market's plate folder as r-<clip>.
Refuses to run unless the re-shoot privacy audit found no email left in any masked clip."""
from pathlib import Path
import json, subprocess
from PIL import Image
from reshoot_privacy import FF, OUT, clips, RAW, ROOT
PLATES = {'ar': ROOT / 'plates-eg', 'sa-ar': ROOT / 'plates-sa'}

def main():
    after = json.loads((ROOT / 'proof/reshoot-after.json').read_text())
    assert len(after) == len(clips(RAW)) and not any(v['matches'] for v in after.values()), 're-shoot privacy audit required'
    for market, plates in PLATES.items():
        meta = json.loads((plates / 'meta.json').read_text())
        for src in sorted((OUT / market).glob('*.mp4')):
            name = 'ar/r-' + src.stem; folder = plates / name; folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob('*.jpg'): old.unlink()
            subprocess.run([FF, '-v', 'error', '-y', '-i', str(src), '-q:v', '2', '-threads', '2', str(folder / '%04d.jpg')], check=True)
            w, h = Image.open(folder / '0001.jpg').size
            meta[name] = {'box': [0, 0, w, h], 'frames': len(list(folder.glob('*.jpg')))}
            print('PLATE', market, name, meta[name], flush=True)
        (plates / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')

if __name__ == '__main__': main()
