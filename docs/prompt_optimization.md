# Prompt 优化 — 针对酵母 DE/DIR 任务的两个 A/B 分支

两套可直接替换的 prompt 模板变体，用来跟当前 v1 baseline（`support/DE_template.py`、
`support/DIR_template.py`）做 A/B 对照。每个分支都是一整套 **DE + DIR** 模板，放在
`support/variants/` 下，通过现有 `prompt` 阶段的 `--template` 参数加载。

| 分支 | 路径 | 一句话思路 |
|---|---|---|
| **v1（baseline）** | `support/DE_template.py`、`support/DIR_template.py` | 当前 yeast 移植版，套用 VCWorld 的 5 步推理脚手架 |
| **A — 机制结构化** | `support/variants/A_mechanism/{DE,DIR}_template.py` | 把因果链显式化、可核查；强制 YEASTRACT TF 符号步骤 + 必须引用类比案例 |
| **B — 校准 / 强调 few-shot** | `support/variants/B_calibration/{DE,DIR}_template.py` | 把"是否DE / 方向哪边"当成**校准**问题；锚定在真实标注的同上下文 Examples 上；推理更精简、输出更紧凑、带置信度陈述 |

三者共用**同一套变量名**（`contexts`、`desc_pert`、`desc_gene`、`desc_context`、`desc_obs`、
`prompt_yeast_DE` / `prompt_yeast_DIR`、`choices_de` / `choices_dir`）和**同一套 `.format()`
字段**（`pert, gene, pert_desc, gene_desc, context_short, context_desc, obs`），所以任何变体都能
直接替换进 `prompt.py`。`[Start of Prompt]…[End of Prompt]` / `[Start of Input]…[End of Output]`
标记逐字节保留，`infer.py` 的正则才能正确解析每个代码块。**两个分支的最终闭集答案句都和 v1 一字不差
地保留**，所以给 v1 打分写的答案行解析器对 A、B 不用改就能用——两个分支的差异只在**推理脚手架**和
**输出代码块**，从不触及决策词表。

---

## 分支 A — 机制结构化

**假设**：v1 的 5 步脚手架规定得不够细——它*提到*了通路、TF 和类比案例，但没有强制模型真的落实
到具体的通路/TF，也没有强制它核查自己的推理链。如果每个论断都锚定在具名机制或已标注的类比案例上，
而不是靠名字相似度联想，准确率应该会上升。具体地，A 分支做了这些：

1. **显式框定酵母生物学假设**——敲除是**完全敲除**（100% 功能丧失，不是部分敲低）；读出的是新的
   **稳态**（所以反馈/去阻遏/补偿效应都要算进去）；**慢生长/环境应激响应(ESR)混杂因素**被单独点出来，
   它是DE的一个真实但非基因特异的成因，要和真正的基因特异效应区分开。
2. **强制一步 YEASTRACT TF 符号判断**——模型必须指出调控该读出基因的 TF，并显式填两个符号：
   （符号1）该 TF 对目标基因是激活子还是抑制子；（符号2）敲除会提高还是降低这个 TF 的活性。
3. **让 DIR 的推理逻辑清晰可核查**——因为敲除是**完全功能丧失**（不是药物激动剂/拮抗剂），
   YEASTRACT 的边符号能干净地推出方向。DIR 第3步先检查**直接边**（被敲除基因本身是不是调控该读出的
   TF？→敲除**激活子**⇒**下降**，敲除**抑制子**⇒**上升**），第4步给出完整的4行间接真值表（降低
   激活子→下降；降低抑制子→上升；升高激活子→上升；升高抑制子→下降），最后必须与同通路类比 Examples
   的真实方向做交叉核对（分歧时以同通路类比为准）。
4. **强制引用类比案例**——模型必须**按编号引用至少1个** Example，引用其真实的Result/方向，并说明
   这个案例是支持还是反对当前的推理链。"没有支持性 Example + 没有调控关系 = 证据薄弱"。
5. **编码去阻遏先验，并要求推理越过它**——Deleteome 的 DIR 标签中约**66%上升 / 34%下降**（敲除让
   靶基因去阻遏的情况比下调更常见），所以一个朴素的"永远猜上升"策略本身就能拿到66%的accuracy。
   A 分支把这个约2:1的先验只当作**真正模糊情形下的弱默认值**——并且因为评测用的是**macro-F1/MCC**
   而不是裸accuracy，明确要求模型在符号规则或最接近的类比案例支持时**敢于判下降**，而不是退回到
   多数类"上升"。抓住少数类"下降"正是macro-F1/MCC能不能赢的关键。

**代价**：prompt更长、期望的补全也更长（更多token）。最适合配更强的backbone
（Qwen2.5-14B），这样多出的结构才能被模型真正跟上。

---

## 分支 B — 校准 / 强调 few-shot

**假设**：模型看不到定义"什么算DE"的原始效应量或`|logFC|`/FDR阈值，所以"这是不是差异表达"这个
问题本质上是"这在**当前数据集**的阈值下过没过线"——是个校准问题，不是纯机制问题。上下文里唯一能
体现这个阈值在哪、这个数据集有多宽松的证据，就是同上下文里那些**真实标注的类比Examples**。所以B
让模型**锚定在Examples上**，机制推理只作为轻量调整/打破平局的手段。具体地，B做了这些：

1. **一开始就点明校准框架**——"你看不到效应量或阈值；已标注的同上下文Examples就是你的校准集；
   锚定在它们上面。"
2. **推理更精简**——3个短步骤而不是5个：
   - **DE**：（1）统计Examples基率+最近类比案例投票→先验；（2）简短的机制性上调/下调；
     （3）校准后的决策。
   - **DIR**：（1）Examples中的方向投票（上升 vs 下降）+最近类比案例的众数方向；（2）激活子/
     抑制子符号规则只作为**打破平局**的手段；（3）校准后的方向。
3. **输出更紧凑、更易解析**——输出代码块以显式的`Confidence:`（High/Medium/Low）和`Final:`
   行结尾，方便下游解析器抓取置信度信号（以后做Answered%/弃权/AUROC类分析时有用）以及确定性地
   抓取最终闭集答案句。
4. **冲突规则**——当类比案例的投票和机制推理不一致时，除非机制/符号规则给出的结论很确定，否则
   相信同上下文的Examples。这就是"校准到你能看见的数据"这句话的可操作化版本。
5. **DIR基率提示但不过度锚定**——B的DIR关键事实代码块同样陈述了约2:1的上升:下降类别先验，但把它
   框定为**弱打破平局手段**，只在最接近的同上下文类比案例投票分裂时才用；而且（因为评分用
   macro-F1/MCC）同样要求模型在符号规则指向下降时敢于判下降，而不是默认多数类上升。

**代价**：更便宜（token更少），但最依赖检索质量——它天然应该和"把**真实**训练标签接入
`retrieved_pairs`"这个修复（PLAN.md Part A.1 / Phase 3）搭配，因为它的整个前提就是Example标签是
真实的、有信息量的、同上下文的。

---

## A、B 与 v1 的区别（汇总）

| 维度 | v1 | A（机制） | B（校准） |
|---|---|---|---|
| 推理步数 | 5 | 5，更丰富+可核查 | 3 + Confidence/Final |
| 敲除性质框定 | 只在上下文散文里带过 | 显式的"完全敲除/新稳态"假设代码块 | 一个校准框架说明代码块 |
| TF符号步骤 | 叙述性("YEASTRACT风格") | 每个TF强制填2个符号 | 只作打破平局用 |
| DIR方向逻辑 | 2条要点规则 | 直接边规则+完整4行真值表+交叉核对+打破平局 | 先投票，符号规则打破平局 |
| DIR类别先验(~66%上升) | 未提及 | 陈述为弱默认值；**证据支持时敢判下降**(为macro-F1/MCC) | 陈述为弱打破平局手段；符号规则支持时敢判下降 |
| Examples的用法 | 引用(可选) | **按编号引用≥1个，说明是否支持** | **锚定/投票；Examples就是先验** |
| 输出 | 编号1–5 | 编号1–5 | 1–3 + `Confidence:` + `Final:` |
| 最终答案句 | 闭集 | **完全一致** | **完全一致** |
| Token开销 | 中等 | 更高 | 更低 |

其余部分（上下文轴、描述字段、证据代码块的构造方式）完全相同，所以任何准确率差异都能归因于
脚手架本身的改动。

---

## 怎么跑每个分支

这些变体是现有`prompt`阶段的直接替换项——只需要改`--template`。从`src/cli_pipeline`目录运行。
`--retrieval`指向`retrieve`阶段产出的检索JSON（或手工构造的，见下面"验证"部分）。

```bash
cd src/cli_pipeline

# ---- 分支A（机制结构化）----
python cli.py de  prompt --retrieval out/cond_DE_retrieval.json  \
  --template ../../support/variants/A_mechanism/DE_template.py   \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DE_prompts_A.txt
python cli.py dir prompt --retrieval out/cond_DIR_retrieval.json \
  --template ../../support/variants/A_mechanism/DIR_template.py  \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DIR_prompts_A.txt

# ---- 分支B（校准/强调few-shot）----
python cli.py de  prompt --retrieval out/cond_DE_retrieval.json  \
  --template ../../support/variants/B_calibration/DE_template.py \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DE_prompts_B.txt
python cli.py dir prompt --retrieval out/cond_DIR_retrieval.json \
  --template ../../support/variants/B_calibration/DIR_template.py \
  --gene-desc ../../data/knowledge/gene_desc.json --context-idx 0 \
  --out out/cond_DIR_prompts_B.txt

# ---- v1 baseline（默认模板；不传--template）----
python cli.py de  prompt --retrieval out/cond_DE_retrieval.json  --out out/cond_DE_prompts_v1.txt
python cli.py dir prompt --retrieval out/cond_DIR_retrieval.json --out out/cond_DIR_prompts_v1.txt
```

然后把每个`*_prompts_*.txt`喂给`de|dir infer --model … --prompts … --out …`
（Qwen2.5-14B为主力；7B/4B/Llama3.1-8B做规模消融），对最终答案行打分，在`RESULTS.md`里为每个
(任务, 模型, prompt版本)组合记一行（config列已经预留了`prompt_ver`槽位：`v1`/`A`/`B`）。

---

## 具体例子（真实渲染出的prompt，非手写模拟）

用同一个最小fixture（扰动`YEL009C`即GCN4，读出`YAL003W`即EFB1；检索到2条Examples：
`YEL009C→YKL109W`真实标签=DE、`YPL240C→YAL003W`真实标签=非DE）跑`generate_prompts`，实际渲染出
v1/A/B三套DE模板，摘录关键差异部分（Input部分三者完全相同，只贴一次；`[Start of Prompt]`部分
贴出能体现"5步 vs 3步"、"TF符号步骤有没有强制"、"类别先验怎么表述"这几处结构差异的段落，省略号
处表示模板本身用词大同小异、贴出来无新信息的部分）。

### 三套模板共享的 Input（真实渲染结果，一字不改）

```
[Start of Input]
- Description of deleted gene / perturbagen (YEL009C): GCN4, bZIP transcriptional activator of amino acid biosynthetic genes; master regulator of general amino acid control.
- Description of readout ORF of interest (YAL003W): EFB1, translation elongation factor 1 beta.
- Context: Single-gene deletion in Saccharomyces cerevisiae (BY4741 background), synthetic complete (SC) medium, log phase; steady-state genome-wide expression measured by two-colour microarray versus an isogenic wild-type reference. This is a loss-of-function (null) perturbation: the reading is the new transcriptional steady state a cell reaches once the gene's product is absent. Many deletions also slow growth, which superimposes a non-specific environmental-stress / slow-growth expression signature on top of the gene-specific response; weigh specificity accordingly.
- Examples: Example 1:
- Perturbagen (deletion): YEL009C
- Readout gene (ORF): YKL109W
- Perturbagen Description: GCN4, bZIP transcriptional activator of amino acid biosynthetic genes; master regulator of general amino acid control.
- Readout Gene Description: HAP4, transcriptional activator of CCAAT-binding complex controlling respiratory gene expression.
- Result: B) Deletion of this gene results in differential expression of the readout gene.

Example 2:
- Perturbagen (deletion): YPL240C
- Readout gene (ORF): YAL003W
- Perturbagen Description: HSP82, Hsp90 chaperone.
- Readout Gene Description: EFB1, translation elongation factor 1 beta.
- Result: A) Deletion of this gene does not differentially express the readout gene.
[End of Input]
```

（`Examples`里的`Result`是检索到的**真实train标签**映射出的句子，不是随机的——这正是本文档开头
说的"两个分支都继承v1这个已修好的行为"。）

### v1 baseline —— 5步，TF符号只在叙述里带过

```
1) **Function & Analogue Identification:**
   State the molecular function of the deleted gene YEL009C (pathway, complex, biological process).
   From the evidence set, identify analogue deletions that act in the *same pathway or complex* as
   YEL009C, and note whether the readout ORF YAL003W is a known co-functional / network neighbour.
...
3) **Downstream Cascade Simulation (pathways & transcription factors):**
   Trace the regulatory cascade from the deletion. Loss of YEL009C perturbs its pathway, which
   changes the activity of specific transcription factors (TFs). Using YEASTRACT-style TF -> target
   logic, name the candidate TF(s) that regulate YAL003W and whether the deletion would raise or
   lower their activity.
4) **Causal Bridge & Evidence Synthesis:**
   Construct the explicit causal chain: deletion of YEL009C -> affected pathway -> transcription
   factor(s) -> target ORF YAL003W. Cite specific analogue cases from the evidence set (matching the
   deletion's true result) that support (or bound) this link.
5) **Final Deterministic Prediction:** ...
```

TF符号步骤是一句话带过（"name the candidate TF(s) ... and whether the deletion would raise or
lower their activity"），没有强制模型显式写出"激活子/抑制子"这两个符号，也没有强制引用Example编号。

### 分支A（机制结构化）—— 同样5步，但TF符号被拆成强制的两问、且要求按编号引用

```
Modeling assumptions you MUST hold:
- A deletion is a COMPLETE null: 100% loss of function of YEL009C's product, not a partial
  knock-down. Reason about what is fully absent, and about anything that becomes de-repressed or
  compensated once it is gone.
- The readout is a new STEADY STATE versus isogenic wild-type, so account for feedback and
  secondary adaptation, not just the immediate primary effect.
- Deleting YEL009C may slow growth; a slow-growth / environmental-stress-response (ESR) signature
  is a real but NON-SPECIFIC cause of DE. Keep it separate from a gene-specific, pathway-directed
  effect.
...
3) **Regulatory Cascade & TF Sign Step (YEASTRACT logic):**
   Trace the cascade from the null: loss of YEL009C -> altered pathway activity -> changed activity
   of specific transcription factor(s) (TFs) that regulate YAL003W. Name the candidate TF(s)
   governing YAL003W. For EACH, state (a) whether it is an ACTIVATOR or a REPRESSOR of YAL003W, and
   (b) whether deleting YEL009C RAISES or LOWERS that TF's activity. ...
4) **Causal Bridge & Mandatory Evidence Citation:**
   Write the explicit chain as text: deletion of YEL009C -> affected pathway -> transcription
   factor(s) -> readout ORF YAL003W. Then CITE at least one specific analogue by its Example number,
   quote its true Result, and state whether it SUPPORTS or ARGUES AGAINST a link here. If the
   closest analogues were NOT differentially expressed, treat that as evidence for "No". A chain
   with no supporting Example and no known regulatory link is weak evidence.
```

对比v1第3步能看出真实差异：A把"raise or lower their activity"拆成了`(a)`/`(b)`两个必须分别填写的
子问题，第4步还多了"CITE at least one specific analogue by its Example number"这句硬性要求——
v1里对应的只是"Cite specific analogue cases"，没有"必须按编号"这个约束。

### 分支B（校准/few-shot为中心）—— 3步+Confidence+Final，先投票再考虑机制

```
Key fact about this task -- read carefully:
- You CANNOT see effect sizes, fold-changes, or the exact statistical cutoff that defines a DE hit.
  "Differentially expressed" means "the change clears this dataset's threshold".
- The Examples are TRUE-LABELLED observations from the SAME context. They are your calibration set:
  they reveal how permissive the threshold is here and how deletions like YEL009C tend to behave on
  readouts like YAL003W. ANCHOR on them. Use mechanism only to nudge off that anchor, not to
  override a clear analogue signal.
...
1) **Calibrate from the Examples:**
   Tally the Examples by their true Result -- how many were differentially expressed vs not. State
   that base rate in one phrase (mostly-DE / mixed / mostly-not). Then pick the 1-3 CLOSEST
   analogues (same pathway/complex as YEL009C, or the same/similar readout as YAL003W) and report
   what they did. This closest-analogue vote is your prior.
2) **Mechanistic adjustment (brief):**
   In 1-3 sentences: does YEL009C's known biology push YAL003W ABOVE the threshold ... or leave it
   BELOW ...? Adjust the step-1 prior up or down accordingly.
3) **Calibrated decision:**
   Combine the analogue vote (step 1) with the adjustment (step 2). If they conflict, trust the
   same-context Examples unless mechanism is decisive.

Confidence: state High, Medium, or Low, based on how consistent the closest analogues were and how
clear the mechanism is.
```

B第1步"Tally the Examples by their true Result"是v1/A都没有的动作——先统计Examples里几条是DE、
几条不是，当成先验，再用第2步的机制推理去微调，跟A"先机制、后引用核对"的顺序正好相反。

三者的`[Start of Output]`/`[End of Output]`骨架也不同（真实渲染结果）：v1和A都是`1) 2) 3) 4) 5)`
五个空位，B是`1) 2) 3)` + `Confidence:` + `Final:`。

---

## 验证（已完成，不需要跑LLM）

在一个2条样例的最小检索fixture（`test_case` = `YEL009C`(GCN4)→`YAL003W`(EFB1) 和
`YPL240C`(HSP82)→`YFL039C`(ACT1)，带真实标注的`retrieved_pairs`）上，通过真实的
`stages/prompt.py:generate_prompts`加载器 + `data/knowledge/gene_desc.json`，渲染了全部六套模板
（v1/A/B × DE/DIR）。对每个渲染出的代码块检查：`[Start of Prompt]/[End of Prompt]`和
`[Start of Input]/[End of Output]`标记精确存在，`infer.py`的两个提取正则都能匹配，真实的SGD描述
和真实标注的Examples都正确填入，且**零**残留的`{…}`格式占位符（f-string没有出现NameError/
KeyError）。两个分支的解析结果和v1完全一致。

```
render_v1_de/dir            blocks=2  markers OK  placeholders OK
render_A_mechanism_de/dir   blocks=2  markers OK  placeholders OK
render_B_calibration_de/dir blocks=2  markers OK  placeholders OK
```

---

## A/B 分支结果（2026-07-23，真实LLM跑分）

**Setting**：Qwen2.5-14B，A/B两个分支各自在T1a-DE/T1b-DIR/T2A-DE/T2A-DIR四个任务的完整test集上
跑满3个seed（0/1/2，vLLM推理，14路并行分片），跟主矩阵v1一样用`compute_metrics()`统一评分口径，
mean±stdev（pstdev，n=3）。数字来自`data/ab/agg_ab.json`（`src/eval/ab_score.py`产出）。

| 任务 | 分支 | Macro-F1± | MCC± | Acc/方向Acc± | Answered% |
|---|---|---|---|---|---|
| T1a-DE | v1（主矩阵） | .680±.001 | .359±.002 | .622±.002 | 74.2% |
| T1a-DE | A（机制结构化） | .648±.001 | .297±.002 | .623±.001 | 75.0±0.1% |
| T1a-DE | B（校准/few-shot） | .674±.001 | .355±.003 | .847±.001 | 99.9±0.0% |
| T1b-DIR | v1（主矩阵） | .683±.001 | .372±.002 | .657±.000 | 93.0% |
| T1b-DIR | A（机制结构化） | .604±.001 | .250±.003 | .608±.001 | 99.1±0.0% |
| T1b-DIR | B（校准/few-shot） | .675±.001 | .358±.002 | .719±.001 | 99.1±0.1% |
| T2A-DE | v1（主矩阵） | .615±.002 | .245±.002 | .465±.002 | 61.9% |
| T2A-DE | A（机制结构化） | .627±.003 | .257±.005 | .391±.003 | 56.2±0.2% |
| T2A-DE | B（校准/few-shot） | .622±.002 | .245±.004 | .678±.001 | 98.3±0.1% |
| T2A-DIR | v1（主矩阵） | .469±.001 | .100±.003 | .741±.001 | 98.8% |
| T2A-DIR | A（机制结构化） | .542±.001 | .190±.003 | .737±.001 | 97.2±0.1% |
| T2A-DIR | B（校准/few-shot） | .625±.001 | .264±.003 | .739±.003 | 98.8±0.1% |

**Analysis**：两个分支呈现明显不同的效果模式，不是"哪个分支全面更好"这种简单结论。**分支B（校准/
先投票再推理）的主要作用是把Answered%顶到接近100%**（T1a-DE从v1的74.2%跳到99.9%，T2A-DE从61.9%
跳到98.3%），代价是Macro-F1/MCC基本持平或小幅低于v1（T1a-DE .674/.355 vs .680/.359，T1b-DIR
.675/.358 vs .683/.372），说明"先投票再考虑机制"这个脚手架让模型更容易给出可解析的确定答案，
但没有实质提升判别力；唯一的例外是T2A-DIR，B分支MCC从v1的.100涨到.264，同时Answered%持平
（98.8%），是这组数据里唯一"分数+可答率都改善"的组合。**分支A（机制结构化/强制引用）在T1的两个
任务上明显更差**（T1a-DE Macro-F1 .648 vs v1 .680、MCC .297 vs .359；T1b-DIR .604 vs .683、
.250 vs .372）——强制模型按编号引用Examples、拆两问的TF符号推理，在Deleteome这个转录读出任务上
似乎干扰了判别而非帮助；但在**T2A两个任务上A分支反而好于v1**（T2A-DE MCC .257 vs .245；T2A-DIR
Macro-F1 .542/MCC .190，明显超过v1的.469/.100），提示"机制强制"这套脚手架跟读出层的匹配度不是
单调的——在生长表型任务上，被强制说清楚扰动子-通路机制这件事本身可能比在转录任务上更有信息量。
**总体结论**：A/B分支消融证实了"prompt脚手架的组织方式确实影响分数"，但方向依赖于（分支×任务）
组合，不存在一个在四个任务上都全面超过v1的分支，因此当前主矩阵仍以v1为准，A/B作为消融附录保留。

---

## 消融C/D结果（2026-07-24，真实LLM跑分：w/o Biocontext 与 w/o CoT）

**Setting**：Qwen2.5-14B，标准消融套件里的两条（`消融2 w/o Biocontext`、`消融3 w/o CoT`）在
T1a-DE/T1b-DIR/T2A-DE/T2A-DIR四个任务上跑满3个seed（0/1/2，vLLM推理，14路并行分片：8s-06全8卡+
8s-01高位6卡，8s-01的GPU0/1按约定留空）。分支C（w/o Biocontext）通过把`--gene-desc`/`--pert-desc`
指向一个空JSON（`data/ab/_empty_desc.json`）实现"描述查不到"，模板见
`support/variants/C_no_biocontext/`；分支D（w/o CoT）保留完整背景描述，只是把输出要求从"5步/4步
编号推理+最终答案"压缩成"只要最终答案句，不要中间推理"，模板见`support/variants/D_no_cot/`。数字
来自`data/ab/agg_ab_cd.json`（`python src/eval/ab_score.py --branches C D --out agg_ab_cd.json`）。

| 任务 | 分支 | Macro-F1± | MCC± | Acc/方向Acc± | Answered% |
|---|---|---|---|---|---|
| T1a-DE | v1（主矩阵） | .680±.001 | .359±.002 | .622±.002 | 74.2% |
| T1a-DE | C（w/o Biocontext） | **.808±.001** | **.617±.003** | .200±.003 | **22.0±0.3%** |
| T1a-DE | D（w/o CoT） | .702±.003 | .426±.005 | .586±.009 | 67.1±0.8% |
| T1b-DIR | v1（主矩阵） | .683±.001 | .372±.002 | .657±.000 | 93.0% |
| T1b-DIR | C（w/o Biocontext） | **.748±.004** | **.496±.007** | .509±.004 | **64.5±0.5%** |
| T1b-DIR | D（w/o CoT） | .687±.004 | .409±.003 | .600±.004 | 85.9±0.4% |
| T2A-DE | v1（主矩阵） | .615±.002 | .245±.002 | .465±.002 | 61.9% |
| T2A-DE | C（w/o Biocontext） | .545±.007 | .165±.013 | .077±.002 | **8.9±0.3%** |
| T2A-DE | D（w/o CoT） | .614±.002 | .237±.002 | .445±.001 | 59.4±0.1% |
| T2A-DIR | v1（主矩阵） | .469±.001 | .100±.003 | .741±.001 | 98.8% |
| T2A-DIR | C（w/o Biocontext） | .632±.003 | .290±.003 | .678±.004 | 88.3±0.3% |
| T2A-DIR | D（w/o CoT） | .518±.006 | .160±.013 | .738±.003 | 97.7±0.1% |

**Analysis**：两条消融各自揭示了不同的机制，都不是"简单地变差"这种预期中的负结果。

**消融2（w/o Biocontext）—— Answered%大幅崩塌，但答的那部分反而更准，是明显的"选择性作答"
效应**：T1a-DE的Answered%从v1的74.2%骤降到22.0%，T2A-DE从61.9%骤降到8.9%——去掉背景描述后模型
绝大多数case都回答"insufficient evidence"，只在极少数case上敢下判断。但恰恰是这敢下判断的
一小撮case，Macro-F1/MCC反而**明显超过v1**（T1a-DE MCC .617 vs .359，逼近翻倍；T1b-DIR MCC
.496 vs .372）。这不是"没有背景描述反而学得更好"，而是一个**样本选择偏差**：没有功能描述可用时，
模型只在Examples里的true-label分布极度一边倒（比如检索到的10个类比案例9个以上是同一个标签）
的case上才敢下判断，这类case本身就是"好猜"的case，回答的正确率自然高；而背景描述存在时，模型
会尝试对更多、更难的case给出判断（Answered%高得多），代价是这部分较难case拉低了整体
Macro-F1/MCC。**这本身是对"背景知识描述的作用"一个有意义的间接验证**：背景描述的价值主要不是
"让答案更准"，而是"让模型敢于对更多困难case给出判断"——去掉描述后模型退化为只在最明显的案例上
表态，其余大量案例弃权。T2A-DIR是部分例外：Answered%仍明显下降（98.8%→88.3%），但MCC不降反升
（.100→.290），说明T2A-DIR上背景描述（yeastphenome compendium的assay说明）本身信息量有限，
真正驱动判断的可能主要是Examples本身，去掉描述反而减少了一些干扰。

**消融3（w/o CoT）—— 去掉多步推理脚手架，四个任务的Macro-F1/MCC都没有下降，反而普遍小幅上升**：
T1a-DE（.702/.426 vs v1 .680/.359）、T1b-DIR（.687/.409 vs .683/.372）、T2A-DIR（.518/.160 vs
.469/.100）都是D分支略高，T2A-DE基本打平（.614/.237 vs .615/.245）。Answered%在T1的两个任务上
有所下降（T1a-DE 67.1% vs 74.2%，T1b-DIR 85.9% vs 93.0%），T2A两个任务基本持平。**这是一个对
"链式推理有多重要"的诚实负结果**：要求模型显式写出5步/4步中间推理，并没有让最终判断更准——四个
任务上直接给最终答案的版本，判别力至少不差、部分还更好。这支持"模型的判断力主要来自看到
Examples/背景描述后的直觉性模式匹配，多步推理脚手架更多是让输出看起来像在做机制推理，而非真的在
提升决策质量"这个消融3开头提出的假设方向。**跟消融2放在一起看**：背景描述（消融2去掉的东西）的
缺失会显著影响模型"敢不敢回答"，但推理步骤（消融3去掉的东西）的缺失几乎不影响"回答得对不对"——
两者在这套白盒框架里扮演的角色并不对称，背景知识是真正驱动判断的输入，多步推理更像是呈现层的
脚手架。

---

## 标准基线 + 消融套件（跨任务通用方法论）

**这不是某个任务专属的一次性补充实验，是每个任务（T1/T2A/T2B，DE 和 DIR 各自）都该配齐的一套
标准对照**。上面 A/B 两个分支是"能不能把 v1 prompt 改得更好"这个优化问题；这里的四行是另一个
正交的问题——**"v1（或任意分支）里的每一块设计，各自真的在起作用吗？"**——用控制变量的方式，
每次只拆掉一块，看分数掉多少。四行分两类：

- **两条零推理弱基线**（Random、Majority）——不调用 LLM，用来标出"及格线"在哪；
- **三条消融变体**（Retrieval-only、w/o Biocontext、w/o CoT）——需要真实调用 LLM，各自拆掉 v1
  五步脚手架里的一个成分，看 Macro-F1/MCC 掉多少，用来回答"模型的高分究竟是从哪个环节来的"。

设计原则统一、跨任务通用；每个任务落地时具体怎么改模板会有差异（比如 T1 的 5 步脚手架和 T2A 的
4 步脚手架，"去掉 CoT"字面上删的步骤数不一样），下面每条先讲通用设计原则，再点出各任务落地时的
已知差异。

### Random 基线（零推理，跟 Majority 是两种不同的弱基线）

**定义**：对每个 test case，独立地从该任务的闭集类别（DE/DIR 系列任务都是二分类：DE 的
Yes/No、DIR 的 Increase/Decrease、T2A 的 phenotype/no-phenotype 与 Sensitive/Resistant、T2B 的
GI/non-GI 与 Positive/Negative）里均匀随机选一个，不依赖任何输入（不看 pert/gene/context，不看
Examples，也不像 Majority 那样利用训练集的类别先验）。

**跟 Majority 的区别，为什么两个都要留**：Majority 是"永远猜固定的多数类"——它隐式利用了"我知道
这个数据集哪个类更常见"这条信息，所以在类别不均衡的任务上裸 Acc 会很高（比如 T1a-DE 84.6%）；
Random 是"完全不看数据分布、均匀瞎猜"，Acc(overall) 恒为 0.5（不管真实类别比例是多少），
macro-F1 会随不均衡程度系统性走低（越不均衡，随机猜中少数类的机会越亏，宏平均被拉低）。两者
合在一起才是一对完整的"下限"参照：**模型必须同时明显超过 Random 的 macro-F1/MCC（证明它真的
在利用输入信息，而不是抛硬币）和明显超过 Majority 的 macro-F1/MCC（证明它没有退化成"总是猜
多数类"这种偷懒策略）**——单独看任何一个都可能被误导（比如一个只会瞎猜的模型也能"偶然"跑赢
Majority 的裸 Acc 附近的数字，但绝不可能系统性跑赢 Random 的 macro-F1；反过来一个退化成"永远
猜多数类"的模型 macro-F1 会卡在 Majority 那一行附近，跑不赢真正学到边界的模型，但 Random 基线
本身看不出这种退化）。

**怎么算**：解析闭式下 Acc(overall) 恒为 0.5（均匀硬币不管真实标签怎么分布，猜对概率都是
1/2），但 macro-F1/MCC 是 (tp,tn,fp,fn) 的非线性函数，不能只背解析式——`src/eval/baselines.py`
的 `random_baseline()`/`summarize_random_trials()` 对每个任务的真实测试集标签向量做 200 次独立
的均匀随机标签抽样（固定 `seed=0`，可复现），每次都用和给 LLM 打分完全同一套
`score.compute_metrics()` 计分，报 200 次抽样的 mean±stdev——用蒙特卡洛而不是纯解析式，既能拿到
macro-F1/MCC 的真实数字，也顺带用抽样均值验证了 Acc=0.5 这条解析结论。真实数字见
[`task_results.md`](task_results.md) 各表。

### 消融 1 — Retrieval-only（去掉 LLM 机制推理，只用检索证据做最近邻式预测）

**假设**：v1（及 A/B）prompt 里同时喂了两类信息——检索到的 Examples（真实标注的类比案例）和
"要求模型走一遍多步机制推理"这个脚手架。如果不要 LLM 做任何推理，单纯统计检索到的 Examples 里
label 的多数（或按相似度加权投票），预测效果如果已经跟完整 pipeline 差不多，说明整套机制推理
脚手架对最终分数的边际贡献很小——真正在起作用的是检索证据本身，LLM 只是在做"看起来像推理"的
包装。

**怎么改**：**不改 prompt 模板，改 pipeline**——跳过 `infer` 阶段（不调用 LLM），直接在
`retrieve` 阶段产出的 `retrieval.json`（`retrieved_pairs=[[pert,gene,label],...]`）上做一个纯
规则的最近邻分类器：对每个 test case，统计其 `retrieved_pairs` 里 label 的众数（或用检索排序
做加权投票，如果检索阶段本身带相似度分数），众数就是预测；`retrieved_pairs` 为空时按该任务的
Majority 类回退（避免退化成随机瞎猜，这样才是跟"LLM+检索"公平的对照——差异只在"要不要用 LLM
推理"这一个变量，其余（检索到的证据集合本身）保持不变）。跟 A/B 分支不同，这一个变体**根本不
经过任何 prompt 模板/LLM 调用**，是纯本地脚本，实现成本比 A/B 都低，但因为需要先确认"哪种投票
/加权方式最贴近 LLM 实际读 Examples 的方式"才算公平对照，仍归为"需要实现验证"的待办项，不在本次
范围内直接编数字。

**跨任务差异**：T1/T2A/T2B 的 `retrieved_pairs` 结构完全一致（都是三元组+真实 label），所以这个
消融的实现方式在三个任务间不需要改代码逻辑，只要换 `retrieval.json` 的输入文件。

### 消融 2 — w/o Biocontext（去掉生物学背景描述，只留裸 ID + Examples）

**假设**：v1 prompt 里 `pert`/`gene`（或 T2A 的 `context`）各自的一句话功能描述、以及那段写死的
数据集/assay 上下文散文，理论上是让模型"用生物学知识做推理"的关键输入。如果去掉这些描述、只留
裸的基因系统名（如 `YEL009C`）+ Examples，模型分数如果掉得不多，说明模型主要是在做**基于 ID/
Examples 表面模式的匹配**（比如"这个基因系统名前几个字符跟 Examples 里出现过的类似"这种伪相关），
而不是真的在调用生物学背景知识做机制推理；如果掉得多，则是"确实用到了背景知识"这一论点的直接
证据。

**怎么改（改模板）**：在 `prompt` 阶段渲染时，把 `pert_desc`/`gene_desc`（T2A 是
`context_desc`）字段替换成空字符串或者最小占位（比如只留 ORF 系统名本身，不接 `gene_desc.json`
查出来的功能描述），同时删掉模板里那一段写死的上下文散文（BY4741/SC培养基/log期这类，T2A 是
yeastphenome compendium 那段）。Examples 代码块**保留**（这是这个消融和"消融1 Retrieval-only"的
关键区别——消融1去掉的是推理步骤，留着证据；这里去掉的是背景知识，留着证据和推理脚手架，只是
脚手架现在没有生物学描述可用，只能靠基因系统名本身和 Examples 里的真实 label 做推理）。推理
脚手架的步数/结构本身不变（仍是 T1 的 5 步、T2A 的 4 步……），只是第1步"说明被敲基因的功能/通路"
这类要求会因为没有描述可用而退化成"你只有系统名 `{pert}`，没有功能描述，请基于 Examples 里的
模式作答"这种明确告知模型信息缺失的提示，避免模型自己编造不存在的功能描述（幻觉）。

**跨任务差异**：T1 的 `desc_pert`/`desc_gene`、T2A 的 `desc_pert`/`desc_context`、T2B（设计中）
预期的 `desc_pertA`/`desc_pertB` 都是同一种"从知识资产 JSON 查出来的一句话描述"，去掉的做法一致；
T1 额外有一段"完全敲除/新稳态/ESR混杂"的生物学假设散文（分支A里显式化的那部分），T2A 额外有一段
assay/compendium 散文，两者都要一并去掉，不能只删字段描述、留着上下文散文。

### 消融 3 — w/o CoT（去掉多步推理脚手架，直接给最终答案）

**假设**：v1（及 A/B）都要求模型先写出多步中间推理（"Function & Analogue Identification"…
"Causal Bridge & Evidence Synthesis"…）才给出最终闭集答案句。如果跳过这些中间步骤、直接让模型
看到 Input 后立刻给出 Final 答案句，分数如果掉得不多，说明链式推理本身对准确率的边际贡献有限，
模型的判断力主要来自看到 Examples/描述后的"直觉"，中间步骤更多是让输出"看起来像在推理"，不是
真的在提升决策质量。

**怎么改（改模板）**：`[Start of Output]`/`[End of Output]` 代码块从"编号 1)…N) 中间推理步骤 +
Final 答案句"压缩成只要求 Final 答案句本身（不要求写出任何编号步骤或推理过程），`[Start of
Prompt]` 部分的指令也相应改成"直接给出最终判断，不需要写出中间推理"。最终答案句词表**不变**
（跟 v1/A/B 一样一字不差，这样打分器不用改），改动只在"要不要求模型显式写出中间推理"这一个
变量上。

**跨任务差异（去掉的具体步骤数不同）**：
- **T1**（DE/DIR 各 5 步）：去掉全部 5 步（Function & Analogue Identification / Specificity &
  Relevance Analysis / Downstream Cascade Simulation / Causal Bridge & Evidence Synthesis /
  Final Deterministic Prediction 中的前 4 步），只保留第 5 步产出的最终答案句。
- **T2A**（DE/DIR 各 4 步，比 T1 少一步）：去掉前 3 步（Function of pert / Relevance to the
  condition 或 Direction logic / Analogue check），只保留第 4 步 Final call。
- **T2B**（设计阶段，预期沿用 T1 的 5 步 DIR 脚手架结构 + 独立的 DE 关联强度判断步骤，见
  [`task_definitions.md`](task_definitions.md) Task 2B "3. 推断（设计）"）：一旦脚手架文本落地，
  同样去掉除最终判断外的全部中间步骤，具体步数以届时定稿的模板为准。

三个任务的"设计原则"完全一致——**去掉的是"要求模型写出中间推理"这件事本身，不是某个特定步骤的
内容**，落地时只是每个任务脚手架的步数不同，删的行数不同。

### 变体 4 — 训练型传统ML对照（同一 train/test split 上训练的轻量分类器，不是消融，是独立对照方法）

**为什么加这一条**：这条不是"拆掉v1的某个部件"，是一个**独立的、需要训练的传统方法**，跟上面三条
消融性质不同，之所以纳入同一套标准套件，是因为VCWorld本身的真实审稿记录（ICLR 2026，
`openreview.net/forum?id=hhq89Hs7T3`）给出了明确先例：**没有一个审稿人质疑"训练型模型和zero-shot
LLM放在同一张表比不公平"**，真正被反复追问的是"是不是在同一个train/test split、同一个benchmark
上比"（reviewer Vroo专门追问"STATE是不是真的只用了5个细胞系训练"，作者的回应就是确认split对齐）。
VCWorld自己就用这个逻辑加了一个**自建GAT baseline**（融合知识图谱训练的图注意力网络，在同样的
30/70 split上训练），这是回应"到底是图结构本身在起作用还是LLM推理加了价值"这个质疑的关键证据
之一，且被审稿人认可。CPA/GEARS/scGen这类需要海量单细胞训练数据的重模型依然不现实（酵母没有
对应规模的数据，见本文档更早的调研结论），但**轻量的、用本项目已有特征训练的传统分类器**是可行
且性价比高的。

**假设**：如果一个不做检索、不做LLM推理、只用**已有的结构化特征**（比如STRING跳数、TF签名状态、
ESR基因集合成员身份、蛋白复合物共属关系——这些在Task 1"生物学意义上的更细分解"分析里已经落地
成真实特征）训练出的简单分类器（逻辑回归/随机森林），在**同一个train/test split**上就能拿到跟
LLM相近的分数，说明LLM推理相对"把已知网络特征喂给传统ML"这件事，边际贡献有限；如果传统分类器
明显打不过LLM，则是"LLM推理确实在做传统特征工程做不到的事"这个论点的有力支撑。

**怎么构造（设计，尚未实现）**：
- 特征来源：直接复用已有的知识资产——`tf_targets.json`(TF签名状态)、`results_close_gene.json`
  (STRING跳数/邻居数)、`esr_genes_gasch2000.json`(ESR成员)、`complex_members_complexportal.json`
  (复合物共属)——不需要额外爬取新数据。
- 训练/测试切分：**必须和LLM评测用的完全同一个split**（同一份`train`/`test`标签，不能另切），
  这是VCWorld审稿记录里被明确要求的"统一平台"底线。
- 模型：逻辑回归或随机森林起步（不追求SOTA，只是"传统ML能从这些特征里榨出多少信号"的参照点）。
- 跨任务落地：T1（DE/DIR）特征最丰富，最适合先做；T2A/T2B/T3 需要各自盘点已有的结构化特征是否
  够训一个简单分类器（比如T3的必需性预测本身就带着"网络连接度"这类天然适合传统ML的特征，见
  [`task_definitions.md`](task_definitions.md) Task 3"6.怎么说明结果更好"提到的Gustafson et al.
  经典网络拓扑基线，AUC=0.77-0.81，这条本质上就是"传统ML训练型baseline"在酵母必需性预测上的
  历史先例，可以作为我们自己训练这条baseline时的参照/校验点）。

**跟消融1(Retrieval-only)的区别**：Retrieval-only是"不训练、用检索到的几个近邻案例做投票"，
是zero-shot范式内部的消融；这条变体4是"真的训练一个模型"，是完全独立于zero-shot范式之外的对照
方法，两者回答的问题不同（前者问"检索证据本身够不够"，后者问"传统ML训练范式够不够，LLM推理是否
比它更好"）。

**架构清单（近5年文献调研，每个任务规划4个，不是挑1个赢家淘汰其余3个——4个都作为独立对照方法，
分别产出各自的Macro-F1/MCC，一起放进`task_results.md`同一组变体4行里）**：

**T1（DE/DIR）的4个**：

- **GAT**（直接对标VCWorld自建baseline先例）
  - 一句话：PPI/知识图谱节点特征 + GAT，在同一个train/test split上训练一个分类头。
  - 任务对应：直接对应 T1a-DE/T1b-DIR（VCWorld原论文自己解决的就是同款DE/DIR分类任务）。
  - 依据：VCWorld论文本身就是这么做的，且被审稿人认可，见上文"为什么加这一条"。特征来源、
    构造方式见下方"怎么构造"。实现：`src/eval/gat_baseline.py`。
  - 引用：Wei et al., ICLR 2026 (arXiv:2512.00306) Appendix B.2。

- **GenKI**
  - 一句话：VGAE（变分图自编码器），只用野生型表达数据 + 推导出的GRN，预测某基因敲除后哪些基因
    会响应；在单一数据集的GRN上直接训练，不需要外部大规模预训练。
  - 任务对应：任务形式就是DE预测（敲除→哪些基因响应），跟T1a-DE几乎一致。
  - 实现要点：比GAT分类头复杂——需要"虚拟敲除节点后看重建变化"这套encoder-decoder机制。
  - 引用：Yang et al. 2023, *Nucleic Acids Research* 51(13):6578-6592。

- **KGE-TGI**
  - 一句话：Multi-subgraph GCN（按关系类型切分异构KG分别卷积），做TF-靶基因关系存在性+方向
    （activation/repression）联合分类，直接在整合好的知识图谱上训练。
  - 任务对应：任务形式=方向分类，几乎跟T1b-DIR一一对应。
  - 实现要点：原论文用的是人类TRRUST数据库（更干净的、人工curator标注过的调控关系），我们移植时
    图结构要换成YEASTRACT，酵母数据密度/标注质量不如TRRUST，预期性能需要单独校准。
  - 引用：Wu et al. 2023, *PLOS Computational Biology* 19(6):e1011207。

- **MultiXrank（RWR + 监督分类器）**
  - 一句话：Random Walk with Restart在网络上跑出的邻近度分数当特征，训练XGBoost/随机森林做关联
    预测——是对老牌guilt-by-association方法（比如McGary et al. 2007）的2024年监督式升级版。
  - 任务对应：网络传播算邻近度 + 轻量分类器两段式，跟T1的TF-target网络结构直接适配。
  - 实现要点：原论文验证的是gene-disease关联，迁移到TF-target需要重新定义"邻近度"在这个图里
    怎么算。
  - 引用：Baptista, Brière, Baudot 2024, *BMC Bioinformatics* 25:70。

**T2A（DE/DIR）的4个**：

- **矩阵分解 NRBdMF/SRMF**
  - 一句话：邻域正则化矩阵分解，专为"基因×化合物"这类稀疏矩阵设计；NRBdMF额外支持+1/-1方向性
    标签（比如药物的治疗效果vs副作用）。
  - 任务对应：T2A-DE/T2A-DIR 的基因×条件矩阵结构天然对应，NRBdMF的方向性设计尤其贴合T2A-DIR
    （敏感vs抗）。
  - 依据：训练成本最低（不需要GPU、不需要图结构数据），T2A的矩阵形状比T1的"扰动子-基因对"结构
    更适合直接套用矩阵分解。实现：`src/eval/matrix_factorization_baseline.py`。
  - 引用：Yasuo et al. 2023, *J. Chem. Inf. Model.*（NRBdMF）；Wang et al. 2017, *BMC Cancer*
    17:513（SRMF）。

- **GAT**（从T1移植）
  - 一句话：跟T1同一套GAT架构，图结构换成化合物结构相似性/靶点网络（而非STRING/YEASTRACT）。
  - 任务对应：T2A-DE/T2A-DIR，图节点变成"基因+条件"两类。
  - 实现要点：需要额外构造化合物-化合物相似性图（T1的STRING/TF图不能直接复用），比矩阵分解多一步
    图构造成本。
  - 引用：同T1条目，Wei et al., ICLR 2026 (arXiv:2512.00306) Appendix B.2。

- **MultiXrank（RWR + 监督分类器）**
  - 一句话：同T1条目的方法，图结构换成条件相似度网络（`condition_similarity.json`已有）。
  - 任务对应：网络传播 + 轻量分类器两段式。
  - 实现要点：原论文验证的是gene-disease关联，迁移到gene-chemical需要额外验证。
  - 引用：Baptista, Brière, Baudot 2024, *BMC Bioinformatics* 25:70。

- **弹性网络回归/随机森林**
  - 一句话：姊妹领域（人类癌症药物敏感性预测，GDSC/CCLE数据集）里最经典、几乎每篇评测论文都必须
    包含的baseline下限——用基因组学特征做弹性网络回归或随机森林预测药物响应。
  - 任务对应：T2A-DE/DIR——"用基因组学特征预测药物敏感性"这个任务形式跟T2A高度相似，只是物种
    不同（人类癌细胞系 vs 酵母）。
  - 实现要点：训练成本极低（标准sklearn实现，分钟级），是这个姊妹领域公认的"最低配置"参照，但
    需要重新构造T2A自己的特征集（不能直接复用人类癌症数据的表达/突变特征）。
  - 引用：综述性评估 *Assessment of modelling strategies for drug response prediction in cell
    lines and xenografts*（PMC7028927），弹性网络baseline具体应用见 *Predicting cancer drug
    targets*（PMC8455625）。

**T1/T2A 目前的实现进度（2026-07-22 更新）**：T1的GAT/MultiXrank/GenKI/KGE-TGI**四个全部已有
真实实现**（`src/eval/gat_baseline.py`、`src/eval/multixrank_baseline.py`、
`src/eval/genki_baseline.py`、`src/eval/kge_tgi_baseline.py`）；T2A的矩阵分解、弹性网络回归、
GAT三个已有真实实现（`src/eval/matrix_factorization_baseline.py`、
`src/eval/elasticnet_rf_baseline_t2a.py`、`src/eval/gat_baseline_t2a.py`），仅T2A的MultiXrank
还是方法论设计阶段、尚未实现代码，数字见 `task_results.md`（已实现的会有真实数字，未实现的保持
⬜）。

**T1的GAT（2026-07-22 已跑出真实数字，`src/eval/gat_baseline.py`）**：技术选型——本机所有conda
环境原生都没装PyTorch Geometric（`base`/`dataprep`/`ptm`/`yeast_embed`/`yorzoi`等逐一查过），但
网络可用，在已有torch 2.6.0的`dtibase`环境里`pip install torch_geometric`直接装上了（CPU版，图
规模小——约7千节点/25万边，GATConv全图前向毫秒级），**不需要退化成sklearn**，全程CPU训练、未碰
GPU/side-channel。图=STRING直接邻居(`results_close_gene.json`)∪YEASTRACT TF→靶基因
(`tf_targets.json`)合并成一张无向图；节点特征=是否TF/是否ESR/复合物数/STRING度数/总度数+**仅用
train split算的目标编码特征**（该基因作为pert/gene时train集经验阳性率，Laplace平滑，严格不碰
val/test标签）+ 可学习节点embedding，两层GAT refine后接pair分类头；train/test切分**完全复用**
LLM评测用的`deleteome_DE.csv`/`deleteome_DIR.csv`的`split`列。**真实结果**：T1a-DE Macro-F1=.709/
MCC=.419/Acc=.845（小幅超过最强LLM 14B的.680/.359/.622）；T1b-DIR Macro-F1=.682/MCC=.441/
Acc=.685（Macro-F1与14B的.683打平，MCC/Acc超过14B的.372/.657）。**关键负结果（如实报告，不是
硬凑出来的漂亮数字）**：合理性校验时发现一个完全不训练、不用KG、只记"该读出基因在train split里
多数类标签"的一行查表基线（`Gene-majority`），Macro-F1/MCC/Acc（T1a-DE: .759/.524/.885；T1b-DIR:
.754/.514/.790）**全面超过GAT，也超过LLM**——说明这份Deleteome数据集存在很强的"某些读出基因
近乎恒定DE/恒定同一方向"的基因级基础率（比如持续处于应激响应状态的基因），这个朴素统计量比GAT的
STRING+YEASTRACT图消息传递捕捉得还准，即使把这个统计量显式加进GAT输入特征后（从.703提升到
.709）仍未追平。这比"GAT是否赢过LLM"这个问题本身更值得关注：本任务里"训练型方法"相对"死记基因
基础率"的边际价值有限。**合理性校验**：结果数值处在VCWorld论文引用区间（DE AUROC 0.59-0.69、DIR
准确率0.52-0.61）同一量级、没有到.9这类明显泄漏信号的水平，Gene-majority基线同样处在类似或更高
的位置，判断是数据集本身"基因级基础率信号强"的真实特性，不是代码bug造成的标签泄漏（已核实：全部
特征含目标编码均只用train split计算，未接触val/test标签）。真实数字见
[`task_results.md`](task_results.md) T1a-DE/T1b-DIR 主结果表格。

### 消融/变体统一用哪个模型跑（跨任务决定，2026-07-22 确认）

**消融（Retrieval-only / w/o Biocontext / w/o CoT）、A/B prompt 分支、变体4（训练型对照）—— 全部
只在一个代表模型上跑，不需要像主矩阵那样 4 个模型全跑**。理由：消融/变体要回答的是"某个组件拆掉后
分数掉多少""某种方法论下能不能打平LLM"，不是重新验证"越大越准"这个规模趋势（那是主矩阵已经回答
过的问题）；VCWorld论文本身的审稿记录里，`VCWorld(Retrieval-only)`/`(w/o Biocontext)`/`(w/o CoT)`
在结果表里也是各自只有一行，没有对每个模型尺寸重复跑一遍，说明"消融只挑一个代表模型"是这类论文的
通行做法。

**代表模型选择**：本项目统一用 **Qwen2.5-14B**——它是主矩阵里综合表现最强的模型（T1a-DE 四项
指标全部领先，T1b-DIR 三项领先，见 [`task_results.md`](task_results.md)），逻辑上跟 VCWorld
（推测用其默认旗舰模型 Gemini 2.5-Flash 做消融，见下方"VCWorld怎么选的"）一致：**用能代表方法
上限的模型做消融，消融结果的说服力最强**（如果连最强模型都需要靠这些组件才能打平/超过消融版本，
论点最扎实；反过来如果拿最弱模型做消融，"是模型太弱"和"是组件真的重要"这两个原因会混在一起，
说服力打折）。

**VCWorld 怎么选的（推测，非确凿事实）**：审稿记录本身的结果表里，消融那几行没有像其他行一样
标注具体模型名（不像 `VCWorld(Llama3-8B)`/`VCWorld(Qwen2.5-14B)` 那样明确写出）。但 reviewer
inaw 的**初次**审稿（rebuttal补充Qwen系列之前）就已经引用了"w/o BioContext ~0.51""w/o CoT ~0.59"
这两个消融数字，说明这些消融在补充开源模型之前就已存在——当时论文的默认/旗舰配置是 Gemini
2.5-Flash（不带模型后缀的"VCWorld"通常指这个默认配置，Llama3-8B 是被单独点名的"较弱开源对比项"）。
据此推断消融大概率用的是 Gemini 2.5-Flash，但**论文正文方法论部分没有直接确认这一点**，这是推断
不是查证过的事实，不需要进一步核实——本项目已经按同样逻辑（挑综合最强模型）独立做出了选择，跟
VCWorld具体怎么选的无关。

跨任务落地：Task 2A的消融/A-B分支/变体4如果启动，统一原则不变，但"综合最强模型"要按Task 2A自己
的主矩阵结果重新判断（Task 2A里最优模型在不同指标上是分散的——Macro-F1/MCC最优是Qwen2.5-7B，
Acc/Answered%最优是Qwen3-4B，见 [`task_results.md`](task_results.md)"T2A-DE 主结果"——届时需要
额外讨论选哪个，不能直接照搬Task 1的Qwen2.5-14B）。

### 这套消融跟 A/B 分支的关系

A/B 是"哪种 prompt 写法更好"（都保留完整的检索证据+背景知识+多步推理，只是脚手架的组织方式
不同）；上面三条消融是"v1（或 A/B）里的每一块设计，拆掉之后分数掉多少"，回答的是完全不同的
问题，两者不冲突、可以正交组合（比如"A 分支 + w/o CoT"这种组合本次未规划，如果需要单独验证
"A 分支的机制强制在没有 CoT 展开时是否还有用"，可以后续再补）。

### 实现状态

- **A/B prompt 分支**：**已实现并跑出真实数字**（2026-07-23，Qwen2.5-14B，T1a-DE/T1b-DIR/
  T2A-DE/T2A-DIR × A/B × 3-seed，数字见上方"A/B 分支结果"一节，`data/ab/agg_ab.json`）。
- **Random 基线**：已用真实代码算出（`src/eval/baselines.py`，见上一节"怎么算"），不需要额外
  实现，数字见 [`task_results.md`](task_results.md)。
- **Retrieval-only**：**已实现并跑出真实数字**（2026-07-24，`src/eval/retrieval_only_baseline.py`，
  纯本地规则脚本，对每个test case的`retrieved_pairs`做真实label众数投票，无`retrieved_pairs`时
  回退train-split多数类，3-seed，`data/ab/agg_retrieval_only.json`），数字见
  `task_results.md`四张主表。
- **w/o Biocontext / w/o CoT**：**已实现并跑出真实数字**（2026-07-24，Qwen2.5-14B，T1a-DE/
  T1b-DIR/T2A-DE/T2A-DIR × C(w/o Biocontext)/D(w/o CoT) × 3-seed，模板见
  `support/variants/{C_no_biocontext,D_no_cot}/`，数字见上方"消融C/D结果"一节，
  `data/ab/agg_ab_cd.json`），同时也已回填进 `task_results.md` 四张主表的对应行。
- **变体4（训练型传统ML对照）**：**T1已实现并跑出真实数字**——走的是上面"架构清单"里的**GAT**
  路线（`src/eval/gat_baseline.py`，2026-07-22，详见上文"T1的GAT"小节，数字见
  `task_results.md` T1a-DE/T1b-DIR 表格），逻辑回归/随机森林那条更简单的备选路线因为GAT已经
  跑通、且GAT本身就是VCWorld审稿记录认可的先例（见"为什么加这一条"）而没有并行再做，不是因为
  技术上不可行；T1的MultiXrank/GenKI/KGE-TGI三个**均已实现并跑出真实数字**（见下方新增段落）。
  **T3等其他任务仍是设计阶段、未实现**。**T2A专门实现了矩阵分解版本并已跑出真实数字**（2026-07-22，见
  `src/eval/matrix_factorization_baseline.py`，数字见 `task_results.md` T2A-DE/T2A-DIR 表格）——
  T2A天然是"基因x条件"矩阵结构，比T1的"扰动子-基因对"结构更适合NRBdMF/SRMF这类矩阵分解直接套用，
  所以T2A没有走特征分类器路线，而是走了本节开头方法论提到的矩阵分解路线（`compute_metrics`同一套
  评分口径，train/test切分与LLM评测完全同一份`hillenmeyer_phenotype.csv`/`hillenmeyer_direction.csv`）。
  **核心实现**：手写bias-augmented ALS（k=25, reg=3.0）对`yp_matrix_z_haphom`连续z-score做低秩
  重构，只用train split格子训练，阈值/符号判定在基因级别留出的15%训练基因上校准。**已核实的关键
  限制**：本项目T2A的split是按基因整体切分（train/test基因**零重叠**），意味着每个test基因在
  train矩阵里都是彻底的行冷启动，标准ALS学不出隐向量；用"该基因在其它Hillenmeyer条件下、未被
  train/test标签表采样到的真实z-score格子"做fold-in解决（2995/3002 test基因有≥3个可用格子）。
  **已核实并如实记录的信息不对称**：fold-in用到的是同一基因在其它条件下的真实定量测量值，这是
  LLM推理管线结构上访问不到的信息通道（LLM只看检索到的文本证据，不接触原始矩阵）；关掉fold-in、
  只用条件级偏置的"结构上真正冷启动"版本，T2A-DE的MCC掉到接近0（-.027，约等于瞎猜），T2A-DIR
  MCC掉到.164（仍有弱信号但远低于fold-in版本的.629）——两个版本的数字都记在`task_results.md`，
  不只报对LLM更有利/更不利的那一个。T3的特征分类器版本仍待实现，优先级见团队讨论。

**2026-07-22 补充：T1的GenKI/KGE-TGI、T2A的GAT 三个此前⬜的方法均已实现并跑出真实数字**（数字见
`task_results.md`对应表格，方法细节见各表格下方说明，此处只记跨方法的实现层面要点，不重复展开）：

- **T1-GenKI**（`src/eval/genki_baseline.py`）：VGAE，全程无监督（DE/DIR标签只用于事后校准一个
  标量阈值，从不进入encoder/decoder梯度），"推导出的GRN"用Deleteome敲除阵列"A"通道（近似WT表达）
  的Pearson相关网络。T1a-DE Macro-F1=.492/MCC=.026、T1b-DIR Macro-F1=.443/MCC=.104——四个训练型
  对照里最弱，但明确跳出Majority/Random两条零推理基线，弱信号符合"先验知识最少的方法"这一预期，
  未出现分数异常。CPU训练，DE/DIR两次跑合计约20分钟（含1400+次虚拟敲出前向传播，是主要耗时点）。
- **T1-KGE-TGI**（`src/eval/kge_tgi_baseline.py`）：Multi-subgraph GCN，仅用YEASTRACT
  activates/represses两张有向子图（不含STRING），关系类型分离卷积。T1a-DE Macro-F1=.684/
  MCC=.429（MCC超过GAT和14B）、T1b-DIR Macro-F1=.650/MCC=.336（略低于GAT）。跟GAT用同一套
  target-encoding特征后二者分数量级接近，说明"关系类型分离卷积"这个架构改动本身边际贡献有限，
  真正驱动分数的仍是共享的基因基础率特征（呼应GAT小节的Gene-majority负结果）。CPU训练，DE+DIR
  合计约15分钟。
- **T2A-GAT**（`src/eval/gat_baseline_t2a.py`）：图结构从头重写为基因<->条件二分图（条件-条件边
  用`condition_similarity.json`、基因-条件边用STITCH靶点+train-interaction两个来源），非
  STRING/YEASTRACT。**关键负结果**：T2A的按基因切分split导致99.5-99.6%的test基因在这张图里
  零度数（STITCH覆盖率太低、train-interaction边按构造连不到test基因），T2A-DE Macro-F1=.234/
  MCC=.024**跌破Random基线**（本项目目前所有训练型对照里唯一一个跑不赢零推理弱基线的例子）；
  T2A-DIR Macro-F1=.434/MCC=.014，大体持平Majority。这跟矩阵分解（靠fold-in真实z-score格子）、
  弹性网络（靠不依赖基因专属历史值的结构特征）形成对比——两者都用不同方式绕开了T2A的结构性冷启动
  问题，GAT-T2A两条路都没走通，是本组四个T2A训练型方法里目前处理冷启动最差的一个，如实记录。
  CPU训练，DE+DIR合计约9分钟。
- **通用技术备注**：三者均沿用GAT-T1建立的先例——`dtibase` conda环境（已装torch 2.6.0+
  torch_geometric 2.8.0 CPU版）、全程CPU训练、未使用GPU/side-channel。运行本机（12核，
  运行期间与其它用户共享，load average一度达17）资源竞争明显，实测单次训练/评测耗时波动较大
  （同样规模的1个epoch有时30秒有时90秒），属正常的多用户环境竞争现象，不影响结果正确性。
