# Yeast-vecell 跑分记录（Results Tracking）

> 用途：**每个任务下、每个模型一个填空**。将来出结果直接把数填进对应格子 + 把原始预测文件路径填进
> "原始输出"列即可。**这一轮只记原始结果**；把原始结果拆解成不同 setting（DE/DIR 细分、baseline、
> 消融、多指标）是**后续轮次**的事，见最后一节，现在不铺开。

**本地模型（N=4，对齐 VCWorld backbone，去 API 的 Gemini）**：
`Qwen2.5-14B`（主力）· `Qwen2.5-7B` · `Qwen3-4B` · `Llama3.1-8B`。统一 `temperature=0.6, top_p=0.9`。
**切分**：按扰动子 30/70，`seed=42`。**状态**：`✅完成 · 🟡跑中 · ⬜待跑`。

相关：[`PLAN.md`](PLAN.md)（任务定义/模型 Part C.5）· [`docs/data_sources.md`](docs/data_sources.md)。

---

## 任务 & 数据总览

| 任务 | 数据 | 扰动子 | 读出/上下文 | #test | 正例率 | 状态 |
|---|---|---|---|---|---|---|
| **T1a** 表达-DE（是否差异表达 Yes/No） | Deleteome | 1484 敲除(小写标准名) | 6112 ORF | 1039 perts | 15.3% | ✅数据就绪 |
| **T1b** 表达-DIR（升/降 Inc/Dec） | Deleteome(DE 命中) | 1414 | 4459 ORF | (DE 子集) | 升66%/降34% | ✅数据就绪 |
| **T2A-DE** 生长有无表型（Yes/No） | yp_matrix_z_haphom | 4554 基因(ORF) | 7689 生长筛选 | 3188 perts | 命中~4.66%(阈`\|z\|≥2`) | ✅数据就绪 |
| **T2A-DIR** 敏感/抗（sens/resist） | yp_matrix_z_haphom(命中) | 4554 | `sign(z)` | (命中子集) | 抗33%/敏感67% | ✅数据就绪 |
| **T2B** 遗传互作符号（neg/pos） | Costanzo SGA | 基因对 | — | ⬜ | ⬜ | 🟡 待 Agent4 |

> 说明：T1a/T1b 来自已跑的 `de prepare`（DE 350,241 行/正例 53,441；DIR 53,441 行/升 35,234·降 18,207）。
> T2A 来自 `build_growth_labels.py`（表型 2,419,323 行/正例 1,510,380；方向 1,510,380 行/抗 499,192·敏感 1,011,188；
> 切分 1,366 train / 3,188 test）。注：这些是**采样负例后**的数据集分布，非总体真实基率。T2B 等 SGA 落地。

---

## 结果表（每个模型一个填空）

> 填法：把主结果数字填进「结果」列；「原始输出」列填该次推理的预测文件路径（**原始结果必须留存**，
> 以便后续拆解）；顺带记 run_id 与日期。主指标默认用 **Acc**（后续拆解时再补 F1/MCC/方向Acc 等）。

### T1a — 表达 DE（Deleteome, 500 例）
| 模型 | 结果(F1 / MCC / Acc, 已答%) | 原始输出(预测文件) | run_id | 日期 |
|---|---|---|---|---|
| **Qwen2.5-14B** | **F1 .71 / MCC .42** / Acc .66 (77%) | DE_pred_qwen14b.txt | t1a-qwen14b-b8-truelab-v1 | 07-20 |
| Qwen2.5-7B | F1 .62 / MCC .25 / Acc .62 (76%) | DE_pred_qwen7b.txt | t1a-qwen7b-b16-truelab-v1 | 07-20 |
| Qwen3-4B | F1 .56 / MCC .17 / Acc .34 (46%) | DE_pred_qwen4b.txt | t1a-qwen4b-b16-truelab-v1 | 07-20 |
| Llama3.1-8B | F1 .64 / MCC .28 / Acc .44 (56%) | DE_pred_llama8b.txt | t1a-llama8b-b16-truelab-v1 | 07-20 |

### T1b — 表达 DIR（Deleteome，DE 命中子集, 500 例/471 有证据）
| 模型 | 结果(F1 / MCC / 方向Acc, 已答%) | 原始输出(预测文件) | run_id | 日期 |
|---|---|---|---|---|
| **Qwen2.5-14B** | **F1 .73 / MCC .46** / Acc .74 (96%) | DIR_pred_qwen14b.txt | t1b-qwen14b-b8-truelab-v1 | 07-20 |
| Qwen2.5-7B | F1 .63 / MCC .29 / Acc .63 (97%) | DIR_pred_qwen7b.txt | t1b-qwen7b-b16-truelab-v1 | 07-20 |
| Qwen3-4B | **F1 .69 / MCC .38** / Acc .72 (82%) | DIR_pred_qwen4b.txt | t1b-qwen4b-b16-truelab-v1 | 07-20 |
| Llama3.1-8B | F1 .61 / MCC .31 / Acc .62 (80%) | DIR_pred_llama8b.txt | t1b-llama8b-b16-truelab-v1 | 07-20 |

### T2A-DE — 生长有无表型（yp_matrix_z_haphom）
| 模型 | 结果(Acc) | 原始输出(预测文件) | run_id | 日期 |
|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ |

### T2A-DIR — 敏感/抗（yp_matrix_z_haphom，表型命中子集）
| 模型 | 结果(方向Acc) | 原始输出(预测文件) | run_id | 日期 |
|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ |

### T2B — 遗传互作符号（SGA，补充任务）
| 模型 | 结果(Acc) | 原始输出(预测文件) | run_id | 日期 |
|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ |

---

## Run Registry（每次推理留一行 —— 原始结果的索引）

| run_id | 日期 | 任务 | 模型 | 配置(budget/few-shot/context/prompt_ver) | 原始预测文件 | 主指标 |
|---|---|---|---|---|---|---|
| _(示例)_ `t1a-qwen14b-b10-truelab-v1-0720` | — | T1a | Qwen2.5-14B | b10 / truelab / Deleteome-ctx / v1 | `out/…pred.txt` | Acc=? |

---

## 后续轮次再拆（暂不填，等有原始结果后从中拆解）

以下都是"从原始预测里拆出不同 setting"的分析，**不是这一轮**，先登记占位：
- **Baselines**：Majority、No-retrieval LLM、Network-neighbor 启发式、LogReg(网络特征)、YEASTRACT 符号规则(DIR)。
- **消融**：few-shot 真标签 vs 随机(复现 VCWorld bug)、有/无检索、规模趋势(4B→7B→14B)、有/无 context。
- **更多指标**：Answered%(弃权率)、Macro-F1、MCC、AUROC(若抽到置信度)。
- **切片**：按上下文/条件、按基因类别、按扰动子度数 等分层报告。

---

## 外部参考（VCWorld 人类 GeneTAK · C32 · 仅看趋势，不可与酵母直接比）
Llama3-8B `0.37` → Qwen2.5-14B `0.65` → Gemini-2.5-Flash `0.70`（我们不跑 Gemini）。

## 首轮观察（T1a/T1b, 500 例, v1 prompt, 真标签检索）
- **DE 复现"越强越准"**：MCC 随模型能力上升 —— Qwen3-4B .17 < Qwen2.5-7B .25 ≈ Llama3.1-8B .28 < **Qwen2.5-14B .42**，与 VCWorld 人类结论一致。
- **DIR 也"越强越准"**：MCC 7B .29 < Llama .31 < 4B .38 < **14B .46**；DIR 普遍强于 DE，都过随机。小模型（尤其 4B）DE 弃权高（46%）拖累整体 Acc，但已答准确率不低（.74–.86）。
- 均为**采样 500 例**、v1 prompt——prompt 分支 A/B、规模全量、baseline 属后续轮次。

## Changelog
- 2026-07-20：改成"每模型一个填空、保留原始结果"的结构；settings 拆解留后续轮次。
- 2026-07-20：填入首轮 T1a/T1b 全 8 格（4 模型 × DE/DIR）。
