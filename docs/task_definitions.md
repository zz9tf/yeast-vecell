# 任务说明 — 定义

本文档合并自原 `supplementary_data_and_tasks.md`（任务定义/数据调研）与
`task_decomposition_analysis.md`（拆解合理性分析），作为"这个项目定义了哪些任务"的唯一权威说明。
**本文档只讲任务定义，不追踪进度/完成状态——进度见 [`RESULTS.md`](../RESULTS.md)。**

---

## 一、进行的任务

### Task 1 — 扰动 → 表达（旗舰，直接对标 VCWorld）
- **尝试回答的问题**：敲除/诱导 `P` 会不会让基因 `G` 差异表达（T1a-DE，Yes/No）？升还是降
  （T1b-DIR）？
- **数据**：Deleteome（首发，已用）→ IDEA / Hughes（已下载核实，未接入 pipeline，见
  [`data_sources.md`](data_sources.md)）。
- **读出**：转录组（logFC + p 已现成）。

#### 端到端技术规格（已验证）

**1. Input**
- **三元组定义**：`(pert=被敲除ORF, gene=读出ORF, context=Deleteome 数据集/敲除类型上下文)`。
- **生成方式**：不是这三个裸字段直接喂给 LLM，而是 `prompt` 阶段（`stages/prompt.py` +
  `support/DE_template.py`/`DIR_template.py`）把它们拼成一段完整文本。
- **文本构成**（这段文本包含的4类内容）：
  - `pert`/`gene` 各自的一句话描述（来自 `gene_desc.json`）；
  - 一段写死的 Deleteome 上下文散文（内容：BY4741 背景、SC 培养基、log 期、双色芯片；显式点出
    "这是完全敲除、有慢生长混杂"两条假设）；
  - 若干条 Evidence（检索出的类比案例，构造方式见第2项"Pipeline 看到的数据形式"）；
  - 最终要求模型输出的问题/答案格式（见第3、4项）。
- **产出文件**：`prompts.txt`（DE 任务和 DIR 任务分别产出一份，即 `de prompt` / `dir prompt`）。

**2. Pipeline 看到的数据形式**
- 源头：源1 Deleteome 原始矩阵（`deleteome_all_mutants_ex_wt_var_controls.txt`，行=6112读出ORF、
  列=每条件的 M/A/p 三列）。
- `prepare` 阶段：**直接阈值化**（不跑差异分析）——`p<0.05 & |M|>0.766` → DE=1，`p>0.1` 每扰动子
  抽200个当负例；DE 命中里 `M>0→Increase(1)` 否则 `Decrease(0)`。产出 `deleteome_DE.csv` /
  `deleteome_DIR.csv`（列 `pert,gene,label,split`）。
- `retrieve` 阶段：用 `perturbagen_similarity.json`(Costanzo SGA)、`results_close_gene.json`
  (STRING) 从 **train** 里挖出带真标签的类比对 `retrieved_pairs=[[pert,gene,label],...]`，写入
  `retrieval.json`。
- `prompt` 阶段：把这些类比对渲染成 Examples 代码块（每条含扰动子/读出基因描述 + 真实 `Result:`
  句）拼进模板，产出最终 `prompts.txt`。

**3. 推断**（v1 baseline，5步脚手架，`support/DE_template.py`/`DIR_template.py`）
1. Function & Analogue Identification——说清被敲基因的功能/通路/复合物，从 Evidence 里找同通路
   类比敲除，判断读出基因是否是已知的共功能/网络邻居；
2. Specificity & Relevance Analysis——判断这次敲除是广谱（慢生长/环境应激）还是窄谱（基因特异）
   效应，读出基因是否合理地在下游；
3. Downstream Cascade Simulation——用 YEASTRACT 风格 TF→靶逻辑，指出调控读出基因的候选 TF，
   敲除会提高还是降低该 TF 活性（DIR 版本额外要求指出该 TF 对读出基因是**激活子**还是**抑制子**）；
4. Causal Bridge & Evidence Synthesis——写出显式因果链 `敲除→通路→TF→读出基因`，引用 Evidence
   里的类比案例支持/反驳（DIR 版本的方向逻辑：降低激活子活性→**Decrease**；降低抑制子活性→
   **Increase**，反之亦然）；
5. Final Deterministic Prediction——落到闭集答案句。

   （A/B 两个 prompt 优化分支分别把第3/4步的 TF 符号强制拆成两问+按编号引用证据、或把5步压成
   3步+Examples 先验投票+Confidence/Final，详见 [`prompt_optimization.md`](prompt_optimization.md)；
   三者最终闭集答案句完全一致，可共用同一个 parser。）

**4. Output**（闭集答案句，逐字取自模板）
- T1a-DE：`"No. Deletion of {pert} does not differentially express {gene}."` /
  `"Yes. Deletion of {pert} results in differential expression of {gene}."` /
  `"There is insufficient evidence to determine how deletion of {pert} affects {gene}."`
  （对应 `choices_de = ["A) ...does not...", "B) ...results in..."]`）
- T1b-DIR：`"Decrease. Deletion of {pert} results in a decrease in expression of {gene}."` /
  `"Increase. Deletion of {pert} results in an increase in expression of {gene}."` /
  同款 insufficient-evidence 弃权句。

**5. 评测口径（`src/eval/score.py`）**：末次匹配（在回答文本里找每个类别正则的**最后一次**出现，
取位置最靠后的那个）解析出闭集答案 → 1/0/None(弃权)。指标：
- `answered%` = 非弃权占比；
- `Acc(overall)` = 弃权记错的总体准确率（RESULTS.md 表里 T1a 列的 "Acc"）；
- `Acc(answered)` = 只在非弃权子集上算的准确率（RESULTS.md 表里 T1b 列的 "方向Acc"——DIR 任务
  本身就是在 DE 命中子集上做的方向判断，故沿用同一个 `acc_answered`/`acc_overall` 计算但换个更
  贴切的名字）；
- **macro-F1、MCC**——只在非弃权子集上算，两个类各自的 F1 取平均（MCC 用标准 tp/tn/fp/fn 公式）。
  这是**主指标**。

**6. 怎么说明结果更好**：Deleteome 里 DIR 标签真实分布是**升66%/降34%**（35,234 up/18,207
down，`docs/pipeline.md`已核实），即"永远猜 Increase"的多数类
基线在 accuracy 上就有 66%，纯裸 Acc 骗人，所以**必须报 macro-F1/MCC**（这也是本项目从一开始就
选它们做主指标的原因）。已验证的判断标准：
- T1a-DE 和 T1b-DIR 的 macro-F1/MCC 都随模型规模单调提升（4B/7B/8B < 14B），复现 VCWorld 在人类
  数据上的"越强越准"（`RESULTS.md`：T1a-DE 14B `.680/.359` 领先；T1b-DIR 14B `.683/.372` 领先），
  这被视为"好现象"/pipeline 有效的证据。
- Majority-class 基线（DIR=66% Increase）和"YEASTRACT 符号规则"基线的计算方法见
  `src/eval/baselines.py`，数字见 `task_results.md`。
- 本任务（连同 T2A/T2B）统一配有一套**标准基线+消融套件**（Random、Retrieval-only、
  w/o Biocontext、w/o CoT），方法论和跨任务落地差异见
  [`prompt_optimization.md`](prompt_optimization.md)"标准基线+消融套件"一节，数字见
  [`task_results.md`](task_results.md) 对应表格，本节不重复。

**7. 已知的pipeline变体**（逐个变体单独说明其 Input/Pipeline 跟 v1 baseline 具体差异在哪一层；
完整方法论/渲染样例见 [`prompt_optimization.md`](prompt_optimization.md)，数字见
[`task_results.md`](task_results.md)，两处均不重复展开）：

- **v1（baseline）**
  - Input：即上面 1–4 项描述的三元组+生成方式+文本构成+产出文件，不改动。
  - Pipeline：`prepare→retrieve→prompt` 全部按上面 2 项所述跑，不改动。

- **A（机制结构化）**
  - Input：三元组、文本构成里的描述/上下文/Evidence 部分跟 v1 完全一样**不变**；唯一改动在文本
    构成第4类"最终要求模型输出的问题/答案格式"对应的推理指令——把上面第3项"推断"5步里的第3/4步
    （TF 符号判断、因果链引用证据）从叙述性要求改成**强制拆成两问+要求按编号引用 Evidence**。
  - Pipeline：不改动 `prepare`/`retrieve`，只改 `prompt` 阶段用的模板文件（`support/DE_template.py`
    →`support/variants/A_mechanism/DE_template.py`，DIR 同理），闭集答案句词表不变，`infer`/`score`
    阶段无需改动。

- **B（校准/强调 few-shot）**
  - Input：跟 A 同理，文本构成里描述/上下文/Evidence 不变；推理指令部分把 5 步压缩成
    "Examples 先验投票→轻量机制调整→校准决策"3 步，输出代码块新增 `Confidence:`/`Final:` 结构化
    字段。
  - Pipeline：只改 `prompt` 阶段模板（`support/variants/B_calibration/DE_template.py`），其余
    阶段不变。

- **消融1 — Retrieval-only**
  - Input：文本构成里去掉"最终要求模型输出问题/答案格式"里的多步推理指令，只保留 Evidence 本身；
    不经过 LLM 生成，改为对检索到的 `retrieved_pairs` 做最近邻投票（多数标签即预测）。
  - Pipeline：`prepare`/`retrieve` 不变，`prompt`/`infer` 两阶段被替换成一个纯规则脚本（读
    `retrieval.json`直接投票，不调用模型）。

- **消融2 — w/o Biocontext**
  - Input：文本构成里去掉"`pert`/`gene`各自的一句话描述"和"写死的 Deleteome 上下文散文"这两类，
    只保留裸 ID（ORF 名）+ Evidence + 输出格式要求。
  - Pipeline：只改 `prompt` 阶段的模板渲染逻辑（跳过描述/上下文两个字段的填充），`prepare`/
    `retrieve`/`infer`/`score` 不变。

- **消融3 — w/o CoT**
  - Input：文本构成的"最终要求模型输出问题/答案格式"部分，从"5步编号中间推理+Final答案句"压缩成
    只要求 Final 答案句本身，不要求写出任何中间步骤；闭集答案句词表不变。
  - Pipeline：只改 `prompt` 阶段模板的 Output 代码块定义，其余不变。

- **GAT（训练型传统ML对照）**
  - Input：给 GAT 的图节点特征（STRING跳数、TF签名状态、ESR成员身份、复合物共属关系，逐个基因
    节点拼成一条特征向量）。
  - Pipeline：`prepare` 产出的 train/test split 复用不变，直接建图（STRING+YEASTRACT关系）训练
    GAT 分类头，在 test split 上预测。PPI/知识图谱节点特征训分类头，直接对标VCWorld自建baseline
    先例（Wei et al., ICLR 2026, arXiv:2512.00306 Appendix B.2）。实现：
    `src/eval/gat_baseline.py`。

- **GenKI（训练型传统ML对照）**
  - Input：野生型表达数据 + 推导出的GRN。
  - Pipeline：用VGAE（变分图自编码器）在单一数据集的GRN上直接训练，虚拟敲除节点后看重建变化来
    预测响应基因。只用WT表达+GRN预测敲除响应基因，任务形式=DE预测（Yang et al. 2023, *Nucleic
    Acids Research* 51(13):6578-6592）。

- **KGE-TGI（训练型传统ML对照）**
  - Input：整合好的知识图谱（TF-靶基因关系网络）。
  - Pipeline：用Multi-subgraph GCN（按关系类型切分异构KG分别卷积）做TF-靶基因关系存在性+方向
    联合分类，任务形式最贴合T1b-DIR方向分类（Wu et al. 2023, *PLOS Computational Biology*
    19(6):e1011207）。

- **MultiXrank（RWR+监督分类器，训练型传统ML对照）**
  - Input：网络传播（Random Walk with Restart）算出的邻近度分数当特征。
  - Pipeline：训练XGBoost/随机森林做关联预测，guilt-by-association（McGary et al. 2007式）的
    2024年监督式升级版（Baptista, Brière, Baudot 2024, *BMC Bioinformatics* 25:70）。

> 以上4个训练型传统ML方法是并列的独立对照，不是选1个赢家淘汰其余3个；完整方法论细节见
> [`prompt_optimization.md`](prompt_optimization.md)"变体4"一节，不重复展开。

- **跨变体的模型选择约定**：消融1-3、A/B 如果需要跑 LLM，统一只用 **Qwen2.5-14B** 一个代表模型
  （不是4个模型全跑一遍），理由见 [`prompt_optimization.md`](prompt_optimization.md)"消融/变体
  统一用哪个模型跑"一节。

> 各变体目前是否已经跑出数字，见 [`task_results.md`](task_results.md) 对应表格，本节不重复。

#### 生物学意义上的更细分解（同一Input下按机制拆的候选子问题，非数据源层面的拆分）

> 真实数字见 [`task_results.md`](task_results.md) Task 1 分解1/分解2/分解3。

- **读出基因是否被扰动子直接转录调控，还是通过蛋白互作/代谢通路间接波及**：这不是"按数据源切"，
  而是同一个Deleteome矩阵内部按因果链深度（1跳 vs 多跳）划出的机制子问题，可用 BioGRID/STRING
  的调控网络跳数标注读出基因，分别测试模型对"直接调控"和"间接级联"两种推理难度的表现。
  **方法**：用 `data/knowledge/results_close_gene.json`（STRING v12, combined_score≥700）里
  `{pert: {direct_neighbors:[...1跳...], two_hop_neighbors:[...2跳...]}}`存的真实图跳数，按原样
  切出"1跳直接"vs"2跳间接"两个子集。覆盖率有限：测试集里落在"1跳"或"2跳"任一类别的 (pert,gene)
  对只占全部 test case 的约0.7%，子集样本量小（三位数量级），结论需谨慎对待。
- **读出基因是否属于环境应激响应(ESR)基因集合，还是基因特异响应基因**：Gasch et al. 2000 鉴定出
  约900个基因组成的"环境应激响应(ESR)"集合，这批基因在几乎任何环境突变下都会趋同响应（不管具体
  扰动子是什么）
  [Gasch et al. 2000, *Mol. Biol. Cell*](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC15070/)。
  对这批基因而言，"DE会不会发生"本质上退化成"这次敲除是否引发了慢生长/普遍应激"这个粗粒度问题，
  跟对非ESR基因做"基因特异性调控推理"是完全不同性质的生物学子问题——可以按读出基因是否属于ESR
  集合分层评测，检验模型是否把这两种机制混为一谈。
  **方法**：用 Gasch 实验室维护的"updated ESR gene sets"页面
  ([gasch.genetics.wisc.edu/esr/](https://gasch.genetics.wisc.edu/esr/)，文件
  `ESR_clusters_UPDATED_2017-FORPUBLICATION.xlsx`）中"ORIGINAL ESR GROUPS"列（保持跟原论文2000
  年定义一致）：iESR cluster 283个 + PAC cluster 457个 + RP cluster 128个 = 868个基因，与文献
  引用的"283诱导+585抑制=868"吻合。已存档为`data/knowledge/esr_genes_gasch2000.json`。
- **读出基因是否与扰动子同属一个已知蛋白复合物，还是跨复合物的调控溢出**：同一转录因子对同一
  蛋白复合物内多个亚基的调控通常一致（复合物需要整体表达同步），对复合物外靶基因的调控则更依赖
  具体的通路逻辑；可按读出基因是否与扰动子编码蛋白同属一个已知复合物（CYC2008等复合物数据库）
  分层，把"复合物共调控"和"通路特异调控"拆成两个可分别验证的子问题。
  **方法**：用 CYC2008 论文（Pu et al. 2009, *NAR*，manuscript gkn1005）官方补充材料
  `nar-02139-s-2008-File005.xls` 的 `CYC2008_complex` 表（1627基因/408复合物，与论文摘要
  "408 manually curated complexes"吻合），归档为`data/knowledge/CYC2008_complex_raw.xls`+
  `data/knowledge/cyc2008_complex_members.json`（基因→复合物ID映射）。结果与 EBI Complex
  Portal 酵母复合物组（交叉验证用的替代数据源，`data/knowledge/complexportal_559292_raw.tsv`+
  `complex_members_complexportal.json`）高度一致，详见`task_results.md`分解3。

### Task 2A — 扰动 → 生长表型（chemical-genomics 式，已采用的框架）
- **尝试回答的问题**：敲除 `P` 在条件 `C`（药物/胁迫）下有没有生长表型（T2A-DE）？更敏感还是更抗
  （T2A-DIR）？
- **数据**：Hillenmeyer 2008 / `yeast-rank-cross-lab` 的 Yeast Phenome 矩阵（源4，见
  [`data_sources.md`](data_sources.md)）。
- **角色**：扰动子=被敲基因；上下文=条件 `C`；读出=相对适合度。这是"多条件"轴最自然落地的地方
  （条件本身就是真上下文轴，比 Task 1 拿数据集当上下文更实在）。

#### 端到端技术规格（已验证）

**1. Input**
- 三元组：`(pert=被敲除ORF, context=条件/screen)`——注意这里读出轴本身就是条件（跟 Task 1
  "读出=基因、上下文=数据集"角色互换）。
- prompt：由 `support/task2/DE_template.py`/`DIR_template.py` 拼出，包含：
  - 被敲基因描述；
  - 条件/screen 描述（`context_desc.json`，源自 `haphom_growth_contexts.csv`）；
  - 一段写死的 assay 上下文散文（yeastphenome compendium、homozygous/HOP 库、"相对野生型的
    适合度"）；
  - Examples（构造方式见第2项）。
- 产出文件：`t2de_prompts.txt`/`t2dir_prompts.txt`。

**2. Pipeline 看到的数据形式**
- 源头：源4 `yp_matrix_z_haphom`（Hillenmeyer 2008 HOP 库，4554基因×7689个growth筛选的 z-score
  矩阵）。
- `src/task2/build_growth_labels.py` 阈值化：产出 `haphom_growth_phenotype.csv`（DE-analog：有无
  表型）和 `haphom_growth_direction.csv`（DIR-analog：敏感/抗），列 `pert,context,label,split`。
- `retrieve` 阶段：读出列换成 `context`，基因相似度换成 `condition_similarity.json`
  （`src/knowledge/build_condition_sim.py` 由 yp 矩阵列-列相关算出的条件邻居），扰动子相似度仍用
  `perturbagen_similarity.json`（Costanzo SGA）；一样产出带真标签的 `retrieved_pairs`。
- `prompt` 阶段：渲染出最终 `t2de_prompts.txt`/`t2dir_prompts.txt`。

**3. 推断**（`support/task2/{DE,DIR}_template.py`，4步脚手架，比 Task 1 少一步）
- DE：
  1. Function of pert——被敲基因服务于哪个通路/过程；
  2. Relevance to the condition——该通路是否是耐受/适应这个特定胁迫或药物所必需的（例如敲掉缓冲
     药物靶点的基因→敏感；敲掉抗性通路的负调控子→抗性；核心必需邻近基因→广谱慢生长）；
  3. Analogue check——Evidence 里功能相似的敲除或同条件下的其它敲除是否显示表型；
  4. Final deterministic call。
- DIR：
  1. Function of pert 及其通路；
  2. Direction logic——敲除是削弱了这个胁迫下需要的防御/耐受通路（→更敏感）还是移除了胁迫本身
     利用的靶点/负调控子（→更抗）；
  3. Analogue check；
  4. Final call。
- **注意**：这里没有 Task 1 那种"YEASTRACT 激活子/抑制子符号"逻辑——"敏感vs抗是适合度问题不是调控符号
  问题，T2A-DIR 需要自己的脚手架，不能套 T1 方向逻辑"，模板已按此重写为"防御通路 vs 靶点/负
  调控子"这套独立逻辑。

**4. Output**（闭集答案句，逐字取自模板）
- T2A-DE：`"No. Deletion of {pert} does not cause a growth phenotype under this condition."` /
  `"Yes. Deletion of {pert} causes a growth phenotype under this condition."` / 同款
  insufficient-evidence 弃权句。
- T2A-DIR：`"Sensitive. Deletion of {pert} makes the cell more sensitive under this condition."` /
  `"Resistant. Deletion of {pert} makes the cell more resistant under this condition."` / 弃权句。

**5. 评测口径**
- 与 Task 1 完全同一套 `src/eval/score.py`（`--task growth` / `--task growth_dir`，
  `--readout-col context`）。
- 同样报 answered%、Acc(overall)、Acc(answered，RESULTS.md 里对应"方向Acc"列）、macro-F1、MCC，
  判定逻辑同 Task 1。

**6. 怎么说明结果更好**
- T2A-DIR 真实标签分布是**抗25%/敏感75%**（`RESULTS.md`"任务&数据"表），majority-class
  （猜 Sensitive）accuracy 基线理论上有 75%——同样是"裸 Acc 骗人，必须看 macro-F1/MCC"的场景，
  且比 T1 更极端。
- 已验证的判断标准（本项目的关键负结果）：**macro-F1/MCC 不随模型规模提升**——`RESULTS.md`
  "全模型对比"表显示 T2A-DE 最优是 7B（.645）、14B 反而掉到第 3（.615）；T2A-DIR 四个模型全部
  挤在 MCC `.07–.11`（近随机信号），且不随规模单调。这被明确判定为"坏信号"/"开放难题"：说明
  检索到的知识图谱证据对"扰动→生长表型方向"的支撑远弱于对"扰动→转录响应"的支撑，推测是
  化学-遗传适合度关系比调控/表达关系更依赖定量剂量效应、纯文本检索难覆盖。
- Majority-class 基线的计算方法见 `src/eval/baselines.py`，数字见 `task_results.md`；
  "网络邻居/LogReg"等对照基线是候选补充项，方法论待定。
- 本任务同样配有 Task 1 一节详述的**标准基线+消融套件**（Random、Retrieval-only、w/o Biocontext、
  w/o CoT），方法论见 [`prompt_optimization.md`](prompt_optimization.md)，数字见
  [`task_results.md`](task_results.md) T2A-DE/T2A-DIR 表格，本节不重复。

**7. 已知的pipeline变体**
- **v1（baseline）**：即上面 1–6 项描述的这一整套（`support/task2/DE_template.py`/
  `DIR_template.py`）。
- **A（机制结构化）**
  - Input：三元组、文本构成里的基因描述/条件描述/assay上下文散文跟 v1 完全一样不变；唯一改动在
    第3项4步脚手架的第2/3步（Relevance to condition / Direction logic、Analogue check）——把这
    两步从叙述性要求改成**强制拆成两问+要求按编号引用 Evidence**（第2问回答该通路是否是耐受/
    适应这个条件所必需、第3问列出支持该判断的同条件/同功能邻居敲除编号）。
  - Pipeline：不改动 `prepare`/`retrieve`，只改 `prompt` 阶段用的模板文件（
    `support/variants/A_mechanism/task2/DE_template.py`/`DIR_template.py`），闭集答案句词表
    不变，`infer`/`score` 阶段无需改动。

- **B（校准/强调 few-shot）**
  - Input：跟 A 同理，基因描述/条件描述/assay上下文不变；推理指令部分把4步压缩成"Examples先验
    投票（同条件/同功能邻居敲除的表型多数）→轻量机制调整（Function of pert 是否有理由偏离多数）
    →校准决策"3步，输出代码块新增 `Confidence:`/`Final:` 结构化字段。
  - Pipeline：只改 `prompt` 阶段模板（`support/variants/B_calibration/task2/DE_template.py`/
    `DIR_template.py`），其余阶段不变。
- **标准基线+消融套件（Random / Retrieval-only / w/o Biocontext / w/o CoT）**：方法论（含 T2A
  4步脚手架"去CoT"该删哪几步的落地差异）见 [`prompt_optimization.md`](prompt_optimization.md)
  "标准基线+消融套件"一节，数字见 `task_results.md`。
- **矩阵分解 NRBdMF/SRMF（训练型传统ML对照）**
  - Input：基因×条件的z-score矩阵（`yp_matrix_z_haphom`）。
  - Pipeline：做邻域正则化矩阵分解，NRBdMF天然支持+1/-1方向性标签，贴合T2A-DIR（敏感vs抗）。
    **关键结构限制**：该split按基因整体切分（train/test基因零重叠），每个test基因在train矩阵里
    都是行冷启动，需要"该基因在其它Hillenmeyer条件下的真实z-score格子"做fold-in——**这个信息
    通道对LLM结构上不可用**（LLM只接触检索到的文本证据，不接触原始表型矩阵），所以同时报告
    "fold-in"和"严格冷启动（去掉这个通道）"两个版本，前者跟LLM不是同一信息预算下的公平对比，
    后者才是。实现：`src/eval/matrix_factorization_baseline.py`（Yasuo et al. 2023,
    *J. Chem. Inf. Model.*；Wang et al. 2017, *BMC Cancer* 17:513）。

- **GAT（从T1移植，训练型传统ML对照）**
  - Input：图节点特征。
  - Pipeline：同T1的图神经网络架构，图结构换成化合物结构相似性/靶点网络（而非STRING/
    YEASTRACT）。

- **MultiXrank（RWR+监督分类器，训练型传统ML对照）**
  - Input：网络传播邻近度分数当特征。
  - Pipeline：训练分类器，图结构换成条件相似度网络（`condition_similarity.json`已有）。

- **弹性网络回归/随机森林（训练型传统ML对照）**
  - Input：基因组学特征（需要重新构造T2A自己的特征集，不能直接复用人类癌症数据的表达/突变特征）。
  - Pipeline：标准sklearn训练，姊妹领域（GDSC/CCLE人类癌症药物敏感性预测）公认的baseline下限。

> 以上4个训练型传统ML方法是并列的独立对照，不是选1个赢家淘汰其余3个；完整方法论细节见
> [`prompt_optimization.md`](prompt_optimization.md)"变体4"一节，数字见 `task_results.md`
> T2A-DE/T2A-DIR 表格，不重复展开。
- **消融/A-B分支/变体4统一用哪个代表模型跑，Task 2A 待定**：不能直接照搬 Task 1 的 Qwen2.5-14B——
  Task 2A 主结果里最优模型按指标分散（Macro-F1/MCC最优是Qwen2.5-7B，Acc/Answered%最优是
  Qwen3-4B，见 `task_results.md`"T2A-DE 主结果"），选哪个代表模型需要额外讨论，原则见
  [`prompt_optimization.md`](prompt_optimization.md)"消融/变体统一用哪个模型跑"一节。

#### 生物学意义上的更细分解（按条件的机制类别拆的候选子问题，非数据源层面的拆分）
- **该基因在某一胁迫机制大类下是否敏感，而不是在7689个原子条件标签上逐一判断**：Hillenmeyer et
  al. 2008 的1144个chemogenomic assay本身覆盖多种性质完全不同的胁迫机制——DNA损伤类（如MMS、
  HU）、氧化应激类（H2O2、diamide一类，机制上与Gasch et al. 2000鉴定的ESR高度重叠）、渗透压/
  细胞壁应激类、药物靶点抑制/多重耐药外排类等
  [Hillenmeyer et al. 2008, *Science*](https://pubmed.ncbi.nlm.nih.gov/18420932/)。当前T2A把
  "条件"当成7689个几乎互不相同的原子标签处理（7463/7689 context 互不相同，几乎不可分箱），
  但按胁迫机制大类重新分组是一个不同粒度的生物学子问题：模型预测"这个基因在DNA损伤条件下
  是否敏感"和预测"在渗透压条件下是否敏感"依赖的是完全不同的通路知识（DNA修复通路 vs 渗透压响应
  通路），拆开评测才能看出模型是不是真的按机制推理，而不是记住了条件名字的表面模式。
  **方法**：本仓库没有精确的"机制类别"注释，用 `haphom_growth_contexts.csv` 的 `conditionset`
  （化合物名+浓度）字段做**关键词正则匹配**（如 MMS/bleomycin/cisplatin→DNA损伤，
  H2O2/diamide/menadione→氧化应激，NaCl/sorbitol/caspofungin→渗透压细胞壁，
  rapamycin/cycloheximide/fluconazole等命名药物→药物靶点/耐药外排），只对能明确命中关键词的
  条件子集算分（覆盖T2A-DE测试集58980行中的27.1%/16001行），其余标"未分类"排除，不是对7689个
  条件的完整机制标注。
- **被敲基因是否是该化合物的直接分子靶点，还是只是耐受该胁迫的旁路通路成员**：同一化合物对基因的
  影响可以来自两种不同的因果距离——被扰动基因本身编码了化合物的直接分子靶点（抑制该基因产物=
  化合物机制的核心环节），或者只是缓冲/耐受该胁迫的旁路通路上的一员（敲除后耐受能力下降，但基因
  本身不是靶点）。这是Hillenmeyer 2008数据集设计上天然支持的一个子问题（同一condition下靶点基因
  通常有远强于旁路基因的表型），可按基因是否为已知药物靶点分层验证。
  **方法/覆盖率**：用 `4932.protein_chemical.links.detailed.v5.0.tsv.gz`（STITCH v5.0酵母
  蛋白-化合物互作，见`data_sources.md`）做靶点匹配——141个Hillenmeyer化合物里只有13个能按PubChem
  CID精确匹配到STITCH记录，其中只有7个有`combined_score≥700`高置信靶点；"直接靶点"子集在
  T2A-DE测试集里最终只有**3个case**，统计上不足以支撑分层评测。根源不是数据源缺失，是这批化合物
  本身多为小众/文库内部编号，公开化合物-靶点数据库天然覆盖不到。
- **该基因的敏感性是否随浓度单调变化，还是只是阈值型的有/无判断**：Hillenmeyer设计里部分化合物
  覆盖了多个浓度点，代表的是一个连续的剂量-响应关系，而不是当前T2A-DE/DIR框定的二分类判断——
  这是一个可以独立验证的子问题（模型能否理解"剂量越高效应越强"这类定量关系），跟当前"有没有
  表型/方向哪边"这种阈值化二分推理是不同性质的能力。
  **方法**：在T2A-DE测试集用到的273个context里，按"同化合物+同论文+同collection、浓度可解析为
  统一单位、distinct浓度数≥3"筛出11个真实的多浓度系列（如cisplatin 8个浓度点、
  rapamycin/HU/FK506等，均来自Hillenmeyer 2008本身，pmid 18420932），覆盖55个distinct
  context/12331行测试样本。

> 上述三个分解的数字见 [`task_results.md`](task_results.md) Task 2A 分解结果，本节不重复。

### Task 2B — 遗传互作（SGA 式，双扰动）
- **尝试回答的问题**：这对基因 `(A, B)` 之间是否存在统计显著的遗传互作（**T2B-DE**，Yes/No）？
  如果存在，是负向（合成致死/病）还是正向（缓解/抑制）（**T2B-DIR**，只在 T2B-DE 命中的子集上判断）？
  这是仿照 Task 1（T1a-DE→T1b-DIR）、Task 2A（T2A-DE→T2A-DIR）同款两级级联结构补上的门槛问题——
  "是否存在互作"本身是真正的稀有事件检测（详见下方"6. 怎么说明结果更好"），不能默认所有输入基因对
  都已经是显著互作。
- **数据**：Costanzo 2016 全基因组遗传互作网络（`thecellmap.org`）。**但本仓库实际能读到的本地
  文件（`folder1_GI_raw/Genetic.interaction.score.tsv`）不是这个全基因组网络本身，而是其中一个
  "以必需基因为query"的 E-MAP 子集**——已实测核实：该文件的query轴（行）100%是`_tsq`后缀的
  温度敏感(TS)等位基因（必需基因无法直接敲除，只能靠TS等位基因在限制温度下失活来测），array轴
  （列）是`_dma`（缺失突变体阵列，非必需基因，3,892列/83%）与`_tsa`（TS等位基因阵列，必需基因，
  792列/17%）的混合，即这是Costanzo文献里"ExE+ExN"两张子网络（必需×必需、必需×非必需），
  **不包含"NxN"（非必需×非必需）这张覆盖基因对数量最大的子网络**。这意味着Task 2B 目前能覆盖到
  的基因范围以"query侧=必需基因"为限（约4,939个query基因），不是全基因组任意基因对，详见下方
  "6. 怎么说明结果更好"里7.15% vs 0.8%的核实结论。
- **角色**：扰动子=**基因对**（双敲）。对 LLM 的"通路冗余/缓冲"推理特别对味——白盒思路里价值最高
  的补充任务，因为它是唯一真正"不同"（双扰动）的任务类型。

#### 端到端技术规格（计划中的设计——Costanzo 2016 尚未接入 pipeline，以下均为设计预期，非已验证结果）

> Task 2B 目前在 `RESULTS.md`/`docs/pipeline.md` 里都明确标为"仍列为后续"/"🟡 后续"，
> `src/task2/` 下还没有对应的 build 脚本、`support/` 下也还没有 T2B 模板文件——下面按"如果照
> Task 1/2A 的既有 CLI 套路实现，应该长什么样"来写，全部标注为**待实现/设计阶段**。

**1. Input（设计）**
- 三元组：`(pert=基因对A+B, context=互作类型/SGA screen 上下文)`，或退化为 `(pertA, pertB,
  context)` 三个字段喂给同一套 `prepare→retrieve→prompt` CLI——T2B-DE 和 T2B-DIR 各自单独一份
  input（仿照 T1a-DE/T1b-DIR 分别产出 `de prompt`/`dir prompt` 的做法）。
- **待实现**：需要给 `prepare`/`retrieve`/`prompt` 增加"扰动子是基因对"的支持，目前 CLI 的
  `pert` 列是单基因假设。

**2. Pipeline 看到的数据形式（设计）**
- 源头：Costanzo 2016 全基因组遗传互作网络（`thecellmap.org`），仓库里已有
  `folder1_GI_raw/Genetic.interaction.score.tsv` 用于 `perturbagen_similarity.json` 检索，但
  **尚未**被当作 T2B 自己的标签源接入。**已实测核实该文件的范围限定**：query轴（5,346行，
  collapse到基因层面后4,939个基因）100%是必需基因的TS等位基因（`_tsq`后缀），array轴（4,684列，
  collapse后4,450个基因）是非必需基因缺失突变体（`_dma`，83%）+必需基因TS等位基因（`_tsa`，
  17%）的混合——即ExE+ExN子网络，不含NxN。这份数据本身**不是全基因组随机基因对的代表性样本**，
  而是"以必需基因为query"的定向子集，用它接入T2B标签时需要在文档/结果里明确标注这个范围限定，
  不能默认它代表全基因组的互作比例（详见"6. 怎么说明结果更好"）。
- 预期阈值化逻辑（两级，仿照 Task 1 的 DE→DIR 阈值化）：
  - **T2B-DE**：`|ε-score| > 阈值 & 统计显著` → 存在互作(label=1)；不显著/未测到 → 不存在互作
    (label=0)。产出 `sga_DE.csv`（列预期 `pertA,pertB,label,split`）——**待实现**。
  - **T2B-DIR**：只在 T2B-DE=1 的子集上，`sign(ε-score)` → 负向(合成致死/病) vs 正向(缓解/抑制)。
    产出 `sga_DIR.csv`（列预期 `pertA,pertB,label,split`）——**待实现**。
- **已知的跨任务泄漏坑**：Costanzo SGA profile 同时被 Task 1 检索当
  "扰动子相似度"用，若 T2B 也用同一份 SGA 数据当标签，需要把"检索相似度来源"和"T2B 标签来源"
  严格分开，避免用同一数据集的相似度信息去预测该数据集自身的标签。

**3. 推断（设计）**
- **T2B-DE**：预期判断基因 A、B 是否存在功能/通路关联（通路重叠、复合物共属、已知互作网络里的
  邻近程度）——关联度越高，存在显著互作的先验概率越高；关联度低/网络距离远，则倾向预测"不存在
  互作"。这一步的推理逻辑跟 T2B-DIR 不同，是"关联强度判断"而非"互作性质判断"。
- **T2B-DIR**：预期沿用 v1 的 5 步脚手架结构，但机制内容换成"通路冗余/缓冲"逻辑——判断基因 A、B
  是否在同一通路/复合物（冗余→负互作/合成致死概率高）还是在不同的平行/补偿通路（缓冲→正互作/
  抑制概率高），而不是 Task 1 的 TF→靶转录逻辑。
- **待实现**：T2B-DE 和 T2B-DIR 的具体脚手架文本都待编写，目前没有 `support/task2b/` 或类似的
  模板文件。

**4. Output（设计）**
- T2B-DE：预期闭集答案句形如 `"No. This gene pair does not show a significant genetic
  interaction."` / `"Yes. This gene pair shows a significant genetic interaction."` /
  insufficient-evidence 弃权句。
- T2B-DIR：预期闭集答案句形如 `"Negative. The double deletion shows a negative (synthetic
  lethal/sick) genetic interaction."` / `"Positive. The double deletion shows a positive
  (alleviating/suppressive) genetic interaction."` / insufficient-evidence 弃权句。
- **待确认**：两组都是根据 Task 1/2A 模板的措辞风格推断出的预期格式，原文没有现成模板可核对。

**5. 评测口径（设计）**
- 预期复用 `src/eval/score.py` 同一套 answered%/Acc/macro-F1/MCC 框架，T2B-DE 和 T2B-DIR 分开
  计分（仿照 T1a-DE/T1b-DIR、T2A-DE/T2A-DIR 各自一行的做法），`--task` 需新增如 `sga`/`sga_dir`
  的分支，含对应的正则 pattern——待实现。

**6. 怎么说明结果更好（设计）**

> **两种口径需要分别标注、都保留**：本地`|ε|≥0.08`阈值算出的显著互作率实测为**7.15%**（见②），
> 跟论文全基因组口径约2.4%（见①）不是同一统计量的两次估计，而是两个不同群体/口径下的数字，
> 不能简单二选一或取平均：

- **① 全基因组口径（论文原文数字）**：Costanzo et al. 2016（*Science*）原文摘要报告构建了
  **超过2300万个双突变体**，鉴定出**约55万个负向、约35万个正向**遗传互作
  [Costanzo et al. 2016, *Science*](https://pubmed.ncbi.nlm.nih.gov/27708008/)。核算负向互作
  占比 = 55万/2300万 ≈ **2.4%**（正+负合计约3.9%；用"complete dataset"~23M对/55万负向计算，
  论文另给出的"representative subset"~19M对/46万负向比例同样约2.4%）。这2.4%仍是远比50/50严重
  的类别不均衡，和 T1a-DE 真实命中率0.59%属同一类"罕见事件检测"问题，
  [An Integrative Multi-Network and Multi-Classifier Approach to Predict Genetic
  Interactions, *PLOS Comp Bio*](https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1000928)
  也把类别不均衡列为该领域核心方法学挑战，普遍用under-sampling、**AUPRC**（而非AUROC/accuracy）
  应对。
  **判定标准（来自 Costanzo 2016 方法学/supplementary）**：论文定义三档置信阈值——
  lenient（仅`P<0.05`）、intermediate（`P<0.05` 且 `|ε|>0.08`，论文主分析采用的档位）、
  stringent（`P<0.05` 且 `ε>0.16`或`ε<-0.12`）。论文intermediate档的量级阈值`|ε|>0.08`和本仓库
  `build_sga_labels.py`用的`|ε|≥0.08`数值上一致，但论文额外要求`P<0.05`的统计显著性联合判据，
  本仓库这份本地矩阵没有配套的p值文件，只能做纯量级阈值——这会把一部分"量级够大但统计上不显著"
  的噪声也计入"显著互作"，是7.15%偏高的**次要**原因（详见②）。
- **② 本地E-MAP子集口径（本仓库实测数字，范围不同，非同一统计量）**：`src/task2/
  build_sga_labels.py` 从 `folder1_GI_raw/Genetic.interaction.score.tsv` 算出的**7.15%**，
  测的**不是全基因组随机基因对**，而是一个**以必需基因为query的定向E-MAP子集**：该文件query轴
  （行）100%是`_tsq`必需基因TS等位基因（collapse后4,939个query基因），array轴（列）是`_dma`
  非必需基因缺失突变体（83%）+`_tsa`必需基因TS等位基因（17%）的混合，即Costanzo文献里的
  "ExE+ExN"两张子网络，**不含"NxN"（非必需×非必需，全基因组里基因对数量最大的一张子网络）**。
  Costanzo 2016论文本身报告"Essential genes participate in ~5-fold more negative and positive
  interactions than nonessential genes"（必需基因是网络里连接度显著更高的hub），即本地这份
  query=必需基因的子集，其互作命中率天然应该系统性高于全基因组平均，7.15% vs 2.4%（约3倍）
  这个方向和量级与"必需基因~5倍连接度"的说法量级吻合。
- **结论（差异归因）**：7.15% vs 2.4%（论文全基因组口径）的差异**主要来自①query基因群体不同**
  （本地=必需基因TS等位基因定向子集 vs 论文全基因组随机基因对），**次要来自②阈值判据不同**
  （本地只有量级阈值`|ε|≥0.08`、缺论文要求的`P<0.05`联合判据）。两者方向一致、都会推高本地数字，
  但量级上①是主因（必需基因~5倍连接度可以直接解释3倍左右的差距量级），②是次要放大因素（没有
  p值文件因此无法单独量化②的贡献，需要在有p值数据时补充验证）。两个数字测的不是同一件事：
  2.4%回答"全基因组任意基因对里显著互作有多罕见"，7.15%回答"以必需基因为query时，其与全基因组
  阵列的显著互作有多常见"——T2B-DE 的实际不均衡程度取决于最终label CSV覆盖的基因范围是否等于
  这份必需基因子集：如果Task 2B最终只能用这份本地数据做标签源，那7.15%（而非2.4%）才是T2B-DE
  实测会遇到的真实类别分布，需要按7.15%/92.85%重新评估不均衡程度和majority-class基线，不能
  照搬全基因组口径的2.4%。
- **T2B-DIR 层面（在 T2B-DE=1 的子集内，不均衡温和）**：Costanzo 2016 论文原文报告全基因组互作
  网络里约55万个负向互作、约35万个正向互作（负/正约61%/39%，约1.57:1），但这是**全网络层面的
  统计，不是本项目实际会用的阈值化标签分布**——本仓库自己按 ε-score 阈值切出 `sga_DIR.csv` 后的
  真实类别比例仍**待确认**，需要接入数据后实测，不能直接照搬论文的全网络比例当 majority-class
  基线。这一层61%/39%只是**中等程度**的不均衡，不应与 T2B-DE 层面的严重程度（全基因组口径约
  97.6%/2.4%，或本地E-MAP子集口径约92.85%/7.15%，视最终标签源而定）混为一谈，也不应夸大成
  "高度不均衡"。
- 实现时应比照 Task 1/2A 的做法，对 T2B-DE 和 T2B-DIR 分别统计真实标签分布、算出 majority-class
  accuracy 上限，再决定主指标——T2B-DE 大概率需要 macro-F1/MCC 或 AUPRC；T2B-DIR 不均衡温和，
  但同样建议报 macro-F1/MCC 而非裸accuracy。
- 本任务同样应配 Task 1/2A 那套**标准基线+消融套件**，方法论见
  [`prompt_optimization.md`](prompt_optimization.md)，变体清单见下方"7. 已知的pipeline变体"。

**7. 已知的pipeline变体**
- **v1（baseline）**：即上面 1–6 项描述的这一整套（设计阶段，尚未接入 pipeline，见本任务小节
  标题）。
- **A/B prompt 分支**：暂无对应变体设计。
- **标准基线+消融套件（Random / Retrieval-only / w/o Biocontext / w/o CoT）**：方法论跟 T1/T2A
  同一套，见 [`prompt_optimization.md`](prompt_optimization.md)；T2B 的标签口径本身尚未定案
  （见上方"6. 怎么说明结果更好"①②两种口径），落地时以最终定稿的口径为准。

#### 生物学意义上的更细分解（按互作机制类别拆的候选子问题，非数据源层面的拆分；设计阶段）
- **基因对A、B之间是负向互作(合成致死/病)还是正向互作(缓解/抑制)，T2B-DIR是否该用同一套脚手架
  判断这两类**：Costanzo et al. 2016 摘要原文报告"Negative interactions connected functionally
  related genes, mapped core bioprocesses"、"Positive interactions often mapped general
  regulatory connections among gene pairs, rather than shared functionality"
  [Costanzo et al. 2016, *Science*](https://pubmed.ncbi.nlm.nih.gov/27708008/)（该研究构建了
  超过2300万个双突变体，鉴定出约35万个正向、约55万个负向互作）——即负向互作连接功能相关基因、
  勾勒核心生物过程，正向互作更多反映调控关系而非功能相似性。（**"多发生在冗余/平行通路之间"这类
  更具体的机制描述，是该领域对负向互作机制的一般性认识，不是论文摘要的逐字结论**，负向互作也可能
  发生在同通路内，取决于具体案例。）这意味着"预测负向互作"和"预测正向互作"依赖的是两套不同的
  机制知识（功能冗余判断 vs 上下游调控关系判断），值得在 T2B-DIR 内部拆成两个独立验证的子问题，
  而不是用同一套"通路冗余/缓冲"脚手架不加区分地处理所有基因对。
- **基因对A、B是否同属一个已知蛋白复合物，还是跨复合物/跨通路的关系**：Baryshnikova et al. 2010
  提出的定量SGA评分方法支持把基因对按"是否同属一个蛋白复合物"分层
  [Baryshnikova et al. 2010, *Nat. Methods*](https://www.nature.com/articles/nmeth.1534)——
  复合物内基因对的负向互作通常代表亚基间的功能冗余（合成致死概率高），跨复合物/跨通路的基因对
  互作更可能反映真正的通路间缓冲或调控串扰。可用CYC2008复合物数据库把基因对分成"复合物内"和
  "跨复合物"两类，分别验证模型是否需要不同的推理逻辑。
- **基因对A、B是否都有已知功能注释，还是至少一个功能未知**：如果基因对里至少一个成员已有GO注释/
  复合物成员身份，模型可以类比该基因的已知功能做推理；如果两个基因都缺乏功能注释，模型只能依赖
  检索到的互作网络结构本身做纯粹的"网络位置"推理，不涉及具体生物学机制——这是两种难度和推理方式
  都不同的子问题，可用于分别测试模型"利用已知机制类比"与"纯拓扑/关联推断"两种能力。

### Task 3 — 基因必需性预测（单基因内禀属性，非扰动-读出对）
- **尝试回答的问题**：给定一个基因（及其可得的功能描述/网络位置等特征），它**是否为必需基因**
  （纯合/单倍体敲除即致死，无法产生存活的 haphom 敲除株）？
- **数据**：haphom vs het 两个 collection 的基因覆盖差集（源4，见
  [`data_sources.md`](data_sources.md)）——**已实测核实**：haphom 覆盖的 4,554 个基因**全部**是
  het 5,639 个基因的子集，het 比 haphom 多出的 **1,085 个基因**就是能直接圈出来的必需基因候选集
  （正例），4,554 个共有基因即非必需基因（负例）。
- **角色**：**这里没有扰动子/上下文/读出这套三元组**——跟 Task 1/2A/2B 的"扰动→效应"结构根本不同，
  是**单个基因的内禀属性分类**，不涉及任何扰动。这是本项目里第一个不属于"扰动-读出对"范式的任务，
  顶层数字用 3（不是"2C"）就是因为它不属于"2"这个"扰动-表型类读出"family，是一条全新的分类轴
  （单基因属性 vs 扰动-响应）。

#### 端到端技术规格（计划中的设计——尚未接入 pipeline，以下均为设计预期，非已验证结果）

> 现有 CLI（`prepare→retrieve→prompt`）是围绕`(pert, gene/context, context)`三元组设计的，这个
> 任务只有"一个基因"，**没有扰动子**，套用现有模板前需要先确认 CLI 能不能retrofit成单实体分类，
> 或者需要一套新的、更简单的模板（少一个实体，少一层）。

**1. Input（设计）**
- **单实体定义**：`(gene=待判断的ORF)`，不是三元组，只有一个实体。
- **生成方式（待设计）**：预期把该基因的一句话功能描述（`gene_desc.json`）、网络连接信息
  （`results_close_gene.json` 里的邻居数/中心性，STRING来源）拼成一段文本，喂给LLM——**这是全新
  模板**，不能直接复用`DE_template.py`/`DIR_template.py`（那些模板的核心是"扰动子对读出基因的
  因果影响"，这里没有因果链，是纯粹的"这个基因本身的性质判断"）。
- **待实现**：目前没有任何这类模板或对应的prompt生成脚本。

**2. Pipeline 看到的数据形式（设计）**
- 源头：`yp_matrix_haphom_20221025.txt`（4,554基因，非必需）+ `yp_het/yp_matrix_het_20221018.txt`
  （5,639基因，含必需）的基因ID差集——**已实测核实**（见上"数据"条），不是推断。
- 预期阈值化逻辑：`gene in het_only_1085` → label=1（必需候选）；`gene in haphom_4554` →
  label=0（非必需）。产出 `essentiality_labels.csv`（列预期 `gene,label,split`）——**待实现**。
- **需要注意的坑**：按基因切train/test（不能同一基因既在train又在test），且如果Input里用到的
  网络特征（STRING邻居）本身部分是从必需基因高连接度这个已知生物学规律反推出来的，要小心特征
  和标签之间是否存在人为的强相关（比如"高连接度→必需"这个规律如果被检索证据直接暴露给模型，
  可能让任务变得"太容易"，掩盖了真正的推理能力评测）。

**3. 推断（设计）**
- 预期判断逻辑：该基因是否编码保守的核心代谢酶/翻译-转录机器组分/结构性蛋白复合物必要亚基
  （必需性高）、还是冗余基因家族成员/条件特异功能/非核心通路旁支（必需性低）——这是全新的推理
  逻辑，不能照搬 Task 1 的 TF→靶逻辑或 Task 2A 的通路耐受逻辑，因为这里判断的不是"扰动的下游
  效应"而是"这个基因本身在细胞里有多不可替代"。
- **待实现**：具体脚手架文本待编写，目前没有对应的模板文件。

**4. Output（设计）**
- 预期闭集答案句形如 `"Non-essential. This gene is not essential for viability."` /
  `"Essential. This gene is essential for viability."` / insufficient-evidence 弃权句。
- **待确认**：这是根据其他任务模板的措辞风格推断出的预期格式，没有现成模板可核对。

**5. 评测口径（设计）**
- 预期复用 `src/eval/score.py` 同一套 answered%/Acc/macro-F1/MCC 框架，`--task` 需新增如
  `essentiality` 的分支——待实现。

**6. 怎么说明结果更好（设计）**
- 真实标签分布：1,085 必需候选 / 4,554 非必需 ≈ **19.2%/80.8%**（约1:4.2）——**已实测核实**，
  不算严重不均衡（不像T1a-DE的0.59%或T2B-DE的2.4%~7.15%那种数量级差距，具体取决于全基因组口径
  还是本地E-MAP子集口径，见Task 2B"6."），但也不是1:1，majority-class
  （猜非必需）accuracy 基线约80.8%，仍建议报 macro-F1/MCC 而非裸accuracy。
- **有外部benchmark可对照**：OGEE数据库（见下方引用）收录了酵母在内多物种的实验验证必需性标注，
  以及大量已发表的必需基因预测方法（多用序列/网络特征+经典机器学习，非LLM prompting），这些方法
  报告的性能可以作为"非LLM baseline"的参照对象，衡量LLM prompting相对传统特征工程方法的优劣。
- **这不是本项目自造的问题**：基因必需性预测是计算生物学里成熟、有专门benchmark数据库和大量方法论
  文献的真实问题——[OGEE: an online gene essentiality database](https://pubmed.ncbi.nlm.nih.gov/22075992/)
  收录多物种（含酵母）的实验验证必需性标注；综述见
  [Research on the Computational Prediction of Essential Genes, *Frontiers in Cell and
  Developmental Biology*](https://www.frontiersin.org/journals/cell-and-developmental-biology/articles/10.3389/fcell.2021.803608/full)。

**7. 已知的pipeline变体**
- **v1（baseline）**：即上面 1–6 项描述的这一整套（设计阶段，尚未接入 pipeline，见本任务小节
  标题）。
- **A/B prompt 分支**：暂无对应变体设计——全新的推理脚手架文本本身待写。
- **消融套件（Retrieval-only / w/o Biocontext / w/o CoT）**：暂无对应变体设计。

#### 生物学意义上的更细分解（按基因功能/保守性类别拆的候选子问题，非数据源层面的拆分；设计阶段）
- **该基因是否属于核心代谢/翻译-转录机器等"管家"功能类别，还是信号转导/结构类功能**：不同GO功能
  大类下必需性的判断依据不同——管家基因类的必需性更多来自"细胞持续运转缺不了"，信号转导类的必需性
  更多依赖具体条件/通路冗余程度，可按GO大类分层验证模型是否需要不同的推理侧重。
- **该基因是否同属一个已知蛋白复合物的必要亚基，还是孤立基因**：复合物内某些亚基的缺失会破坏整个
  复合物功能（必需性高度相关），可用CYC2008复合物数据库把基因分成"复合物内"和"孤立"两类，分别
  验证模型能否利用"复合物成员共必需性"这条捷径。
- **该基因是否有跨物种（人类/其他真核生物）的保守直系同源基因，还是酵母特异基因**：跨物种保守度
  是必需基因预测文献里公认的强特征之一（保守度越高、必需概率通常越高），可按是否有已知跨物种
  直系同源分层，测试模型能否利用/是否隐式利用了这条已知的机制线索。

---

## 二、可能的任务

> 排期状态不在这里说明——这里的任务全部是**未排期**；一旦排期，会移到"一、进行的任务"里按同样的
> 端到端技术规格细化。

### 过表达任务（Yeast ORF 过表达库）
- **尝试回答的问题**：过表达基因 `P` 是否导致基因 `G` 差异表达（DE）？方向如何（DIR）？
- **采用**：Sopko 2006 / MoBY-ORF / Douglas 2012 过表达文库——与 Task 1 的敲除方向互补（功能获得
  vs 功能缺失）。
- **可复用机制**：Task 1 同一套 YEASTRACT TF→靶符号推理理论上可镜像使用——过表达≈提高该 TF 的
  活性，方向逻辑与敲除相反（提高激活子活性→靶基因升，提高抑制子活性→靶基因降）。

### CRISPRi/dCas9 敲低库
- **尝试回答的问题**：剂量型敲低（非 0/1 完全敲除）对表达/表型的影响，是否存在剂量-响应关系。
- **采用**：CRISPRi/dCas9 敲低文库（具体数据源尚未确定）。
- **与现有任务的关键差异**：Task 1/2A 的扰动都是二元的（敲除=完全丧失），这里引入连续剂量维度，
  可能需要回归而不是当前的二分类框架，DE/DIR 的阈值化逻辑不能直接套用。

### 单细胞酵母读出
- **尝试回答的问题**：同 Task 1（扰动→表达），但读出改成单细胞分辨率，能否捕捉到细胞间异质性
  （群体平均掩盖掉的响应模式）。
- **采用**：Jackson 2020 / Nadal-Ribelles 2019 scRNA-seq 数据，形式上最贴近 VCWorld 原论文用的
  单细胞数据。
- **局限**：酵母单细胞数据本身稀疏，可能需要按细胞群pooling才能拿到可用信噪比。

### IDEA 时序动力学
- **尝试回答的问题**：TF 诱导后，读出基因的响应是 fast/slow、transient/sustained 里的哪一种模式
  （静态终点数据回答不了这个问题，只有时序数据能回答）。
- **采用**：IDEA 数据集（已下载核实，见 [`data_sources.md`](data_sources.md) 源2），可作 Task 1
  的第二个数据集（功能获得上下文，与 Deleteome 的功能缺失互补）。
- **知识泄漏风险**：YEASTRACT 的 TF→靶标注部分同源于类似的诱导实验数据，如果同时用 IDEA 做标签、
  又用 YEASTRACT 当检索证据，可能造成信息泄漏，需要先隔离两者的数据来源再接入。

### het/HIP（必需基因）作平行 T2 人群
- **尝试回答的问题**：必需基因（无法完全敲除，只能杂合缺失/haploinsufficiency）是否也表现出
  条件依赖的生长表型，与非必需基因（haphom 人群）相比是否有系统性差异。
- **采用**：Yeast Phenome 矩阵的 het collection（源4，与 haphom 互补，覆盖 haphom 测不了的必需
  基因，见 [`data_sources.md`](data_sources.md)）。

### 仅凭上下文(条件)本身能否一定程度上推断生长表型——T2A 的 context-only 基线
- **尝试回答的问题**：不看具体被敲的是哪个基因，只凭"这是哪个条件（药物/胁迫/浓度）"本身，能不能
  在一定程度上预测该条件下"大多数基因是否表现出生长表型"（T2A-DE 的 context-only 版本）？
  **⚠️ 已用真实数据核实——这个信号确实存在**：直接统计 `haphom_growth_phenotype.csv`
  （7,688 个有效条件，每条件≥5个基因观测）里每个条件的正例率，均值 0.629（62.9%）、标准差
  0.142，个别条件正例率低至0.0、高至1.0——说明"这个条件本身有多苛刻"携带着可观的预测信号，不是
  所有条件都均匀地在62.9%附近，纯粹"看条件不看基因"的简单基线在部分条件上就能大幅偏离全局多数类
  基线。
- **采用**：`haphom_growth_phenotype.csv`/`haphom_growth_direction.csv`（已有标签文件，见
  [`data_sources.md`](data_sources.md) 源4）+ `haphom_growth_contexts.csv`（条件元数据）+
  `condition_similarity.json`（条件相似度，`src/knowledge/build_condition_sim.py` 产出）——不需要
  接入新数据源，用现有 Task 2A 的标签文件重新聚合统计即可验证。
- **可复用机制 / 关键差异**：这不是给 LLM 推理任务本身提供的上下文特征（已删除的旧条目那个思路），
  而是一个**独立于模型的诊断性基线**——用"每条件的历史正例率"（或"每条件按 K 近邻相似条件插值"）
  直接预测，不经过任何 LLM 推理，作为衡量 T2A-DE/DIR 真实难度的下界参照：如果这个纯统计基线本身
  就能拿到不错的 macro-F1/MCC，说明 T2A 任务里有一部分信号来自"记住条件的苛刻程度"而非"理解扰动子
  的生物学机制"，评测时应该把这个 context-only 基线也列进 `RESULTS.md` 的对照基线里（跟
  Majority-class、YEASTRACT 符号规则并列），否则没法判断 LLM 推理相对这个廉价基线到底贡献了多少。

### Hughes 作跨实验室泛化测试集
- **尝试回答的问题**：在 Deleteome 上学到的 DE/DIR 推理模式，能否泛化到另一个实验室、另一批更早
  技术条件下测的独立数据。
- **采用**：Hughes compendium（已下载核实，见 [`data_sources.md`](data_sources.md) 源3）。
- **用途边界**：不新增任务类型，只作为 Task 1 的 hold-out 泛化评测。

