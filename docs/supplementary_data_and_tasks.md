# 双任务设计 + 酵母补充数据/任务调研

决策（2026-07-19）：在"扰动→表达"之外，**再并行做"扰动→生长表型"**；并调研还有哪些酵母数据/任务
适合当补充。VCWorld 只做了"扰动→表达"这一类，这里是我们相对原文的**扩展**。

---

## 两个主任务（都套 VCWorld 的 DE/DIR 式二分 + 方向框架）

### Task 1 — 扰动 → 表达（旗舰，直接对标 VCWorld）
- **问题**：敲除/诱导 `P` 会不会让基因 `G` 差异表达（DE, Yes/No）？升还是降（DIR）？
- **数据**：Deleteome（首发）→ 之后 IDEA / Hughes。见 [`data_sources.md`](data_sources.md)。
- **读出**：转录组（logFC + p 已现成）。

### Task 2 — 扰动 → 生长表型（并行新增）
同样做成"有没有表型 + 方向"的二分，好复用同一套 pipeline / 检索 / 模板。两种可选框架：

- **框架 A：单突变体适合度（chemical-genomics 式）**
  - **问题**：敲除 `P` 在条件 `C`（药物/胁迫）下有没有生长表型？更敏感（fitness↓）还是更抗（fitness↑）？
  - **数据**：Hillenmeyer 2008（1144 个 assay × 敲除库适合度，HIP+HOP）/ **你自己的 het & growth 矩阵**。
  - 扰动子 = 被敲基因；上下文 = 条件 `C`；读出 = 相对适合度。**这是"多条件"最自然落地的地方**
    （条件本身就是一个真上下文轴，比 Task 1 里"拿数据集当上下文"更实在）。

- **框架 B：遗传互作（SGA 式，双扰动）**
  - **问题**：同时敲 `A` + `B` 有没有遗传互作？负（合成致死/病）还是正（缓解/抑制）？
  - **数据**：Costanzo 2016 全基因组遗传互作网络。
  - 扰动子 = **基因对**（双敲）；这对 LLM 的"通路冗余/缓冲"推理特别对味 —— 白盒思路的高价值任务。

> **建议**：Task 2 先做**框架 A**（和你的矩阵直接对接，且天然多条件）；框架 B（SGA）作为"补充任务"里
> 最强的候选，稍后单独立项。

### ⚠️ 你的矩阵需确认（决定 Task 2-A 怎么接）
从上下文看你有 `het_profile_matrix` 和 `growth` 两个**同型**矩阵（可用 panel ~3520 列）。推测：
**行 = 敲除株/基因，列 = 条件/实验，值 = 适合度**，`het` 很可能是 **HIP（杂合缺失，单倍剂量不足谱）**。
请确认：**行是什么、列是什么、值是什么量纲**（fitness ratio? z-score? 生长速率?），以及 `het` vs `growth`
的区别。确认后我把它当 Task 2-A 的读出直接接进来。

---

## 补充数据 / 补充任务调研

### (a) 更多"扰动→表达"（增强 Task 1）
| 资源 | 内容 | 补充价值 |
|---|---|---|
| **IDEA**（Hackett 2020, Calico） | ~200 TF 诱导，RNA-seq 时序 | 功能获得 + 动态；强 TF→靶 ground truth，利于 DIR & 可解释性核查 |
| **Hughes/Rosetta compendium**（2000） | 300 敲除+化学处理，微阵列 | 独立跨实验室测试集 |
| **Gasch 2000 ESR** | WT 在 ~150 种环境胁迫下的表达 | 提供"条件扰动"轴（非遗传），可做上下文/背景 |
| 单细胞酵母（Jackson 2020 / Nadal-Ribelles 2019） | scRNA-seq GRN | 让读出回到单细胞（更贴 VCWorld 原味），但数据稀疏 |

### (b) 生长/适合度（支撑 Task 2）
| 资源 | 内容 | 门户 |
|---|---|---|
| **Hillenmeyer 2008** chemical-genomics | 1144 assay × 敲除库适合度（HIP/HOP），97% 基因有表型 | FitDB `chemogenomics.pharmacy.ubc.ca/fitdb` |
| **Costanzo 2016** SGA | ~6000 基因、23M 双突变、~35万正/55万负互作 | `thecellmap.org` / boonelab supplement |
| **Giaever 2002** 缺失库适合度 | 单缺失株生长 | — |
| **你的 het / growth 矩阵** | 待确认（见上） | 本地 |

### (c) 其它扰动模态（候选补充任务）
- **过表达**：Yeast ORF 过表达库（Sopko 2006；MoBY-ORF, Ho 2009；Douglas 2012）→ 功能获得表型，
  可做"过表达 P 有没有毒性/表型"任务，与敲除方向互补。
- **CRISPRi/dCas9** 敲低库 —— 剂量型扰动。

### (d) 知识源（喂检索/推理，不是任务本身）
SGD 描述 + GO、**YEASTRACT**（TF→靶，DIR 王牌）、STRING、BioGRID（物理+遗传）、KEGG、YeastNet。
**关键协同**：**Costanzo SGA profile 一物两用** —— 既是 Task 2-B 的数据，又是 Task 1 检索里
**扰动子相似度（perturbagen-sim）** 的最佳来源。

---

## 落地优先级建议
1. **Task 1 / Deleteome** 打通（旗舰，最快出分）。
2. **Task 2-A** 用你的 het/growth 矩阵（确认后）—— 复用同一 pipeline，天然多条件。
3. 补充：IDEA（增强 Task 1 的 DIR/可解释）、**SGA 遗传互作**（Task 2-B，白盒高价值补充任务）。
4. 其余（Hughes / Gasch / 过表达）按需扩展。
