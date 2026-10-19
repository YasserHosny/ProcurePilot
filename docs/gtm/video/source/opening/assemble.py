import json, sys, subprocess
d, out, ff = sys.argv[1:4]
t = json.load(open(d + '/times.json'))
with open(d + '/list.txt', 'w') as f:
    for i, ts in enumerate(t):
        dur = (t[i + 1] - ts) if i + 1 < len(t) else 0.5
        f.write(f"file '{d}/{i:05d}.png'\nduration {dur:.4f}\n")
    f.write(f"file '{d}/{len(t)-1:05d}.png'\n")
subprocess.run([ff, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', d + '/list.txt', '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '16', '-preset', 'medium', out], check=True)
