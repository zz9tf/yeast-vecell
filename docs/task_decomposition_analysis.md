# 任务拆解再审视 — 该不该继续拆、能不能拆

> 纯分析文档（不动 pipeline 代码 / 数据）。回答用户核心问题：**当前的任务分解要保持、合并、还是继续拆分？**
> 结论先行，然后按 5 个子问题逐条给出有数据支撑的推理，最后给一份按「价值/成本」排序的推荐任务清单。
>
> 现状任务：**T1** 表达（T1a DE Yes/No、T1b DIR Inc/Dec）on Deleteome；**T2A** 生长表型（DE-analog Yes/No、DIR-analog sens/resist）on `yp_matrix_z_haphom`；**T2B** 遗传互作符号（neg/pos）on SGA。模型 = LLM 逐三元组、固定 5 步推理脚手架（对标 VCWorld）。

---

## 底线建议（TL;DR）

**保持当前 5 个任务的分解，本轮不要再拆成更多任务。** 现有 DE / DIR 二分本身已经是正确的、且已经是一个「DE 门控 → DIR」的两级级联结构，不需要改成 3-way 或回归。真正该做的不是「拆任务」，而是两件**低成本、高价值**的事：

1. **修 DIR 推理内容以匹配「敲除 = 完全 LoF」**（结构可迁移，但推理逻辑必须重写）——这是**正确性**问题，不是拆分问题。
2. **把「拆分」降级为「评测时的 reporting slice」**，并且**只保留分析上真有意义的那几个切片**（TF vs 非 TF 最关键），其余按 RESULTS.md 的「raw-first、settings 后续轮次再拆」精神登记为 later-round。

一个贯穿全文的**最重要发现**（影响的是评测而非分解）：**当前落地 CSV 里的正例率全是负采样产生的假象，且两个 DE 任务方向相反** —— T1a 建成集 15.3% 正例（真实每格率 ≈ 0.59%），T2A-DE 建成集 **62% 正例**（真实命中率 4.66%）。这意味着 (a) 裸 accuracy 几乎没有意义、必须按真实基率/按人群分开报，(b) **越把数据切碎，正例越稀、数字越不稳** —— 这本身就是**反对现在过度拆分**的硬理由。

| 任务 | 建议 | 一句话理由 |
|---|---|---|
| T1a 表达-DE | **保持** | 旗舰，直接对标 VCWorld；结构无需动 |
| T1b 表达-DIR | **保持 + 重写脚手架** | LoF 让方向逻辑更干净（见 §4），但当前脚手架没吃满这个红利 |
| T2A-DE 生长有无表型 | **保持** | 天然多条件，复用同一 pipeline |
| T2A-DIR 敏感/抗 | **保持但降信心** | 「方向」是适合度而非调控，且有 orientation 未审计的 caveat（见 §4） |
| T2B 遗传互作符号 | **保持（待建）** | 唯一真正「不同的」白盒任务（双扰动、通路冗余推理），价值高 |
| 合并成单一 3-way{down/none/up} | **不采纳为主任务** | 会把「有没有效应」（阈值/噪声主导）和「往哪走」（机制主导）两种性质完全不同的判断混在一个指标里；且丢失 VCWorld 可比性。可作为 later-round 的**免费衍生视图** |
| 幅度回归 / binned-magnitude / ranking | **不作为任务**，最多 later-round 的 reporting bin | LLM 无标定回归能力，few-shot 例子不带幅度；ranking 还破坏「逐三元组独立推理」的架构 |

---

## 关键事实（下面所有推理都基于这些数）

均来自本次对仓库内数据/知识资产的直接核查。

**Task 1 / Deleteome**（`deleteome_all_mutants_ex_wt_var_controls.txt`，`prepare.py`）
- 1484 个敲除实验（1482 个唯一基因，1 个 `hsn1` 解析失败）；6112 个读出 ORF。扰动类型 = **完全缺失 / LoF**，单一稳态条件（SC、log phase）。
- 其中 **167 / 1482 = 11.3%** 的扰动子是 YEASTRACT 有符号 TF（`tf_targets.json` 共 192 个签名 TF，含 activate/repress）。读出侧 189 个 ORF 是 TF。
- DIR 分布 **升 66% / 降 34%**（35,234 up / 18,207 down）—— 这不是噪声，是 Kemmeren 2014 的核心发现「abundance of gene-specific repressors」：删东西更多是**去抑制→升高**。majority baseline 就有 66%。
- DE 建成集 15.3% 正例（350,241 行 / 53,441 正）是 `n_neg=200/pert` 采样的产物；真实每格命中率 ≈ **0.59%**。

**Task 2A / `yp_matrix_z_haphom`**（`build_growth_labels.py`）
- 4554 基因（扰动子，系统 ORF）× **7689** 个 growth 筛选（context）。
- context 几乎**不可分箱**：7689 个里有 **7463 个互不相同的 conditionset**（近乎每个筛选一个独有条件）；`standard`（未处理基线）仅 72 个。
- phenotype 字段**退化**：6830/7689 是 `growth (pooled culture)`，一类独大 → 按 phenotype 分层无意义。
- collection：7031 hom（非必需基因纯合缺失）+ 618 hap → **本矩阵本质就是「非必需基因」人群**；必需基因（HIP/het）在另一个矩阵（`--use-het`，未默认建）。
- 来自 **345 个不同 pmid/paper** → 强烈的批次/打分口径异质性（builder 自己标注了 DIR 的 orientation「未逐 screen 审计」caveat）。
- DE-analog 建成集 **62% 正例**（2,419,323 行 / 1,510,380 正）也是采样假象（正例不设上限、每基因中位 208 命中 >> 200 采样负例）；真实命中率 **4.66%**。DIR 抗 33% / 敏感 67%。

**知识资产（已就绪，决定能不能做机制化 DIR 与分层）**
- `tf_targets.json`：192 签名 TF（YEASTRACT，activate/repress）——DIR 机制推理与 TF 分层的基础。
- `perturbagen_similarity.json`（5707 基因）、`results_close_gene.json`（5791）、`gene_desc.json`（7166）、`gene_alias.json`（23937 resolver keys）。

**仓库里现有 vs 缺失的扰动数据**：Deleteome ✅、Hillenmeyer2008 HOP/HIP ✅（但 HOP 273 列已并入 haphom 矩阵）、**IDEA ❌ 未下载**、Hughes ❌、SGA(T2B) ❌ 待建。

---

## 1. DE + 独立 DIR 是对的分解吗？还是应该换成别的？

**先厘清一个常被忽略的点：当前设计已经是一个两级级联。** DIR 只在 DE 命中子集上打标签与评测（`prepare.py` 的 `dir_records` 只 append 正例）。所以「two-stage（DE gate → DIR）」不是替代方案，而是**现状**。真正的设计选项是「要不要把这两级合成一个」。

### 逐个替代方案

**(a) 单一 3-way {down / none / up}** — **不采纳为主任务**。
- 坏处 1：把两种性质完全不同的判断塞进一个指标。「none vs 非 none」是**稀有事件检测**，命中与否高度依赖阈值 + 平台噪声（微阵列 p 值、慢生长混杂）；「up vs down」是**近机制化的符号推理**，干净得多。合并后单一 accuracy 无法分别诊断这两件事。
- 坏处 2：类别基率悬殊（真实 none ≈ 99.4%，up:down ≈ 2:1）——3-way 会被 none 完全主导，宏观指标退化。
- 坏处 3：丢失与 VCWorld 的**横向可比性**（论文就是 DE + DIR 两张表）。
- 坏处 4：对 LLM prompting，DE 的推理（「这基因到底在不在下游」）和 DIR 的推理（「去抑制一个激活子→降」）是**不同脚手架**；合并会稀释各自的机制链。
- 唯一正面用法：3-way 混淆矩阵可以从两个二分预测**免费衍生**出来当诊断视图（例如看「DE 判对但方向判反」有多少）——列为 later-round 的 free view，不设成任务。

**(b) 幅度回归 / binned-magnitude** — **不作为任务，最多做 reporting bin**。
- 标签有（M / z 现成，无泄漏、基率无碍）。但 (i) LLM 无标定连续回归能力；(ii) 检索的 few-shot 例子**不携带幅度**，in-context 无从校准量纲；(iii) VCWorld 也不做。
- 正确用法：把 |M| / |z| 切成 bin **只用于评测切片**（见 §2「effect-size bins」），不改变任务本身。

**(c) ranking（按 DE 可能性给读出基因排序）** — **later-round 至多**。更贴近「一次筛选产出一个排序」的真实形态、且**绕开任意阈值**；但它**破坏 VCWorld 的核心架构**（逐三元组独立推理），需要 listwise/长上下文或 O(n²) 成对比较，与现有 infra 不兼容。属重构级改动，不在本轮。

**(d) two-stage（DE→DIR）** — **保持（已是现状）**，但要把一个隐含选择显式化：DIR 在**推理时**是跑在「预测为 DE 阳性」上（真实级联、误差传播），还是跑在「gold DE 阳性」上（干净测方向推理能力）？VCWorld 用后者（DIR CSV 就是 gold DE-hit 子集）。**建议**：主指标用 gold-DE 子集（干净地量方向推理），把端到端级联的 3-way 作为 later-round 次要指标。

**§1 结论**：DE 与 DIR 保持为**两个独立 prompt / 独立指标**（对标 VCWorld、保持基率干净、保持脚手架聚焦）。不合并为 3-way 主任务；3-way 混淆矩阵、幅度 bin、ranking 全部 later-round。

---

## 2. 是否该把每个任务分层成子任务 / 报告切片？哪些有意义、哪些是噪声

**原则**：这些应是**评测时的 reporting slice（同标签、同 prompt、eval 时切）**，不是新任务、不是新数据 pipeline。且鉴于「关键事实」里的基率假象，**碎片化会放大数字不稳**，所以只保留分析上真有意义的少数几个。

### Task 1（Deleteome）

| 切片 | 判定 | 理由 |
|---|---|---|
| **TF vs 非 TF 扰动子** | ✅ **最有意义** | 167/1482=11.3% 扰动子是签名 TF。删 TF → 其靶基因直接变化、**符号可由 YEASTRACT activator/repressor 直接定**；删非 TF 则因果链长、多为间接。这是**白盒论点的核心判决**：若机制推理是真的，DIR 在 TF 扰动子上应显著高于非 TF。低成本、高诊断价值 |
| **effect-size bins（\|M\| 分箱）** | ✅ 有意义 | 近阈值命中（\|M\|≈0.766）是标签噪声所在；强命中（\|M\|>2）应易判。分箱能把「能检出强效应」与「阈值处是否标定」分开。DIR 同理（强方向易判）。低成本 |
| **慢生长混杂切片** | ✅ 有意义（中成本） | 很多敲除引发非特异慢生长/应激表达签名。按扰动子是否「slow-growth strain」切，可把特异调控效应从通用应激里分出。需慢生长注释（或用 `responsive`/`svd_transformed` 版本对比），列 later-round |
| **必需 vs 非必需（扰动子轴）** | ❌ 退化 | Deleteome 扰动子按定义都是**非必需**（必需基因无法做纯合缺失株）。此轴对 T1 扰动子近乎恒定，无信息 |
| **读出基因功能类（GO）** | ⚠️ 噪声偏多 | 类别多、每类 n 小；TF→靶关系才是「功能类」的锐利版本，优先用它 |

### Task 2A（growth）

| 切片 | 判定 | 理由 |
|---|---|---|
| **standard/未处理 vs stress/化学条件** | ✅ 有意义（低成本） | `standard` 下有生长表型 = 缺失株的**内在慢生长**（基因内禀、较易预测）；stress 条件下 = **条件特异化学敏感**（本质不同、更难）。混在一起报会掩盖两种能力。可从 conditionset=`standard`（72 个）+ 关键字粗分近似 |
| **hom vs hap collection** | ✅ 弱有意义 | 7031 hom / 618 hap，人群不同；可作次要分层 |
| **按 phenotype 类型** | ❌ 退化 | 6830/7689 是 `growth (pooled culture)`，一类独大，切不出信息 |
| **按细粒度 condition** | ❌ 基本不可行 | 7463 个互不相同的 conditionset，多为 singleton，切不出稳定的箱；要粗分类须大量手工 curation（drug / oxidative / DNA-damage / osmotic / nutrient / temperature），多数仍是 singleton。**噪声 >> 信号** |
| **按 source paper/batch（345 pmid）** | ⚠️ 是**混杂**不是干净切片 | 打分口径异质 + DIR orientation 未审计。应作为**要控制的 confound**（报告时注意）而非拿来做卖点分层 |
| **必需 vs 非必需** | = 换数据源 | 这里等价于「het 矩阵 vs haphom 矩阵」（不是 task 内切片）。het/HIP（必需、单倍剂量不足）是**另一人群**，若建了 het 标签可作平行报告，见 §3 |

**§2 结论**：真正值得的切片只有少数几个——**T1：TF vs 非 TF（最高）、effect-size bins、慢生长混杂；T2A：standard vs stress、hom vs hap**。退化/噪声的（T2A phenotype 类型、T2A 细粒度 condition、T1 必需性）不做。**全部登记为 later-round slice**，与 RESULTS.md「settings 拆解留后续轮次」一致。本轮唯一要保证的「现在」动作：**保留原始 M/z 数值可 join 回预测**，让这些切片将来可算（大多数 flag 可事后从 pert/gene/context + 原始矩阵重算，所以甚至无需现在改 CSV schema）。

---

## 3. 给定现有数据，还值得新增哪些子任务？（可行性：标签 / 基率 / 泄漏）

| 候选 | 标签可得性 | 基率 | 泄漏风险 | 结论 |
|---|---|---|---|---|
| **IDEA 时序动力学**（fast/slow、transient/sustained responder） | 需把时序 collapse（峰值 \|log2FC\| + 符号）——**但 IDEA 数据当前未下载** | 尚可 | ⚠️ **高**：若同时用 IDEA TF-诱导做标签、又把 YEASTRACT TF→靶当证据，而 YEASTRACT 部分源自类似诱导数据 → 模型可「作弊」。需隔离知识源 | **later-round**：先把 IDEA 当 **Task-1 的第二个数据集/上下文**（gain-of-function，补 LoF），跑通再谈「dynamics」这个真正新颖的子任务。需先获取数据 + 处理泄漏 |
| **幅度 / 方向+幅度**（3-way weak/strong/none 之类） | 有（M/z 现成） | none 主导 | 无 | **不作为任务**，作 §2 的 effect-size reporting bin |
| **T2B SGA 符号（neg/pos）** | Costanzo 明确定义（待建） | GI 本身稀（几 %），符号在显著 GI 内 | 低（注意别把 SGA profile 同时当 T1 检索相似度**又**当 T2B 标签→跨任务泄漏，分开即可） | **保持（已规划）**：唯一真正「不同」的白盒任务（双扰动、通路冗余/缓冲推理），价值最高的补充 |
| **het/HIP（必需基因、单倍剂量不足）作平行 T2 人群** | builder 已有 `--use-het` 通道 | 待测 | 低 | **later-round**：与 haphom 互补的必需基因人群，同框架直接复用 |
| **Hughes/Rosetta 作跨实验室泛化测试集** | 格式类 Deleteome（ratio+p），未下载 | 类 T1 | 低 | **later-round**：只作 hold-out 泛化评测，不新增任务类型 |
| 「TF-缺失方向可预测性」聚焦基准 | = §2 的 TF 切片精选高置信子集 | — | — | **不是新任务**，就是 §2 的 TF 切片；可作白盒卖点的重点展示 |

**§3 结论**：本轮**不新增任务类型**。唯一已规划该做的新任务是 **T2B（SGA）**，保持。IDEA/het/Hughes 都是 later-round，且 IDEA 要特别防 YEASTRACT 泄漏。

---

## 4. VCWorld 的 DE/DIR 拆分能原样迁移到酵母遗传扰动吗？——「敲除 = 完全 LoF」改变了推理

**结构可迁移，但 DIR 的推理内容必须为 LoF 重写**（DE 的结构基本照搬即可）。三个酵母特有的点：

1. **方向逻辑更干净，不是更复杂。** VCWorld 的扰动是**药物**：对直接靶点是抑制还是激活本身就有歧义（agonist/antagonist），所以它的 DIR 脚手架要写「suppress activator→decrease；suppress repressor→increase，**and vice versa for drug activation**」。酵母**完全缺失 = 无歧义地移除功能**：删掉 TF_p，若 p **激活** 靶 G → G **降**；若 p **抑制** G → G **升**。符号**完全由 YEASTRACT 边的符号决定**，比人类药物干净。VCWorld 里「药物抑制还是激活靶点？」这一步在缺失场景下是**冗余**的。
   - **现状核查**：仓库的 `support/DIR_template.py` **已经**部分 LoF 化（写了「removes its function」、activator/repressor 双分支、slow-growth 混杂提示）——方向对。**但还没吃满红利**：没有把下面第 2 点的**去抑制先验**写进去。建议补一句方向性先验。
2. **Kemmeren 的「去抑制」不对称（升 66% / 降 34%）是酵母特有的真信号，不是噪声。** 删东西更常导致**去抑制→升高**（「abundance of gene-specific repressors」）。含义：
   - DIR 的 **majority baseline = 66%**，裸 accuracy 会骗人 → **必须报 macro-F1 / MCC + majority baseline**。
   - 这反而是**白盒推理的绝佳展示**：模型若能解释「删的是一个抑制子 → 去抑制 → 升」，就展示了真机制。建议脚手架显式提示这个先验。
   - 这也再次支持 §2 的 TF 切片：干净的符号逻辑只在**直接 TF→靶边**成立；非 TF 缺失的 DEG 多是**间接**（代谢反馈、应激），符号不可由单边决定。DIR 准确率在 TF+直接靶切片上理应显著更高。
3. **T2A 的 DIR 只是「表面」类比，不是同类推理。** T2A-DIR「敏感 vs 抗」是**适合度**问题，不是调控符号问题——「去抑制激活子/抑制子」那套**根本不适用**。而且「抗」（删掉某基因反而长得更好，33%）往往反映丢失了药物导入/激活通路或某个限速调控子，机制杂、且 builder 明确标注 **orientation 未逐 screen 审计**。所以：
   - T2A-DIR 需要**自己的脚手架**（通路缓冲、条件下的通路必需性），不能套 T1 的方向逻辑；
   - 应**标注为低信心**、单独报告，别和 T1-DIR 混为一谈。

**§4 结论**：DE/DIR 的**框架**迁移得很好，甚至因为 LoF 更适合白盒推理；但 **DIR 的推理内容要按 LoF 重写并加入去抑制先验**（T1 已部分完成，差临门一脚），**T2A-DIR 要另起脚手架并降信心**。这是**改脚手架**，不是**改任务分解**。

---

## 5. 推荐最终任务清单（按 价值/成本 排序）+ later-round

### 本轮保持的任务分解（raw-first，不动结构）
- **T1a DE**（Deleteome）· **T1b DIR**（Deleteome, gold-DE 子集）· **T2A-DE**（growth）· **T2A-DIR**（sens/resist）· **T2B SGA**（待建）。
- **不**合并成 3-way 主任务；**不**新增幅度/ranking 任务。

### 按 价值/成本 排序的行动项

| # | 行动 | 价值 | 成本 | 何时 |
|---|---|---|---|---|
| 1 | **保持现有 5 任务分解** | 高 | 0 | 现在（已对） |
| 2 | **DIR 脚手架加「去抑制」方向先验** + DIR 评测改报 **majority(66%)+macro-F1+MCC** | 高（正确性） | 低 | 现在 |
| 3 | **诚实基率报告**：明确标注建成集正例率（T1a 15% / T2A-DE 62%）是采样假象、真实率（0.59% / 4.66%），**按人群/真实基率分开报**，别只看汇总 accuracy | 高 | 低 | 现在 |
| 4 | **保证原始 M/z 可 join 回预测**（让 later-round 切片可算；多数 flag 事后可重算，无需现在改 schema） | 高 | 低 | 现在 |
| 5 | **T2A-DIR 单列 + 降信心标注**（orientation caveat、适合度≠调控） | 中 | 低 | 现在 |
| 6 | **T2B（SGA）建标签并跑通** | 高 | 中（建数据） | 本轮末～下轮，已规划 |
| 7 | later-round 切片：**TF vs 非 TF（最高）**、effect-size bins、慢生长、standard-vs-stress、hom-vs-hap | 高 | 低（但要有原始预测） | later |
| 8 | **3-way {down/none/up} 混淆矩阵**：从两个二分预测免费衍生的诊断视图 | 中 | 低 | later |
| 9 | **IDEA** 作 Task-1 第二数据集（GoF 上下文）→ 再谈 dynamics 子任务 | 中-高 | 高（获取+防 YEASTRACT 泄漏） | later |
| 10 | **het/HIP** 平行人群、**Hughes** 跨实验室 hold-out | 中 | 中 | later |
| 11 | 幅度回归 / ranking 作**任务** | 低-中（LLM 标定风险） | 高 | 大概率不做 |

### 明确留给「后续轮次」的（对齐 RESULTS.md「原始优先、settings 后拆」）
所有 reporting slice（#7）、3-way 衍生视图（#8）、幅度 bin、IDEA/het/Hughes 扩展（#9/#10）、以及 ranking/回归（#11）。本轮只跑原始 5 任务、留全原始预测，把这些登记为 later-round —— 与现有 RESULTS.md「后续轮次再拆」小节完全一致，无需新增结构。

---

### 一句话回答用户
**任务不该再往下拆成更多任务，也不必合并——现有 DE/DIR × (T1/T2A/T2B) 五格分解是对的。** 该投入的地方是：(1) 把 DIR 推理按「敲除=完全 LoF + 去抑制不对称」重写（改脚手架不改分解）；(2) 用诚实的基率/分人群评测，别被采样假象骗；(3) 把「拆」降级为**少数几个真有意义的 later-round 报告切片**（TF vs 非 TF 最关键），而不是现在制造更多稀疏、不稳的子任务。
