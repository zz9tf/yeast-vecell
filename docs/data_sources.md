# 遗传扰动数据源 — 分析与使用方案

决策上下文（已定）：**先做遗传扰动**（敲除 / TF 诱导）；**尽量把数据源都用上**，多跑分数再决定取舍；
**只用本地模型推理**（无 API）。

本文档 = 每个源"是什么"的事实分析 + 跨源"怎么用"的方案（后半部分标了「待讨论」，见 chat）。
每个源按 [`data-source-profile`](/home/zhengz2/skills/data-source-profile/SKILL.md) skill 的
4-section 骨架写：Section 1 论文与基本说明 / Section 2 实验设计 / Section 3 文件格式 / Section 4 分析。

---

## 源 1 — Deleteome（主力，Tahoe 替身）

### Section 1 — 论文与基本说明
- **论文**：Kemmeren et al., *Cell* 2014, "Large-Scale Genetic Perturbations Reveal Regulatory
  Networks and an Abundance of Gene-Specific Repressors."（DOI/PubMed 见本节末尾参考链接）。
- **✅ 已下载**：数据门户见本节末尾参考链接（下载页 `downloads.php`）；DeleteomeTools（R 包，
  相似度分析用得上）见参考链接。

### Section 2 — 实验设计
- **~1484 个单基因敲除株**，每株用双通道微阵列测全基因组表达，**每株 vs 野生型（WT）对照**，带
  dye-swap 重复。读出 ~6000 个 ORF。
- 扰动类型 = **功能缺失（deletion / loss-of-function）**；稳态（对数期，SC 培养基）。**基本是单一条件**。

### Section 3 — 文件格式（tab 分隔，逐文件）

- **`deleteome_all_mutants_ex_wt_var_controls.txt`**（主用文件）
  - **结构形式**：~1484行基因 × (1484敲除株×3)列，宽表；行=基因（`reporterId`+系统ORF名+标准
    symbol三列标识），列=每个敲除株占3列。
  - **值的意义**：`M`=log2(mutant/WT)即logFC、`A`=平均信号强度、`p`=p值；已去掉WT-variable基因，
    无额外归一化。
  - **缺失情况**：无缺失/填充问题——每个格子都有完整的M/A/p三元组。
  - **文件意义**：**推荐使用的主文件**，比全量版更干净（剔除了WT本身就波动大的基因）。
- **`deleteome_all_mutants_controls.txt`**
  - **结构形式/值的意义**：同上，唯一区别是**含WT-variable基因**（未剔除）。
  - **缺失情况**：同上，无缺失。
  - **文件意义**：全量版，不推荐作为默认输入，仅在需要WT-variable基因时使用。
- **`deleteome_responsive_mutants_(ex_wt_var_)controls.txt`**
  - **结构形式**：行数少于主文件，只保留"responsive"株（列数相应减少）。
  - **值的意义**：同主文件（M/A/p），筛选阈值为FC>1.7 & p<0.05（≥4个显著变化的株才保留）。
  - **缺失情况**：无。
  - **文件意义**：一个预筛选子集，用于只关心强响应株的分析。
- **`deleteome_all_mutants_svd_transformed.txt`**
  - **结构形式**：行列同主文件，但**只有M值**（无A/p列）。
  - **值的意义**：M值经过SVD变换，扣掉了"慢生长特征"这个主成分。
  - **缺失情况**：无。
  - **文件意义**：定义更"特异"（非慢生长混杂）DEG时的参考版本，配合主文件使用而非替代。
- 附带3组内部对照比较（matA vs matα、YPD vs SC、二倍体 vs 单倍体），结构与上述文件同型，
  用途是背景对照而非主分析输入。

### Section 4 — 分析（在我们项目中的应用）
每个 `(敲除基因 P, 读出基因 G)` 格子已有 `M` + `p`，所以我们的 `prepare` **不用跑 scanpy
`rank_genes_groups`**，只做阈值：
- **DE**：`p<0.05 & |M|>阈值` → label=1（Deleteome 原生用 FC>1.7，即 `|M|>~0.77`）；label=0 从明显不显著里抽。
- **DIR**：`sign(M)`（M>0 升高，M<0 降低）。
- **扰动子 P** = 被敲的基因；**读出 G** = 微阵列上的基因。同一个基因可在一处当 P、另一处当 G。
- ⚠️ **慢生长混杂**：很多敲除会拖慢生长，产生一大片非特异的"环境应激/生长"表达变化。建议用
  `ex_wt_var` 版，必要时参考 `svd_transformed`（已扣掉慢生长信号）来定义更"特异"的 DEG。

### 参考链接
- 论文 DOI：`10.1016/j.cell.2014.02.054`；PubMed：`24766815`。
- 数据门户：http://deleteome.holstegelab.nl （下载页 `downloads.php`）。
- DeleteomeTools（R 包，相似度分析）：https://github.com/AitchisonLab/DeleteomeTools

---

## 源 2 — IDEA（Induction Dynamics Expression Atlas，Hackett 2020, Calico）

### Section 1 — 论文与基本说明
- **论文**：Hackett et al., *Mol. Syst. Biol.* 2020, "Learning causal networks using inducible
  transcription factors and transcriptome-wide time series."（EMBO Press；DOI见参考链接）。
  门户见参考链接。
- **✅ 已下载**：门户本身不提供处理好的汇总表下载，GEO `GSE142864` 只有原始芯片 RAW 数据；真正
  可用的是论文的 **Expanded View 补充材料**，已下载到 `data/perturbation/idea/`（具体文件清单+
  各自内容见 Section 3）。

### Section 2 — 实验设计
- **203 个 TF 诱导株**（Table EV1：216个菌株 = 203个TF诱导株 + 10个"Prediction"验证株 + 3个对照），
  用 **β-estradiol 诱导过表达**（ZEV系统）单独诱导，**chemostat 稳态培养**（磷限制为主，列名里也有
  N/M等其他限制条件），诱导后取 **8 个时间点**（0/5/10/15/20/30/45/90分钟）。
- 技术是**双通道微阵列**（Agilent 2-color，GEO明确标注，Dataset EV2直接给出`green_median`/
  `red_median`双通道原始强度）——**和 Deleteome/Hughes 同为微阵列技术，不是RNA-seq**。
- 扰动类型 = **功能获得（induction / gain-of-function）**，带**动态时序**（Deleteome/Hughes是单一
  稳态终点，IDEA是诱导后0~90分钟的8个采样点）。

### Section 3 — 文件格式（逐文件）

- **Table EV1**（63KB）
  - **结构形式**：短表，216行菌株清单。
  - **值的意义**：菌株角色分类——203个TF诱导株 + 10个"Prediction"验证株 + 3个对照。
  - **缺失情况**：无。
  - **文件意义**：菌株身份元数据，用于确认Dataset EV1里哪些列属于哪个TF/角色。
- **Table EV2**（162KB）
  - **结构形式**：短表，715行motif分析结果。
  - **值的意义**：motif富集/分析统计量（非表达数值）。
  - **缺失情况**：无。
  - **文件意义**：辅助分析产物，不直接参与DE/DIR标签产出。
- **Table EV3**（34KB）
  - **结构形式**：10个验证TF各自的2×2混淆矩阵。
  - **值的意义**：模型预测 vs 实测的 activator/no-change 分类计数。
  - **缺失情况**：只覆盖10个验证TF，不是全部203个。
  - **文件意义**：**不是逐基因的靶基因判定汇总表**——没有现成的"直接靶vs间接靶"判定表可以直接
    拿来当标签用，只是模型验证结果的汇总统计。
- **Dataset EV1**（核心大表，37.9MB）
  - **结构形式**：6175行 × 1694列，宽表。**行 = 基因**，用**标准基因符号**标识（如`AAC1`，不是
    系统ORF名，接入前需要自建 symbol↔ORF 映射）。**列 = 每次采样**，列名格式为
    `TF_菌株_日期_限制条件_诱导机制_时间点`（如`ACA1_SMY2049_02/29/2016_P_ZEV_90.0`）。
  - **值的意义**：相对t0的log2表达比值，t0列全部为0。
  - **缺失情况**：非显著响应被清零成0（稀疏矩阵——论文原文说"2千万个观测里只有10万个有信号"），
    清零的0和"真实无变化"无法区分，用作负例时要注意。
  - **文件意义**：核心时序表达矩阵，DE/DIR标签需从这里自己按峰值算。
- **Dataset EV2**（验证表，长表，36.7MB）
  - **结构形式**：49.4万行长表，列 = `TF, restriction, mechanism, time, GeneName, green_median,
    red_median, log2_ratio, log2_cleaned_ratio`。
  - **值的意义**：`green_median`/`red_median`是双通道微阵列原始强度，`log2_ratio`/
    `log2_cleaned_ratio`是处理后的比值。
  - **缺失情况**：只覆盖10个候选调控子（ANB1/ARN2/FMP48/HMX1/PHM6/PHO11/PHO5/STP4/YGL117W/
    YGR066C），不是全部203个TF。
  - **文件意义**：小规模验证集，用于核对Dataset EV1的处理流程是否可信，不能当主标签来源。
- **方法学附录**（PDF，33MB）
  - **结构形式**：非结构化文档。
  - **值的意义**：不适用。
  - **缺失情况**：不适用。
  - **文件意义**：直接靶/间接靶判定模型的方法说明，若要复现论文的判定逻辑需要参考这份文档。

### Section 4 — 分析（在我们项目中的应用）
- **DE**：从 Dataset EV1 里，对每个`(TF, 读出基因G)`取相对t0的**峰值 |log2FC|**（时序里绝对值最大
  的时间点）→ 阈值化（因为非显著已清零为0，可以先看非零比例定阈值，不能直接套Deleteome的数值）。
- **DIR**：取峰值时间点的 `sign(log2FC)`。
- **没有现成判定表可以抄近道**——直接靶/间接靶的判定逻辑要么从Dataset EV1时序自己算（比较不同
  时间点的响应先后），要么参考PDF方法学附录里的模型说明重新实现。
- **扰动子 P** = 被诱导的 TF（只能是这203个TF之一）；**读出 G** = 任意被测基因，用标准基因符号。
  **不对称于 Deleteome**（Deleteome里扰动子和读出基因可以互换角色，IDEA里扰动子只能是TF）。
- **价值**：和 Deleteome/Hughes **方向互补**（诱导=功能获得 vs 敲除=功能缺失）；因为扰动子限定是
  TF，**TF→靶的ground truth信噪比比敲除类数据高**→对**DIR方向推理**和**可解释性核查（比对
  YEASTRACT的已知调控符号）**特别有用；8个时间点的动态信息也是敲除类静态终点数据没有的。
- **局限**：只有TF能当扰动子；核心矩阵是稀疏的；行ID是symbol不是ORF，接入前要先解决ID映射。

### 参考链接
- 论文 DOI：`10.15252/msb.20199174`（EMBO Press, *Mol. Syst. Biol.* 2020）。
- 数据门户：http://idea.research.calicolabs.com
- GEO（仅原始芯片 RAW 数据）：`GSE142864`
- Expanded View 补充材料直链（Springer静态内容服务器）：
  - Table EV1：https://static-content.springer.com/esm/art%3A10.15252%2Fmsb.20199174/MediaObjects/44320_2020_BFMSB199174_MOESM2_ESM.xls
  - Table EV2：https://static-content.springer.com/esm/art%3A10.15252%2Fmsb.20199174/MediaObjects/44320_2020_BFMSB199174_MOESM3_ESM.xls
  - Table EV3：https://static-content.springer.com/esm/art%3A10.15252%2Fmsb.20199174/MediaObjects/44320_2020_BFMSB199174_MOESM4_ESM.xls
  - Dataset EV1（主表达矩阵）：https://static-content.springer.com/esm/art%3A10.15252%2Fmsb.20199174/MediaObjects/44320_2020_BFMSB199174_MOESM5_ESM.xlsx
  - Dataset EV2（验证实验表）：https://static-content.springer.com/esm/art%3A10.15252%2Fmsb.20199174/MediaObjects/44320_2020_BFMSB199174_MOESM6_ESM.xlsx
  - 方法学附录（PDF）：https://static-content.springer.com/esm/art%3A10.15252%2Fmsb.20199174/MediaObjects/44320_2020_BFMSB199174_MOESM1_ESM.pdf
- 本地落地路径：`data/perturbation/idea/`

---

## 源 3 — Hughes compendium（Rosetta, 2000）

### Section 1 — 论文与基本说明
- **论文**：Hughes et al., *Cell* 2000, "Functional Discovery via a Compendium of Expression
  Profiles."（这是 Deleteome 之前的老一代同类工作，Deleteome 可看作它的规模化升级版）。
- **✅ 已下载**：Rosetta Inpharmatics 官方页面已失效，数据由 University of Washington Noble Lab
  存档保留（目录页链接见参考链接，可直接点开核实）。已下载到 `data/perturbation/hughes/`（具体
  文件清单+各自内容见 Section 3）。

  **数据版权属 Rosetta Inpharmatics，引用/使用需遵守其声明的许可条款**。

### Section 2 — 实验设计
- **300 个扰动实验**（`experiment_list.txt`确认），分三类，**不是"敲除 vs 化学处理"二分**：
  1. **#1–277**：单/双倍体敲除株（对应`experiment strain`/`control strain`列）。
  2. **#278–287**：**tet 启动子可滴定敲减**（titratable knockdown，既非常规完全敲除也非化学
     处理，是第三类，实验设计要单独标记）。
  3. **#288–300**（13个）：化学/环境处理（如 MMS、HU、cycloheximide、tunicamycin 等）。
- 技术是**双通道微阵列**（和 Deleteome 同一类技术，但更早、覆盖探针更少、批次效应更大）：
  每个扰动样本 vs 一个参考池，测比值。

### Section 3 — 文件格式（逐文件）

- **`experiment_list.txt`**（303行元数据，18KB）
  - **结构形式**：长表，303行，每行一个扰动实验；字段含strain/control strain/collection/
    phenotype/conditionset等（tab分隔，有表头）。
  - **值的意义**：多为文本型元数据（菌株编号、条件描述），不是数值矩阵。
  - **缺失情况**：无系统性缺失。
  - **文件意义**：`data_expts*.xls`里300个实验列的说明书，也是区分"敲除株/tet敲减/化学处理"三类
    扰动的唯一依据。
- **`data_expts1-75.xls` / `76-150.xls` / `151-225.xls` / `226-300.xls`**（4个分卷，各约21MB）
  - **结构形式**：6328行（探针/基因）× 227列，宽表；第1列ID多为系统ORF名（如`YAL019W`），第2列
    是标准基因名/别名（常为空）；每个扰动实验占3列，四份合计`(227-2)/3=75`列×实验数=300个实验列，
    与`experiment_list.txt`的300行对上。
  - **值的意义**：`log10(Intensity)`（平均信号强度）、`Log10(ratio)`（处理/参考比值，**底数是
    log10不是log2**，和Deleteome换算/联合使用时要注意）、`P-value`（标准p值，区分
    "gene-specific error model"和"measurement-error-only"两种来源，**未提及多重检验校正**，
    需要自己决定是否校正）。
  - **缺失情况**：无系统性缺失，但基因ID列里少数是`NORFxx`（当时未知/无同源物的unclustered ORF）。
    readme提到还有更完整版本（`data_expts1-300_geneerr`/`_meas`/`_ratios`，含spot强度/ratio误差
    等），但该下载目录里**没有挂出这些大文件**，只有这份精简版（intensity+ratio+P值）可下载到。
  - **文件意义**：核心数据矩阵，按实验编号分卷存储，DE/DIR标签从这里阈值化产出。
- **`readme.doc`**（原作者字段说明）
  - **结构形式**：非结构化文档（Word）。
  - **值的意义**：不适用。
  - **缺失情况**：不适用。
  - **文件意义**：解释以上文件每个字段的含义，是核对列名/统计量口径的权威来源。
- 特殊处理（跨文件）：扰动类别可以**分三类标记**（不是简单的敲除/化学处理二分）：
  `experiment_list.txt`里的`experiment strain`/`control strain`/实验名文本能区分三类
  （tet-promoter和化学处理的实验名里带剂量/药名，容易正则识别）。引入前按这三类打标签，
  tet-titratable那10个要么单列一类要么先排除。

### Section 4 — 分析（在我们项目中的应用）
- **独立的跨实验室泛化测试集 / 交叉验证**：和 Deleteome 在不同实验室、不同批次、更早的技术条件下
  测的，可以检验模型/检索在 Deleteome 上学到的模式能不能跨数据集泛化。
- 阈值化逻辑同源1（`|ratio|`超阈值+P值达标→DE=1；符号→DIR），但注意底数是log10不是log2、且
  技术更老噪声更大，阈值需要单独定，不能直接照搬 Deleteome 的 `|M|>0.77`（那是log2下的数值）。

### 参考链接
- 论文：Hughes et al., *Cell* 2000, "Functional Discovery via a Compendium of Expression Profiles."
- 存档目录页（University of Washington Noble Lab）：https://noble.gs.washington.edu/proj/microarray/Rosetta/
- 下载文件直链：
  - 实验1–75的表达/比值/P值数据：https://noble.gs.washington.edu/proj/microarray/Rosetta/data_expts1-75.xls
  - 实验76–150的表达/比值/P值数据：https://noble.gs.washington.edu/proj/microarray/Rosetta/data_expts76-150.xls
  - 实验151–225的表达/比值/P值数据：https://noble.gs.washington.edu/proj/microarray/Rosetta/data_expts151-225.xls
  - 实验226–300的表达/比值/P值数据：https://noble.gs.washington.edu/proj/microarray/Rosetta/data_expts226-300.xls
  - 303行实验元数据表：https://noble.gs.washington.edu/proj/microarray/Rosetta/experiment_list.txt
  - 原作者字段说明文档：https://noble.gs.washington.edu/proj/microarray/Rosetta/readme.doc
- 本地落地路径：`data/perturbation/hughes/`

---

## 源 4 — `yeast-rank-cross-lab` 的 Yeast Phenome 矩阵（⚠️ 不是转录组，是生长表型）

### Section 1 — 论文与基本说明
- **论文**：Kritikos & Typas et al., *Science Advances* 2023, "Global analysis of the yeast
  knockout phenome"（`Yeast Virtual Cell Model.docx` 里"8) phenome data after single-gene
  knockout"引用的正是这篇，DOI见参考链接）。
- **数据门户**：见参考链接 —— 一个**聚合库**，把所有已发表的、基于酵母敲除文库（YKO collection）
  做的表型筛选实验汇总成统一矩阵，号称汇总了 **~4300 万条"基因→表型"因果关系**，是同类数据里
  覆盖面最大的。
- **✅ 已下载**：这份数据不在本仓库（`yeast-vecell`）里，实际落在姊妹项目 `yeast-rank-cross-lab`
  的原始下载目录+项目内加工后的特征矩阵目录（具体文件清单+各自内容见 Section 3，路径见参考链接）。
  经 `md5sum` 实测核对（2026-07-22），姊妹项目内的文件与 `MiniShare` 共享盘上的同名文件 md5 均为
  `c90f69952709d42096ea2940a93048ab`（两处路径见参考链接）——确认这就是"Yeast Virtual Cell
  Model"项目里"Folder 8（phenome）"数据集，两个项目复用的是同一份下载。

### Section 2 — 实验设计
- **扰动仍是单基因敲除**（覆盖 ~4554–5640 个基因，因 collection 不同而略有差异），但**读出不是表达量，
  是"生长快慢"这一个标量表型**：把敲除株铺在某种条件下（药物/温度/培养基/营养限制等），测它比参照
  长得快还是慢，汇总成一个 Z 分数。
- **不是单一条件**：反而是这个源里"条件"维度最大——每一列就是一个独立发表过的"筛选实验"（screen），
  一共 **14,484 个（haphom）+ 7,011 个（het）**，覆盖各种药物浓度、培养基、胁迫条件，是全部四个源里
  唯一天然自带"大量条件"维度的数据。
- **两套平行 collection，覆盖互补**：
  - **haphom**（haploid + homozygous diploid deletion，非必需基因）：`yp_screens_haphom_20221025.txt`
    的 `collection` 列实测分布为 `hom`(7119) / `hap alpha`(6236) / `hap a`(1048) / `hap a (post-SGA)`(58)
    / 混合类型(hap a/hap alpha 等，共22) / `hap ?`(13)，合计 14,484 个 screen。
  - **het**（heterozygous diploid deletion）：全部 7,011 个 screen 的 `collection` 列都是 `het`。
    **为什么单独一套**：必需基因纯合敲除会致死，测不了 haphom，只能测**杂合缺失（单倍剂量不足，
    haploinsufficiency）**下生长是否受影响，所以 het 是**覆盖必需基因**的唯一途径，和 haphom 是
    "非必需基因 vs 必需基因"互补关系，不是同一批基因的重复测量。
  - **✅ 已实测核实基因覆盖关系**（直接对比两个矩阵行名/基因ID集合）：haphom 的 4,554 个基因
    **全部**是 het 5,639 个基因的子集（haphom-独有基因数 = 0）；het 比 haphom **多出 1,085 个
    基因**，这 1,085 个是只能在 het（杂合缺失）里测到、无法进 haphom（纯合/单倍体敲除会致死）的
    基因——**这批 1,085 个"het-独有"基因就是本数据集里唯一能直接圈出来的必需基因候选集合**。
    换句话说：**haphom（生长表型主矩阵）本身只覆盖非必需基因，不含任何必需基因**——这一点原先
    是设计层面的推断，现在已经用真实基因ID列表核实过，不是靠命名/描述推断的。

### Section 3 — 文件格式（逐文件说明，均 tab 分隔）

**原始下载**（姊妹项目 `data/folder8_raw/`，路径见参考链接）：

- **`yp_screens_haphom_20221025.txt`**（screen 元数据表，14,484 行）
  - **结构形式**：长表，14,484行，每行一个已发表的表型筛选实验（screen）。
  - **值的意义**：`id`（screen唯一编号，即下面矩阵的列名）、`name`（可读全名）、`collection`
    （用的敲除文库类型）、`phenotype`（测的是什么，如`growth (streaks on agar)`、
    `growth (pooled culture)`）、`conditionset`（具体条件，如`rapamycin [25 nM]`）、`medium`
    （培养基，如YPD/SC-Ura）、`paper`/`pmid`（出处）、`latest_tested_status`（该screen实际测试
    的菌株列表能不能拿到：`loaded`/`not available`/`request abandoned`）、`num_tested`（论文
    报告的测试菌株数）。
  - **缺失情况**：无系统性缺失，是元数据说明书本身。
  - **文件意义**：不是数值矩阵本身，是下面`yp_matrix_*`矩阵**列id的说明书**——建模时按
    `phenotype`/`conditionset`这两列可以把14,484列重新归类成"药物筛选/营养筛选/温度筛选"等
    更粗的条件簇。
- **`yp_matrix_haphom_20221025.txt`**（原始未归一化表型矩阵）
  - **结构形式**：4,555行（含表头）× 14,485列（含基因名列），与README描述的4,554基因×14,484
    screen对上。行=基因（系统ORF名，如`YAL002W`），列=screen id（对应元数据表的`id`列，表头即
    id数字，不带前缀）。
  - **值的意义**：清洗但未归一化的表型分数（原始量纲随原论文而异）。清洗包括：修正基因名/ORF
    拼写错误、旧ORF名转当前名、剔除dubious/merged/blocked ORF、同一ORF重复值取平均。
  - **缺失情况**：需下载核实具体每列的缺失率（不同screen覆盖的菌株数不同）。
  - **文件意义**：未归一化的原始版本，建模时优先用下面的Z分数版而非这份。
- **`yp_matrix_z_haphom_20221025.txt`**（推荐用这份）
  - **结构形式**：行/列同上（4,554基因 × 14,484 screen）。
  - **值的意义**：归一化后的Z分数——对每一列做**相对众数（mode，不是均值）的列内Z变换**，因为
    很多筛选里大多数基因是"正常"的，少数是极端表型，用众数当基线比均值更抗离群值干扰。
  - **缺失情况**：同上一份（对齐后的缺失率见下方`het_profile_matrix.pkl`条目的说明，haphom本身
    覆盖相对完整）。
  - **文件意义**：**四个源里质量控制最好、直接可用的一份**，建模优先用这份而不是未归一化版。
- **`yp_het/yp_screens_het_20221018.txt`**（het collection 的 screen 元数据，7,011 行）
  - **结构形式**：长表，字段与`yp_screens_haphom`完全一致
    （id/name/collection/phenotype/conditionset/medium/paper/pmid/...）。
  - **值的意义**：同haphom元数据表，`collection`列固定为`het`。
  - **缺失情况**：无系统性缺失。
  - **文件意义**：het矩阵的列id说明书，作用同haphom版。
- **`yp_het/yp_matrix_het_20221018.txt` / `yp_het/yp_matrix_het_z_20221018.txt`**
  - **结构形式**：行=基因（het collection覆盖的全部基因，含必需基因，共约5,639个，比haphom的
    4,554多，因为多了必需基因），列=7,011个het screen id。
  - **值的意义**：分别是未归一化 / Z分数版（Z变换规则同haphom的相对众数版）。
  - **缺失情况**：真实覆盖率不是均匀的（详见下方`het_profile_matrix.pkl`条目——对齐到项目统一
    4,554基因集合后真实有值的只约3,520列）。
  - **文件意义**：**和haphom矩阵的关系**：不是同一批基因的重复读出，而是**互补的基因集合**
    （het独有必需基因，haphom独有部分非必需基因的hap a/alpha单独视角）；两者的screen id空间也
    完全不重叠（haphom用1–187区间的一批id，het用87/109/414/...等另一批id）。

**项目内加工后的特征矩阵**（姊妹项目 `results/features/`，供直接建模用，路径见参考链接）：

- **`het_profile_matrix.pkl`**
  - **结构形式**：4,554 基因 × 7,011 列（对齐到项目统一的4,554基因集合后的het矩阵）。
  - **值的意义**：`fillna(0)`填出来的版本——原始NaN被填成了0。
  - **缺失情况**：⚠️ 真实覆盖率只有约3,520列（因为het测的很多是必需基因，我们的4,554基因里约
    一半在某个het screen里根本没被测到，NaN被填成了0），另外约3,491列因此变成**全零常数死列**
    （48.3%）。**任何要看"值"的分析（分箱、当预测目标）必须回到原始`yp_matrix_het_z_20221018.txt`
    保留真NaN，不能用这份pkl直接做值分析**（详见项目内`het_fillna_zero_pitfall`记忆）。
  - **文件意义**：当**输入特征**用（配合missing-flag）问题不大，但不能当值分析的数据源。
- **`het_profile_coverage.csv`**
  - **结构形式**：4,554行。
  - **值的意义**：每个基因在het矩阵里非NaN的screen数（`n_non_na_screens`）。
  - **缺失情况**：这份文件本身就是在量化缺失情况，不适用"缺失"这个概念。
  - **文件意义**：用于判断该基因的het表型数据是否够用，配合`het_profile_matrix.pkl`使用。
- **`growth_panel_matrix.pkl`**
  - **结构形式**：4,554 基因 × 7,689 列——从haphom的14,484列里筛出的子集。
  - **值的意义**：Z分数（规则同`yp_matrix_z_haphom`），筛选标准是覆盖质量好、值干净。
  - **缺失情况**：**保留真NaN，缺失率7.4%，无常数死列**——是这个源里目前最干净的版本。
  - **文件意义**：目前**可以直接拿来训练/验证的推荐版本**。
- **`growth_panel_condition_ids.json`**
  - **结构形式**：长度7,689的id列表。
  - **值的意义**：`growth_panel_matrix.pkl`那7,689列对应的原始screen id。
  - **缺失情况**：不适用。
  - **文件意义**：可回查`yp_screens_haphom_20221025.txt`拿到条件的具体含义（药物/培养基/表型
    描述），是`growth_panel_matrix.pkl`列名的说明书。

### Section 4 — 分析（在我们项目中的应用）
- **和源 1/2/3 的本质区别**：源 1/2/3 都是"敲除/诱导后测**基因表达**"，格子是`(扰动子, 读出基因)`；
  源 4 是"敲除后测**这一株细胞长得快不快**"，格子是`(扰动子, 条件)`，**没有"读出基因"这一维**——
  它是一个基因级的**标量**表型，不是基因对基因的表达矩阵。**不能套用源1/2/3那套阈值化出 DE/DIR
  label 的逻辑**（没有 M/p 这种"基因对基因"结构可供阈值化）。
- **适合接入的角色**：
  1. **另一个独立任务的标签**：把"敲除基因 → 在某条件下的生长 Z 分数"当**回归/分类目标**本身（如
     `yeast-rank-cross-lab` 现行主线在做的"基因表型可预测性"研究），而不是塞进转录组 DE/DIR 那条
     pipeline。
  2. **扰动子的上下文特征/先验**：如果某扰动子在很多条件下都显著影响生长（表型效应大），可以当作
     该基因"扰动烈度"的辅助特征，帮助 DE/DIR 任务判断"这个敲除大概率会引起大范围表达变化"（源1
     文档里提到的"慢生长混杂"现象，本质上就是源4测的这个量在源1里的副作用）。
  3. **essential/non-essential 基因的区分信号**：het vs haphom 的覆盖差异（已实测核实：haphom
     4,554个基因全部是het的子集，het独有1,085个基因即必需基因候选集，见Section 2）——**不只能当
     弱标签喂给其他任务，本身也可以是一个独立的预测目标**：给定基因的序列/网络/表达等特征，预测
     它是不是这1,085个必需基因之一。这是计算生物学里一个真实、成熟的问题（有专门的benchmark数据库
     OGEE收录多物种包括酵母的必需基因标注，也有大量机器学习方法论文用序列/网络特征预测必需性），
     不是本项目自造的问题，见"二、可能的任务"里的候选任务条目。
- ⚠️ **坑**：(a) haphom 和 het 是两套不重叠 id 空间、不重叠基因覆盖的矩阵，合并使用前必须先弄清楚
  一个基因到底该查哪套；(b) `het_profile_matrix.pkl` 的 `fillna(0)` 坑（见上表），任何值分析先回原始
  txt；(c) 与源 1（Deleteome）**扰动子基因大量重叠**（都是敲除同一批基因），但读出模态完全不同，
  不能因为基因名对得上就当成同一种标签去合并训练。

### 参考链接
- 论文 DOI：https://www.science.org/doi/full/10.1126/sciadv.adg5702
- 数据门户：www.yeastphenome.org
- 姊妹项目本地路径：
  - 原始下载：`/home/zhengz2/projects/yeast-rank-cross-lab/data/folder8_raw/`
  - 项目内加工后的特征矩阵：`/home/zhengz2/projects/yeast-rank-cross-lab/results/features/`
- md5 核对涉及的两处具体文件路径：
  - `/home/zhengz2/projects/yeast-rank-cross-lab/data/folder8_raw/yp_matrix_z_haphom_20221025.txt`
  - `/home/zhengz2/MiniShare/mini1/h100/public/Yeast/zz_view/yeast/8/yp_matrix_z_haphom_20221025.txt`
- 必需基因预测作为独立问题的文献支撑（OGEE数据库+方法论综述，均已核实可打开）：
  - [OGEE: an online gene essentiality database](https://pubmed.ncbi.nlm.nih.gov/22075992/)
  - [Essential gene prediction using limited gene essentiality information — semi-supervised ML, *PMC*](https://pmc.ncbi.nlm.nih.gov/articles/PMC7703937/)
  - [Research on the Computational Prediction of Essential Genes, *Frontiers in Cell and Developmental Biology*](https://www.frontiersin.org/journals/cell-and-developmental-biology/articles/10.3389/fcell.2021.803608/full)

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
