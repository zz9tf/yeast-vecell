# VCWorld pipeline — 拆解

参考文献：**VCWorld: A Biological World Model for Virtual Cell Simulation**（ICLR 2026，
arXiv:2512.00306）。代码分析自克隆在`../VCWorld`的官方仓库。

本文档精确记录上游pipeline消费什么、做什么、产出什么，这样酵母移植版(`../PLAN.md`)可以换后端
而不用重新读一遍源码。

---

## 1. 核心思路

VCWorld**不是一个训练出来的模型**。它是一个**检索增强、prompt工程化的LLM**，针对每个
**(扰动, 基因, 上下文)三元组**，回答以下两个问题之一：

- **DE**（差异表达）：扰动药物`P`会不会改变细胞系`C`里基因`G`的表达？→`Yes/No`
- **DIR**（方向变化）：在DE命中的情况里，`G`是`Increase`还是`Decrease`？

整个pipeline存在的意义就是：(a)从单细胞数据里挖出真实标签，(b)检索出最相关的类比案例+生物学
描述作为证据，(c)强制LLM走一套固定的机制性推理脚手架，得到一个确定性的最终答案。

论文原图把它框成三个模块：
1. **排序检索** — 扰动通路、细胞过程、相似样本。
2. **LLM增强** — 描述、生物学背景、few-shot样例。
3. **基于规则的生成** — 固定角色("分子生物学家")、固定的5步"怎样&为什么"推理，一个最终答案。

---

## 2. 数据流

```
 .h5ad (Tahoe-100M，单个细胞系)
        │  prepare  (scanpy: normalize→log1p→rank_genes_groups，对比DMSO)
        ▼
 {cell}_DE.csv / {cell}_DIR.csv        列：pert, gene, label, split (train/test 30/70)
        │  retrieve  (+ 药物相似度JSON，基因相似度KG JSON)
        ▼
 retrieval.json     [{test_case:{drug,gene}, retrieved_pairs:[[drug,gene]...]}]
        │  prompt   (+ 药物描述JSON，基因描述JSON，带细胞系描述的DE/DIR模板)
        ▼
 prompts.txt        (代码块用"===="分隔)
        │  infer  /  infer-api  (本地HF模型 或 OpenAI兼容端点)
        ▼
 predictions.txt    (5步推理轨迹 + 最终的Yes/No或Increase/Decrease)
```

---

## 3. 逐阶段输入输出

### 阶段1 — `prepare` (`src/cli_pipeline/stages/prepare.py`)
- **输入**：单个细胞系的一个`.h5ad` AnnData文件。`obs[perturbation_col]`（默认`drug`）存放扰动，
  对照组=`DMSO_TF`。
- **处理**：
  1. `sc.pp.normalize_total(target_sum=1e4)` → `sc.pp.log1p`。
  2. `sc.tl.rank_genes_groups(groupby=drug, reference=DMSO_TF, method="wilcoxon",
     corr_method="benjamini-hochberg")` → 每个药物、每个基因得到`logfoldchanges, pvals, pvals_adj`。
  3. **切分**：打乱扰动顺序，前`train_fraction`(0.3)→train，其余→test。
  4. **DE标签**：`pvals_adj < fdr(0.05) & |logFC| > lfc(0.25)`则`label=1`；`label=0`从非显著基因中
     采样（`pvals > pval_neg(0.1)`），每个药物采`n_neg=200`个。
  5. **DIR标签**：在DE命中里，`logFC>0`则`label=1`否则`0`。
- **输出**：`{cell}_DE.csv`、`{cell}_DIR.csv`，列为`pert, gene, label, split`。

### 阶段2 — `retrieve` (`src/cli_pipeline/stages/retrieve.py`)
- **输入**：DE/DIR CSV + **药物相似度JSON** + **基因相似度JSON**。
  - `load_similarity_json`兼容性很强：接受`{key:[...]}`、`{key:[{"Drug":..}]}`，或带
    `direct_neighbors / two_hop_neighbors / neighbors / …`的KG字典。
- **处理**：
  - `build_seen_structures(train)` → `seen: drug→[genes]`，`seen_gene: gene→[drugs]`（只用train）。
  - 对每个唯一的test `(drug,gene)`：取相似度最高的`budget`个`close_drugs`、`close_genes`。
  - `get_drug_gene_pairs`按优先级从train里组装类比证据对：共享药物的对、共享基因的对、
    "两边都相似"的对，然后补齐——全部用带种子的RNG做预算上限控制。
- **输出**：`retrieval.json` = `{test_case:{drug,gene}, retrieved_pairs:[[drug,gene]…]}`的列表。
- ⚠️ **注意**：`retrieved_pairs`**不带标签**——见第6节。

### 阶段3 — `prompt` (`src/cli_pipeline/stages/prompt.py` + `support/{DE,DIR}_template.py`)
- **输入**：retrieval.json + **药物描述JSON** + **基因描述JSON** + 模板文件。
  - 模板是一个被`exec`执行的Python文件，用来取出`cell_lines`(`(short, description)`列表)、
    `prompt_vcworld_DE/DIR`（脚手架）、`choices_de/dir`。
- **处理**：每个case挑一个细胞系上下文（随机或`--cell-line-idx`指定）；从检索到的pair里构建
  "Examples"代码块（药物/基因+描述+一行`Result:`）；用`pert, gene, pert_desc, gene_desc,
  cell_short, cell_desc, obs`去`.format(...)`模板。
- **输出**：`prompts.txt`——每个case一个代码块，用80个`=`分隔；每个代码块含
  `[Start of Prompt]…[End of Prompt]`(system)和`[Start of Input]…[End of Output]`(user)。

### 阶段4 — `infer` / `infer-api` (`stages/infer.py`, `stages/infer_api.py`)
- **输入**：prompts.txt + 本地HF模型路径(`AutoModelForCausalLM`) **或** OpenAI兼容的
  `/chat/completions`端点(`--api-url`, `--api-model`，key通过flag/环境变量传入)。
- **处理**：正则解析每个代码块为`system`+`user`消息 → `apply_chat_template` → 采样
  (`temperature=0.6, top_p=0.9`，默认`max_new_tokens`)。本地路径走batch；API路径走循环。
- **输出**：`predictions.txt`——每个case，模型的5步推理+最终确定性的一行。

### 辅助 — `single` (`stages/single_case/prompt.py`)
对于数据集之外的`(pert, gene, cell)`：通过大小写不敏感+字母数字归一化匹配在JSON里解析相似药物/
基因，一个硬编码的基因别名表，以及查询在相似度JSON里找不到时的**LLM排序兜底**。从CSV里收集证据对，
生成单条prompt。和批量`prompt`不同，它在每个example里用的是**真实的**train标签。

---

## 4. 推理脚手架（模板）

`DE_template.py`和`DIR_template.py`都设置了：
- `cell_lines`：5个手写描述(C32, PANC-1, HepG2/C3A, HOP62, Hs766T)，带组织来源+标志性突变
  (KRAS, TP53, BRAF V600E, …)。prompt明确告诉LLM要用自己的内部知识去*补充*这些描述。
- 一套模型必须填写的固定**5步**分析：
  1. 机制与类比识别（共享的作用机制/通路节点）。
  2. 特异性与相关性（药物-基因-细胞三元组；考虑到突变情况，靶点是否相关）。
  3. 下游信号级联模拟。
  4. 因果桥接与证据综合（`Drug → Target → Pathway → TF → Gene`，引用类比案例）。
  5. 最终确定性预测（闭集里的一句原话）。
- DIR额外加了显式的**方向逻辑**："抑制一个*激活子*→下降；抑制一个*抑制子*→上升"（反之亦然）。

---

## 5. 知识资产与benchmark

外部文件（上游gitignore掉了，来自Google Drive + Zenodo）：
- `combined_similarity_sorted.json` — **药物相似度**（化学结构/作用机制上的邻居）。
- `results_close_gene.json` — **基因相似度** = 来自*开放世界知识图谱*的邻居（图中标注为
  Reactome/UniProt/STRING），暴露出`direct_neighbors`, `two_hop_neighbors`等字段。
- `drug_simp.json` — 药物文字描述（PubChem/DrugBank）。
- `gene_output.json` — 基因文字描述。

**Benchmark — GeneTAK**：从Tahoe-100M单细胞图谱衍生。5个细胞系、348个药物化合物，DE+DIR任务，
格式化为`(细胞系, 扰动, 基因)`三元组，按扰动切分train/test，比例**30/70**以模拟few-shot条件。

**依赖要求**：Python 3.10；`numpy, pandas, scanpy, anndata, scipy, scikit-learn, statsmodels`
（数据pipeline）+ `torch, transformers, accelerate`（本地推理）。

---

## 6. 移植时要带走的观察

1. **批量`prompt`里的few-shot样例标签是随机的。**`retrieved_pairs`丢掉了标签，所以
   `format_observations`给每一行`Result:`填的是`random.choice(choices)`。只有`single_case`用的
   是真实标签。酵母移植版应该把真实的train标签接入检索结果（保留一个`--shuffle-labels`开关做
   消融）。这很可能是单点质量杠杆里最大的一个。
2. **检索是一个手工调的启发式方法**(`get_drug_gene_pairs`)。作为baseline够用；酵母有更密、更高
   置信度的网络(STRING/BioGRID/SGA/YEASTRACT)，能支持真正的图感知、按置信度排序的检索。
3. **细胞系上下文是硬编码的散文**，不是数据。在酵母版里这变成了菌株/条件列表——编写成本低，而且
   "标志性突变"这个钩子正好对应到菌株背景/活跃通路。
4. **模板是被`exec`执行的Python**，所以能嵌入逻辑而不只是字符串——很适合把YEASTRACT的激活子/
   抑制子符号直接编码进DIR脚手架。
5. CLI里没有自带评测/指标脚本——打分（答案行→标签→Acc/F1/AUROC）留给用户自己做，移植版需要
   自己搭一套。
