import sys, subprocess, os
sys.path.insert(0, os.environ['V2']); sys.path.insert(0, os.environ['V2'] + '/deps')
import numpy as np
from audit import load_templates, match_frame
from paths import FF
templates = load_templates()
for path in sys.argv[1:]:
    phone = 'phone' in path; W, H = (390, 844) if phone else (1920, 1080)
    p = subprocess.Popen([str(FF), '-v', 'error', '-i', path, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
    n = hits = 0
    while True:
        raw = p.stdout.read(W * H)
        if len(raw) != W * H: break
        if match_frame(np.frombuffer(raw, np.uint8).reshape(H, W), templates): hits += 1
        n += 1
    print(os.path.basename(path), 'frames', n, 'frames with email', hits, flush=True)
