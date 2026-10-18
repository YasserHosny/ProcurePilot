import random, sys
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
random.seed(7)
src = Image.open(sys.argv[1]).convert("RGB")
W, H = 1536, 2048  # phone photo, WhatsApp-sized
# Desk background: warm wood-ish gradient with grain streaks.
bg = Image.new("RGB", (W, H), (120, 84, 56))
d = ImageDraw.Draw(bg)
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=(int(128 - 30 * t), int(90 - 22 * t), int(60 - 16 * t)))
for _ in range(260):
    y = random.randint(0, H); c = random.randint(-18, 14)
    d.line([(0, y), (W, y + random.randint(-40, 40))], fill=(110 + c, 76 + c, 50 + c), width=random.randint(1, 3))
bg = bg.filter(ImageFilter.GaussianBlur(2))
# Paper: slightly warm, a little darker, perspective-skewed (photographed from the bottom-right).
paper = ImageEnhance.Brightness(src).enhance(0.96)
paper = Image.blend(paper, Image.new("RGB", paper.size, (246, 240, 226)), 0.10)
sw, sh = paper.size
quad = [(170, 140), (1400, 205), (1475, 1930), (95, 1870)]  # TL, TR, BR, BL in the output
def coeffs(dst, srcpts):
    import itertools
    A, B = [], []
    for (x, y), (u, v) in zip(dst, srcpts):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    # Solve 8x8 by Gaussian elimination.
    n = 8; M = [row + [b] for row, b in zip(A, B)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [a - f * b for a, b in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]
c = coeffs(quad, [(0, 0), (sw, 0), (sw, sh), (0, sh)])
warped = paper.transform((W, H), Image.PERSPECTIVE, c, Image.BICUBIC)
mask = Image.new("L", (sw, sh), 255).transform((W, H), Image.PERSPECTIVE, c, Image.BICUBIC)
# Soft shadow under the paper.
shadow = Image.new("L", (W, H), 0); ImageDraw.Draw(shadow).polygon([(x + 18, y + 22) for x, y in quad], fill=150)
shadow = shadow.filter(ImageFilter.GaussianBlur(22))
bg.paste(Image.new("RGB", (W, H), (35, 22, 14)), (0, 0), shadow)
bg.paste(warped, (0, 0), mask)
# Uneven light: brighter top-left, dimmer bottom-right, plus the phone's own shadow at the bottom.
light = Image.new("L", (W, H)); ld = ImageDraw.Draw(light)
for y in range(H):
    ld.line([(0, y), (W, y)], fill=int(255 - 70 * (y / H)))
light = Image.composite(light, Image.linear_gradient("L").rotate(90).resize((W, H)), Image.new("L", (W, H), 200))
img = Image.composite(bg, Image.new("RGB", (W, H), (0, 0, 0)), light)
ph = Image.new("L", (W, H), 0); ImageDraw.Draw(ph).ellipse([300, 1650, 1500, 2400], fill=70)
img = Image.composite(Image.new("RGB", (W, H), (20, 15, 10)), img, ph.filter(ImageFilter.GaussianBlur(120)))
# Camera softness and sensor noise.
img = img.filter(ImageFilter.GaussianBlur(0.9))
noise = Image.effect_noise((W, H), 12).convert("RGB")
img = Image.blend(img, noise, 0.04)
img = ImageEnhance.Contrast(img).enhance(1.05)
img.save(sys.argv[2], "JPEG", quality=72)
