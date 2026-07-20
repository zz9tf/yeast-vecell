# Yeast-VCWorld — 方案

面向 **酿酒酵母（Saccharomyces cerevisiae）** 的白盒"虚拟细胞"模拟器，移植 VCWorld
（ICLR 2026, arXiv:2512.00306）的思路：用**结构化生物知识 + LLM 因果推理**，以数据高效、可解释的方式
预测扰动下的转录组响应。

上游参考实现已克隆在 `../VCWorld`；pipeline 详细拆解见 [`docs/vcworld_pipeline.md`](docs/vcworld_pipeline.md)。

---

## Part A — VCWorld 到底在做什么（pipeline 拆解）

关键认知：VCWorld **不是训练出来的神经网络**，而是一个**检索增强 + 提示词工程的 LLM**。它逐条回答
**(扰动, 基因, 上下文)** 三元组的两个问题：

- **DE**（差异表达）：药物 `P` 扰动细胞系 `C`，会不会让基因 `G` 差异表达？ → `Yes / No`
- **DIR**（方向）：在 DE 命中里，`G` 是 `Increase / Decrease`？

预测单位是 **(扰动, 基因, 上下文) 三元组**。其余所有机制都是为了给 LLM 喂对证据、并强制它逐步做机制推理。

### 论文图里的 3 个概念块
1. **Sorted Retrieval（排序检索）** — 扰动通路、细胞过程、相似样本。
2. **LLM Augmentation（LLM 增强）** — 描述、生物学上下文、few-shot 例子。
3. **Rule-based Generation（规则化生成）** — 固定角色（"分子生物学家"）、固定 5 步推理脚手架
   （"how & why"）、唯一确定的最终答案。

### 5 个 CLI 阶段（具体 I/O）

| 阶段 | 代码 | 输入 | 处理 | 输出 |
|------|------|------|------|------|
| **1. prepare** | `stages/prepare.py` | `.h5ad` 单细胞（Tahoe-100M，单个细胞系；`obs['drug']`，对照 `DMSO_TF`） | `normalize_total(1e4)`+`log1p` → `sc.tl.rank_genes_groups`（Wilcoxon，每药 vs DMSO，BH-FDR）。DE 标签：`padj<0.05 & \|logFC\|>0.25` 记 1；标签 0 从 `pval>0.1` 里每药抽 200。DIR：DE 命中里 `logFC>0` 记 1。扰动按 30/70 切 train/test。 | `{cell}_DE.csv`、`{cell}_DIR.csv` → 列 `pert, gene, label, split` |
| **2. retrieve** | `stages/retrieve.py` | DE/DIR CSV + **药物相似度 JSON** + **基因相似度 JSON**（知识图谱邻居） | 从 **train** 建 `seen` 映射（药→基因、基因→药）。对每个测试 case，取 top-k 相似药 & 相似基因，再从 train 里捞出类比的 **(药,基因)** 对（共享药 / 共享基因 / 两者都相似）。有 budget 上限。 | `retrieval.json`：`[{test_case:{drug,gene}, retrieved_pairs:[[drug,gene]...]}]` |
| **3. prompt** | `stages/prompt.py` + `support/*_template.py` | retrieval.json + **药物描述 JSON** + **基因描述 JSON** + 模板（提示脚手架 + 手写的 `cell_lines` 描述） | 选一个细胞系上下文；把检索到的对拼成 "Examples"（描述 + 一个 Result 标签）；填入 5 步 DE/DIR 模板。 | `prompts.txt`（块间用 `====` 分隔） |
| **4a. infer** | `stages/infer.py` | prompts.txt + 本地 HF 模型（如 Llama-3.1-8B） | 把 `[Start of Prompt]…`/`[Start of Input]…` 解析成 system+user 消息 → chat template → `model.generate`。 | `predictions.txt`（推理链 + 最终 `Yes/No` 或 `Increase/Decrease`） |
| **4b. infer-api** | `stages/infer_api.py` | prompts.txt + OpenAI 兼容接口 | 同上，走 HTTP `/chat/completions`。 | `predictions.txt` |
| **(辅助) single** | `stages/single_case/prompt.py` | 单个数据集外的 `(pert,gene,cell)` | 解析相似药/基因（大小写无关 / 归一化 / 别名 / JSON 里缺失时用 **LLM 排序兜底**），从 CSV 收集证据对，产出单条 prompt。 | 单 case 的 `prompt.txt` |

### 知识资产（gitignore；来自 Google Drive + Zenodo）
- `combined_similarity_sorted.json` — **药物相似度**（化学 / MoA 邻居）。
- `results_close_gene.json` — **基因相似度** = 来自*开放世界知识图谱*的邻居（`direct_neighbors`、
  `two_hop_neighbors`…）；按论文图由 Reactome/UniProt/STRING 构建。
- `drug_simp.json` — 药物文本描述（PubChem/DrugBank）。
- `gene_output.json` — 基因文本描述。
- 细胞系描述是**硬编码在模板里**的（组织来源、招牌突变如 KRAS/TP53）。

### Benchmark
**GeneTAK**，源自 Tahoe-100M 图谱：5 个细胞系、348 个药物化合物，DE + DIR 两个任务，按扰动 30/70
切 train/test，以模拟 few-shot。

### 移植前值得注意的两点
1. **批量 `prompt` 阶段的 few-shot 例子标签是 `random.choice(choices)` 随机贴的** —— retrieved
   pairs 不带 label，所以每个例子的 "Result:" 行是*随机*的。只有 `single_case` 路径用了真标签。
   移植到 yeast 应该**把真标签一路带到检索里**，让 in-context 例子真正有信息量（或刻意保留一个
   "无标签类比" 的消融）。
2. **检索逻辑是拍脑袋的启发式**（`get_drug_gene_pairs`）。作为 baseline 没问题，但 yeast 的网络更
   密、置信度更高，可以做真正的图检索。

---

## Part B — VCWorld → Yeast 映射

核心 reframe：酵母是单细胞，所以**没有"细胞系"轴、通常也没有药**。数据最全、最自然的类比是
**基因扰动 → 转录组**。

| VCWorld（人） | Yeast-vecell | 备注 |
|---|---|---|
| 扰动 = **药物化合物** | 扰动 = **单基因敲除 / TF 诱导 / 过表达**（化学可选） | 遗传扰动是酵母覆盖最好的金标准数据 |
| 读出 = 人类基因 | 读出 = 酵母 ORF（~6000） | 系统名 `YFL039C` + 标准名 `ACT1` |
| 上下文 = **癌细胞系**（5 个）+ 招牌突变 | 上下文 = **菌株背景 + 培养基/胁迫条件**（如 BY4741 在 YPD；±胁迫） | 替换模板里的 `cell_lines` 列表 |
| DEG 标签 vs DMSO 对照 | DEG 标签 vs **WT / mock** | Wilcoxon/limma 逻辑相同 |
| 药物相似度（化学/MoA） | **扰动子相似度** = SGA 遗传互作 profile 相关性 和/或 敲除基因间 GO 功能相似 | Boone/Costanzo 的 SGA 是巨大资产 |
| 基因 KG（Reactome/STRING） | **酵母共功能 KG**：STRING、BioGRID、YeastNet、KEGG、GO | 比人类更密、质量更高 |
| 药物描述（PubChem） | **基因描述** = SGD 描述 + GO term（扰动子==被敲基因） | 一份描述同时服务两个角色 |
| 基因描述（UniProt） | SGD/UniProt-yeast 基因描述 | |
| —（隐含调控） | **YEASTRACT TF→靶基因调控网络** | DIR（方向）推理的**王牌**；酵母里近乎完备 |

### 推荐的扰动数据集（"Tahoe 替身"）
- **首选：Deleteome**（Kemmeren et al., Cell 2014）—— ~1484 个单基因敲除株 × ~6000 基因，表达 vs WT，
  自带 logFC + p 值。它几乎是 GeneTAK 的直接替身：已经能产出
  `(被敲基因, 被测基因, logFC, pval)` 三元组 → DE/DIR 标签。
- **备选 / 扩展**：
  - **IDEA**（Hackett et al. 2020）—— 200+ 个 TF 诱导时序（适合 DIR/动力学）。
  - **Hughes compendium**（2000）—— 300 个敲除/处理（更老，做交叉验证）。
  - **化学**：若想要药物轴，加一套化合物扰动数据 + PubChem 描述，即可完全保留 VCWorld 原框架
    （此时扰动子相似度又回到化学相似度）。
  - **你已有的酵母资产**（`yeast-rank-cross-lab` 里的 growth / het / 表达矩阵）可以作为额外的上下文轴
    或评测集 —— 接入前需先确认范围。

### Yeast 上的任务定义（**双任务**，详见 [`docs/supplementary_data_and_tasks.md`](docs/supplementary_data_and_tasks.md)）
- **Task 1 — 扰动→表达（旗舰，对标 VCWorld）**
  - **DE**：敲除/诱导 `P` 会不会让 ORF `G`（在条件 `C` 下）差异表达？ `Yes/No`
  - **DIR**：DE 命中里 `Increase/Decrease`。数据：Deleteome（首发）→ IDEA/Hughes。
- **Task 2 — 扰动→生长表型（并行新增，同一套 DE/DIR 式框架）**
  - **框架 A**（首选）：敲除 `P` 在条件 `C` 下有没有生长表型？更敏感/更抗？
    数据：Hillenmeyer 2008 chemical-genomics + **用户自有 het/growth 矩阵**（待确认内容）。
  - **框架 B**（补充任务）：双敲 `A`+`B` 有没有遗传互作？负/正？数据：Costanzo 2016 SGA。
- 两任务都按扰动子 30/70 切 train/test，保留 few-shot、数据高效前提。

---

## Part C — 实施阶段

沿用 VCWorld 的阶段布局（`src/cli_pipeline/stages/`），保持 CLI 熟悉；只替换底层数据/知识后端。

**Phase 0 — 脚手架 & 数据获取**
- 克隆 VCWorld 的 CLI 结构；保留 `cli.py` 的子命令（`prepare/retrieve/prompt/infer`）。
- 下载 Deleteome 矩阵 + p 值 → `data/perturbation/`。
- 拉取知识：SGD 基因描述 + GO、STRING/BioGRID/YeastNet 边、YEASTRACT TF→靶、Costanzo SGA profile
  → `data/knowledge/`。

**Phase 1 — `prepare`（打标签）**
- 若从 Deleteome 已算好的 logFC/p 值起步：跳过 `rank_genes_groups`，直接套同样阈值
  （`padj<0.05 & |logFC|>thr` → DE=1；每扰动子抽非 DE 负样本）。
- 若从原始 counts 起步：保留 scanpy 路径（normalize→log1p→Wilcoxon vs WT）。
- 产出 `{condition}_DE.csv`、`{condition}_DIR.csv`，列 `pert, gene, label, split`。

**Phase 2 — 知识构建器（真正的工作量）**
- `build_gene_sim.py` → `results_close_gene.json`：对每个 ORF，从 STRING/BioGRID/YeastNet
  （+ GO 语义相似）取排序后的共功能邻居，带 `direct_neighbors` / `two_hop`。
- `build_pert_sim.py` → `perturbagen_similarity.json`：对每个被敲基因，用 SGA 遗传互作 profile 相关性
  和/或 GO/功能相似取相似扰动子。
- `build_descriptions.py` → `gene_desc.json`（SGD "Description" + GO BP/MF/CC + 别名），复用为扰动子描述。
- `build_regulatory.py` → `tf_targets.json`（来自 YEASTRACT，用于让 DIR 推理机制化）。
- 编写 `support/DE_template.py` / `DIR_template.py`：把 `cell_lines` 换成**条件**列表（菌株 + 培养基 +
  活跃通路备注）；把 5 步脚手架改写成酵母术语（敲除 → 上位/通路 → TF（YEASTRACT）→ 靶 ORF → 方向）。

**Phase 3 — `retrieve`（在 baseline 启发式上改进）**
- 保留 VCWorld 的 `seen`/budget 逻辑作 baseline。
- 加图检索：优先选扰动子是 SGA/通路邻居 **且** 读出基因是网络邻居的类比对，按综合边置信度排序。
- **修掉随机标签问题**：把真 train 标签带进 `retrieved_pairs`，让 few-shot 的 "Result:" 行是真证据。
  保留 `--shuffle-labels` 开关做消融。

**Phase 4 — `prompt` + `infer`**
- `prompt.py`/`infer.py`/`infer_api.py` 几乎原样复用（模板 + JSON 换成 yeast 后它们与数据无关）。
- 推理用对齐 VCWorld 的那套模型（Qwen2.5-7B/14B、Qwen3-4B、Llama3.1-8B、Gemini-2.5-Flash）
  —— 具体清单/路径/参数见 **Part C.5**。

**Phase 5 — 评测 & baseline**
- 解析器：最终行 → 标签；算 Accuracy / F1 / AUROC（DE）、方向准确率（DIR），按扰动子和按条件拆分。
- 要打败的 baseline：(a) 多数类，(b) "网络邻居 → DE" 启发式，(c) **不带检索**的 LLM（消融证据），
  (d) 简单监督模型（网络特征上的逻辑回归）。
- 可解释性检查（VCWorld 的核心卖点）：LLM 引用的 TF→靶桥接是否匹配 YEASTRACT ground truth？报告机制一致率。

**Phase 6 — 扩展（可选）**
- 把条件/胁迫做成真正的第二个轴（环境基因表达 compendium）。
- 从二分类 DE 走向幅度/回归；从静态走向时序（IDEA）。

---

## Part C.5 — 模型与推理配置（对齐 VCWorld，pipeline 搭好即可直接跑分）

直接复用 VCWorld 论文用的那套 backbone 模型，好处是 yeast 的分数能和论文横向对比。我们的 CLI 已经内置
`infer`（本地 HF）和 `infer-api`（OpenAI 兼容 / OpenRouter）两条路，**不用改代码**，把 `--model` /
`--api-model` 指到下面这些就行。

| Backbone | HF 路径 / 接入方式 | 参数量 | 角色 | 论文实测(C32 acc) |
|---|---|---|---|---|
| **Llama-3.1-8B-Instruct** | `meta-llama/Llama-3.1-8B-Instruct`（`infer`） | 8B | 规模下限参照 | 0.37 |
| **Qwen3-4B-Instruct-2507** | `Qwen/Qwen3-4B-Instruct-2507`（`infer`） | 4B | 轻量 | — |
| **Qwen2.5-7B-Instruct** | `Qwen/Qwen2.5-7B-Instruct`（`infer`） | 7.6B | 主力开源 | — |
| **Qwen2.5-14B-Instruct** | `Qwen/Qwen2.5-14B-Instruct`（`infer`） | 14B | **最强开源** | 0.65 |
| ~~Gemini-2.5-Flash~~ | ~~OpenRouter `infer-api`~~ | API | **本项目暂不用（无 API key，只跑本地）** | 0.70（论文参考） |

**推理参数**（论文 B.4，与 CLI 默认一致，无需额外传）：`temperature=0.6`、`top_p=0.9`；输入 prompt
统一约 **2600 tokens**。

**论文关键结论**：性能随模型推理能力单调上升 —— Llama3-8B (0.37) → Qwen2.5-14B (0.65) →
Gemini-2.5-Flash (0.70)；作者据此断言"这个任务吃的是推理能力，不是模式匹配"。
→ **对我们的启示（本地版）**：优先跑 **Qwen2.5-14B**（本地开源天花板）；Qwen2.5-7B / Qwen3-4B /
Llama3.1-8B 作为**规模消融**（验证 yeast 上是否复现"越强越准"趋势）。Gemini 的 0.70 仅作论文对照，
将来拿到 key 再补 `infer-api`。

**怎么跑（pipeline 搭好后，全本地）**：
```bash
# 默认 temp/top_p 已对齐论文
python cli.py de infer --model Qwen/Qwen2.5-14B-Instruct \
  --prompts out/cond_DE_prompts.txt --out out/cond_DE_pred_qwen14b.txt
# 规模消融：把 --model 换成 Qwen2.5-7B-Instruct / Qwen3-4B-Instruct-2507 / Llama-3.1-8B-Instruct
```
**显存**：14B bf16 约需 ≥28GB（单卡 A100 40/80G 可跑，或多卡 `--device-map auto`）；4B/7B 单卡消费级即可。

> 注：论文里的 CPA / scVI / STATE / scGPT 等是**专用深度学习 baseline**（非 VCWorld 的 backbone），
> 属于 Phase 5 的对照方法，先不纳入初始跑分。

---

## Part D — 关键设计取舍 & 坑

- **为什么 yeast 很合适**：模式生物 → LLM 已有强先验；网络（YEASTRACT、SGA、STRING）又密又高置信 →
  白盒推理比在人类里更有根基。Deleteome 便宜地给出成千上万条干净的 扰动→转录组 三元组。
- **标识符卫生**：统一用系统 ORF 名；维护别名映射（标准名 ↔ 系统名 ↔ SGD ID）。VCWorld 本就需要基因别名表
  —— yeast 需要一张更大的。
- **DIR（方向）是知识发力的地方**：把 YEASTRACT 的激活/抑制符号编码进去，让模板的
  "抑制一个激活子 → Decrease" 逻辑可核查，而不是拍脑袋。
- **检索里带真标签**（见 Part A 第 1 点）—— 很可能是最大的单点质量杠杆。
- **泄漏**：按扰动子切（不是按对切）；确保检索只读 **train** split。
- **评测要诚实**：始终把不带检索、多数类这两个 baseline 一并报告。

---

## 决策记录（2026-07-19）

1. **扰动类型** ✅ **先做遗传**（敲除 / TF 诱导），化学轴以后再说。
2. **上下文轴** ✅ **先按多条件设计**（多数据集/多扰动类型当上下文），之后再补单条件专项跑。
3. **数据源** ✅ **尽量都用上**（Deleteome + IDEA + Hughes + 你的矩阵），多跑分数再决定取舍。
   数据源的具体用法见 [`docs/data_sources.md`](docs/data_sources.md)，跨源细节 chat 里继续定。
4. **推理** ✅ **只用本地模型**（Qwen2.5-14B 主力，7B/4B/Llama3.1-8B 做规模消融；无 API/Gemini）。

5. **双任务** ✅ 除"扰动→表达"外，**并行做"扰动→生长表型"**；并调研补充数据/任务
   （见 [`docs/supplementary_data_and_tasks.md`](docs/supplementary_data_and_tasks.md)）。

**跨源用法已基本定**（`docs/data_sources.md`：①多数据集当上下文 ②各源原生阈值—先 Deleteome 单阈值
③Deleteome 先出分 ④按扰动子跨源 hold out）。**唯一待你确认 = het/growth 矩阵的行/列/量纲**，
定了就能接 Task 2-A。

---

## 仓库结构（本项目）
```
yeast-vecell/
├── PLAN.md                     # 本文件
├── README.md
├── src/cli_pipeline/
│   ├── cli.py                  # de/dir prepare|retrieve|prompt|infer （移植）
│   └── stages/                 # prepare, retrieve, prompt, infer, infer_api, single_case
├── support/                    # DE_template.py, DIR_template.py（酵母条件 + 5 步脚手架）
├── data/
│   ├── perturbation/           # Deleteome / IDEA 矩阵 → DE/DIR CSV
│   └── knowledge/              # gene_desc, gene_sim (STRING/BioGRID), pert_sim (SGA), tf_targets (YEASTRACT)
└── docs/                       # 数据集说明、KG 构建说明、评测报告
```
