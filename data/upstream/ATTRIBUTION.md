# 上游数据署名

`jgw_1203_labeled.json` 原样取自公开数据集，未修改字段与取值。

- **数据集**：Oracle Bone Glyphs: Parametric Vector Dataset (v0.3)
- **作者**：Qing-sheng Li（李清生）、Yu-lin Bian（边玉林）
- **论文**：Qing-sheng Li and Yu-lin Bian. *An Interpretable Parametric Representation
  and Open Dataset for Oracle Bone Script: Adaptive Arc Segmentation and SVG Resource.*
  npj Heritage Science, 2026.
- **许可**：CC BY 4.0（https://creativecommons.org/licenses/by/4.0/）
- **DOI**：10.5281/zenodo.22467946
- **镜像**：https://github.com/aylqs2025/oracle-bone-jgw-1203
  提交 `5496ad559f81ae8632f3915e8ec2beb705c64ba3`
- **规模**：1,203 个甲骨字形；按现代字去重后 1,169 个字
- **字段**：`glyph_id`、`modern_char`、`unicode`、`char_form`、`encoding_status`、
  `pinyin`、`n_points`、`n_strokes`、`stroke`

## 使用口径

- `pinyin` 在上游仅作辅助检索字段，未标声调；本项目转述时注明“数据集拼音，未标声调”。
- `n_strokes` 是**甲骨字形**的笔画数，与现代通行汉字的笔画数不一定相同
  （例：日，甲骨字形 3 画；现代汉字 4 画）。转述时必须说明，不能当作现代笔画数。
- `unicode` 指向现代字，甲骨字形本身没有独立编码。
- 同一现代字可能对应多个字形（如 39 与 283 都是「萑」），这是整理上的异体区分，不是重复。
- 本项目的 `data/kb.jsonl` 是**派生数据**，每条都带 `source` 字段，便于逐条核对。
