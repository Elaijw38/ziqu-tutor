# -*- coding: utf-8 -*-
"""把龟宝做成助教形象：抠白底 → 头像资源 → 接进对话界面 + 人设提示词。

素材来源：本人另一件作品「字趣」的原创形象 guibao-front.png（只读复制，不改原文件）。
"""
import os

import numpy as np
from PIL import Image

SRC = r"C:\DSH\字趣\assets\guibao-front.png"
DST = r"C:\DSH\ziqu-tutor\web\assets\guibao.png"

im = Image.open(SRC).convert("RGB")
w, h = im.size
# 从四边 flood fill 白底（用 PIL 的 floodfill 标记，内部白色（眼睛高光）不会被误伤）
from PIL import ImageDraw
MAGIC = (255, 0, 255)
for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
           (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
    ImageDraw.floodfill(im, pt, MAGIC, thresh=28)

a = np.asarray(im).astype(np.int16)
mask = (a[:, :, 0] == 255) & (a[:, :, 1] == 0) & (a[:, :, 2] == 255)
alpha = np.where(mask, 0, 255).astype(np.uint8)
rgb = np.asarray(im).astype(np.uint8).copy()
rgb[mask] = (255, 255, 255)
out = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
bb = out.split()[-1].getbbox()
if bb:
    out = out.crop(bb)

# 头像用 256 足够（前端显示 26~96px，高分屏也不糊）
H = 256
out = out.resize((round(out.width * H / out.height), H), Image.LANCZOS)
out.save(DST, "PNG", optimize=True)
print("  写出 %s  %dx%d  %d KB" % (DST, out.width, out.height, os.path.getsize(DST) // 1024))
