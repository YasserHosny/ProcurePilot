"""Check that no demo video still shows the old contact (owner, 2026-11-15).

OCR (tesseract, English) on the closing seconds of every video, where the end card and the call to action sit,
at 3 frames a second. A file passes when no frame shows the old number or the founder's name or personal email,
and some frame shows the company number.

usage: python verify_contact.py <video> ...      (prints one line per file; exit 1 on any failure)
"""
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OLD = re.compile(r'4140|102\s*735|1027354140|yasser|hosny', re.I)
NEW = re.compile(r'5087\s*8238|1050878238')
TAIL = 14  # seconds


def check(path):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['ffmpeg', '-v', 'error', '-sseof', f'-{TAIL}', '-i', str(path), '-vf',
                        'fps=3,scale=1280:-2', f'{d}/%03d.png'], check=True)
        old, new = [], 0
        for png in sorted(Path(d).glob('*.png')):
            text = subprocess.run(['tesseract', str(png), '-', '-l', 'eng', '--psm', '11'], capture_output=True,
                                  text=True, env={**os.environ, 'OMP_THREAD_LIMIT': '1'}).stdout  # threads stall
            if OLD.search(text):
                old.append(png.stem)
            if NEW.search(text.replace('\n', ' ')):
                new += 1
        return path, old, new


def main(paths):
    bad = 0
    with ThreadPoolExecutor(4) as pool:
        for path, old, new in pool.map(check, paths):
            ok = not old and new > 0
            bad += not ok
            print(('ok  ' if ok else 'FAIL'), f'new-number frames {new:3d}', f'old frames {old[:5]}', path, flush=True)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
