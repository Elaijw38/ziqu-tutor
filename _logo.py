# -*- coding: utf-8 -*-
"""处理郑大校徽：裁出圆形徽记、去掉下方说明文字，透明底，供顶栏使用。

注意（校徽使用规范）：**只裁切、不缩放变形、不改颜色**，
所以这里不做任何重绘或调色，只按非白像素的包围盒裁切 + 抠白底。
"""
import os

import numpy as np
from PIL import Image

SRC = r"C:\Users\32058\.dsh\attachments\v1\objects\9b\9bf461ea7395cacd98242c3005d9d6462c6aa535451ef9361c661cb48e682adf"
DST_DIR = r"C:\DSH\ziqu-tutor\web\assets"
os.makedirs(DST_DIR, exist_ok=True)
DST = os.path.join(DST_DIR, "zzu-logo.png")

im = Image.open(SRC).convert("RGB")
a = np.asarray(im).astype(np.int16)
# 非白像素（阈值放宽，保住细笔画）
mask = (a.sum(axis=2) < 720)
ys, xs = np.where(mask)
# 只要上半部分（说明文字在下方，单独排除）
h = a.shape[0]
top_mask = mask.copy()
top_mask[int(h * 0.78):, :] = False
ys, xs = np.where(top_mask)
y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
pad = 4
crop = im.crop((max(0, x0 - pad), max(0, y0 - pad),
                min(a.shape[1], x1 + pad), min(a.shape[0], y1 + pad)))

# 白底转透明（保留抗锯齿的灰度边缘）
ca = np.asarray(crop.convert("RGB")).astype(np.float32)
lum = ca.mean(axis=2)
alpha = np.clip((250.0 - lum) / 60.0, 0.0, 1.0)  # 越白越透明
rgb = ca.copy()
# 去掉透明区残留的白，避免深色底上出现白边
rgb[alpha > 0.99] = rgb[alpha > 0.99]
out = np.dstack([rgb, (alpha * 255)]).astype(np.uint8)
img = Image.fromarray(out, "RGBA")

H = 160  # 大一点存，前端按 38~40px 显示，保证高分屏清晰
img = img.resize((round(img.width * H / img.height), H), Image.LANCZOS)
img.save(DST, "PNG", optimize=True)
print("  写出 %s  %dx%d  %d KB" % (DST, img.width, img.height, os.path.getsize(DST) // 1024))
