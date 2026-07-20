# 遗传扰动数据源 — 分析与使用方案

决策上下文（已定）：**先做遗传扰动**（敲除 / TF 诱导）；**尽量把数据源都用上**，多跑分数再决定取舍；
**只用本地模型推理**（无 API）。

本文档 = 每个源"是什么"的事实分析 + 跨源"怎么用"的方案（后半部分标了「待讨论」，见 chat）。

---

## 源 1 — Deleteome（主力，Tahoe 替身）

- **论文**：Kemmeren et al., *Cell* 2014, "Large-Scale Genetic Perturbations Reveal Regulatory
  Networks and an Abundance of Gene-Specific Repressors." DOI `10.1016/j.cell.2014.02.054`,
  PubMed `24766815`。
- **数据门户**：http://deleteome.holstegelab.nl （下载页 `downloads.php`）。
- **DeleteomeTools**（R 包，做相似度分析用得上）：https://github.com/AitchisonLab/DeleteomeTools
  （NAR Genom. Bioinform. 2025）。

### 实验设计
- **~1484 个单基因敲除株**，每株用双通道微阵列测全基因组表达，**每株 vs 野生型（WT）对照**，带
  dye-swap 重复。读出 ~6000 个 ORF。
- 扰动类型 = **功能缺失（deletion / loss-of-function）**；稳态（对数期，SC 培养基）。**基本是单一条件**。

### 文件格式（tab 分隔）
- **行 = 基因**：`reporterId` + 系统 ORF 名 + 标准基因名（symbol）三列标识。
- **列 = 敲除株，每株 3 列**：`M`（= log2(mutant/WT)，即 logFC）、`A`（平均信号强度）、`p`（p 值）。
- 附带 3 组内部对照比较（matA vs matα、YPD vs SC、二倍体 vs 单倍体）。

可下的几个版本：
| 文件 | 内容 |
|---|---|
| `deleteome_all_mutants_controls.txt` | 全部株，含 WT-variable 基因 |
| `deleteome_all_mutants_ex_wt_var_controls.txt` | 全部株，**去掉 WT-variable 基因（更干净，推荐）** |
| `deleteome_responsive_mutants_(ex_wt_var_)controls.txt` | 只留**"responsive"株**（≥4 个显著变化，FC>1.7 & p<0.05） |
| `deleteome_all_mutants_svd_transformed.txt` | 去掉"慢生长特征"的 SVD 版（只有 M 值） |

### → 直接产出 DE/DIR 标签（关键优势）
每个 `(敲除基因 P, 读出基因 G)` 格子已有 `M` + `p`，所以我们的 `prepare` **不用跑 scanpy
`rank_genes_groups`**，只做阈值：
- **DE**：`p<0.05 & |M|>阈值` → label=1（Deleteome 原生用 FC>1.7，即 `|M|>~0.77`）；label=0 从明显不显著里抽。
- **DIR**：`sign(M)`（M>0 升高，M<0 降低）。
- **扰动子 P** = 被敲的基因；**读出 G** = 微阵列上的基因。同一个基因可在一处当 P、另一处当 G。
- ⚠️ **慢生长混杂**：很多敲除会拖慢生长，产生一大片非特异的"环境应激/生长"表达变化。建议用
  `ex_wt_var` 版，必要时参考 `svd_transformed`（已扣掉慢生长信号）来定义更"特异"的 DEG。

---

## 源 2 — IDEA（Induction Dynamics Expression Atlas，Hackett 2020, Calico）

- **门户**：http://idea.research.calicolabs.com ；论文 *Mol. Syst. Biol.* 2020，
  "Learning causal networks using inducible transcription factors and transcriptome-wide time series."
- **设计**：~200 个 TF，各自用 β-estradiol **可诱导过表达**，chemostat 培养，**RNA-seq 时序**
  （诱导后 ~90 分钟内多个时间点）。
- **扰动类型 = 功能获得（induction / gain-of-function）+ 动态时序**；技术是 RNA-seq（与 Deleteome 的
  微阵列不同）。
- **→ 标签**：需把时序 collapse 成每个 `(TF, G)` 一个值 —— 例如取相对 t0 的**峰值 |log2FC|** + 显著性，
  DIR 取符号；或直接用论文提供的模型响应调用。
- **价值**：和 Deleteome **方向互补**（诱导 vs 敲除）；TF→靶 ground truth 极强 → 对 **DIR 方向推理**
  和**可解释性核查（对 YEASTRACT）** 特别有用。局限：只有 TF 当扰动子。

---

## 源 3 — Hughes compendium（Rosetta, 2000）

- 300 个敲除 + 化学/环境处理的微阵列 compendium，格式类似 Deleteome（ratio + p）。更老更小。
- **用途**：独立的**跨实验室泛化测试集** / 交叉验证；阈值化逻辑同 Deleteome。

---

## 源 4 — 你自己的 `yeast-rank-cross-lab` 矩阵（⚠️ 需你确认内容）

- 从记忆看是 `het_profile_matrix` / growth / `yp_matrix` 之类 —— 这些像是**生长/适合度表型**，
  **不是转录组**。
- 如果确实是表型：那它是**另一种读出模态**，不能直接当 DE 标签。要么当**另一个任务**（预测生长表型），
  要么当**特征/上下文**。接入前需要你确认这些矩阵到底装的是什么（扰动-表达？还是扰动-生长？维度？）。

---

## 跨源使用方案（待讨论要点）

1. **标识符统一**：以**系统 ORF 名**（如 `YFL039C`）为规范；建一张 SGD 别名表
   （symbol ↔ ORF ↔ SGD ID）。扰动子和读出都按 ORF 键。
2. **"上下文/细胞系"轴换成什么**（对应问题 2 的多条件）：遗传数据在单个数据集内基本是单条件，所以
   "多条件"在这里 ≈ **多数据集/多扰动类型**。候选：(a) 数据集/平台当上下文（Deleteome / IDEA / Hughes），
   (b) 扰动类型当上下文（deletion vs induction），(c) 菌株背景/培养基。**倾向 (a)+(b) 组合**。
3. **阈值跨平台对齐**：**结论 = 不做全局数值对齐，各源用各自原生阈值即可。**
   理由（关键）：模型看不到 query 的 M/p 数值、也看不到阈值，它只能从**同上下文的 few-shot 例子**
   in-context 校准出该数据集的 DE 门槛。所以跨平台阈值差异会被**自校准吸收** —— 但**前提是**：
   (i) 检索例子来自**同一数据集/上下文**，(ii) 例子带**真标签**（即必须先修 VCWorld 的随机标签 bug，
   见 [`vcworld_pipeline.md`](vcworld_pipeline.md) §6 note 1）。
   阈值仍真正影响两件事（与文字无关）：**标签质量**（太松/太紧→标签变噪声，尤其微阵列 p 值）和
   **类别基率**（→ few-shot 正负比 & 评测需**按数据集分开报**，不能只看汇总 accuracy）。
4. **合并策略**：产出一张统一 CSV，加 `dataset/context` 列 → `pert, gene, label, split, dataset`。
   **按扰动子切 train/test，且跨数据集把整个扰动子一起 hold out**，避免泄漏。
5. **检索复用**：Deleteome/Hughes 的扰动子可以是任意基因，IDEA 只有 TF；读出基因大面积重叠 →
   支持跨数据集的类比检索（"相似扰动子在另一个数据集里的响应"当证据）。

> 上面 1–5 是提案，具体在 chat 里定。定完我把结论回填到 PLAN 的 Phase 1（prepare）。
