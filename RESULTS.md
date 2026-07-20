# Yeast-vecell 跑分记录（Results Tracking）

> 用途：记录各任务下 **N 个本地模型 + baseline** 的评测跑分。每完成一次推理评测就更新对应格子，并在
> **Run Registry** 里追加一行。空格 = 未跑。指标定义、约定见下。

相关：任务定义 [`PLAN.md`](PLAN.md) · 模型清单 Part C.5 · 数据 [`docs/data_sources.md`](docs/data_sources.md)
· [`docs/supplementary_data_and_tasks.md`](docs/supplementary_data_and_tasks.md)。

---

## 约定

- **模型（本地，对齐 VCWorld backbone，去掉 API 的 Gemini）**：
  `Qwen2.5-14B`（主力）· `Qwen2.5-7B` · `Qwen3-4B` · `Llama3.1-8B`。推理参数统一 `temperature=0.6, top_p=0.9`。
- **切分**：按扰动子 30/70，`seed=42`；检索只读 train。
- **评测按数据集/任务分开报**（不同任务基率不同，不混合成一个 accuracy）。
- **指标定义**：
  - `Answered%` = 非 "insufficient/弃权" 的占比（这套 prompt 允许弃权，必须跟踪）。
  - `Acc` = 整体准确率，**弃权记为错**（另可在括号注明"仅已答"的 Acc）。
  - `Macro-F1`、`MCC`（类别不均衡时比 Acc 更可信）。
  - `方向Acc`（DIR/2A-DIR）= 在**真差异/真表型命中**上的升降(或敏感/抗)判对率。
  - `AUROC` = 仅当从模型抽到置信度/logit 时才填，否则 `—`。
- **run_id 命名**：`<task>-<model>-b<budget>-<lab>-<promptver>-<MMDD>`，
  例 `t1de-qwen14b-b10-truelab-v1-0720`（`truelab`=真标签 few-shot，`shuf`=随机标签消融）。

## 状态图例
`✅ 完成` · `🟡 跑中` · `⬜ 待跑` · `❌ 失败` · `—` 不适用

---

## 任务 & 数据总览

| 任务 | 子任务 | 数据 | #test cases | 正例率(base rate) | 阈值 | 状态 |
|---|---|---|---|---|---|---|
| **T1 扰动→表达** | 1a DE (Yes/No) | Deleteome (all_mutants_ex_wt_var) | ⬜ | ⬜ | `p<0.05 & \|M\|>0.766` | ⬜ 待 prepare |
| | 1b DIR (Inc/Dec) | Deleteome (DE 命中子集) | ⬜ | ⬜ | `sign(M)` | ⬜ |
| **T2A 扰动→生长表型** | 2A-DE 有无表型 | yp_matrix_z_haphom | ⬜ | ⬜ | `\|z\|>?（待定）` | ⬜ 待 build |
| | 2A-DIR 敏感/抗 | yp_matrix_z_haphom | ⬜ | ⬜ | `sign(z)` | ⬜ |
| **T2B 遗传互作**(补充) | 2B sign (neg/pos) | Costanzo SGA | ⬜ | ⬜ | `\|ε\|>?, p<?` | ⬜ |

---

## Scoreboard

### T1a — DE：扰动是否让基因差异表达（Yes/No） · Deleteome

| 模型 / baseline | Answered% | Acc | Macro-F1 | MCC | AUROC | run_id | 日期 |
|---|---|---|---|---|---|---|---|
| **Qwen2.5-14B** (主力) | ⬜ | ⬜ | ⬜ | ⬜ | — | | |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | — | | |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | — | | |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ | — | | |
| _baseline: Majority_ | — | ⬜ | ⬜ | ⬜ | — | | |
| _baseline: No-retrieval LLM (14B)_ | ⬜ | ⬜ | ⬜ | ⬜ | — | | |
| _baseline: Network-neighbor 启发式_ | — | ⬜ | ⬜ | ⬜ | ⬜ | | |
| _baseline: LogReg(网络特征)_ | — | ⬜ | ⬜ | ⬜ | ⬜ | | |

### T1b — DIR：差异方向（Increase/Decrease） · Deleteome（DE 命中子集）

| 模型 / baseline | Answered% | 方向Acc | Macro-F1 | MCC | run_id | 日期 |
|---|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| _baseline: Majority(多数方向)_ | — | ⬜ | ⬜ | ⬜ | | |
| _baseline: YEASTRACT 符号规则_ | — | ⬜ | ⬜ | ⬜ | | |

### T2A-DE — 扰动是否产生生长表型（Yes/No） · yp_matrix_z_haphom

| 模型 / baseline | Answered% | Acc | Macro-F1 | MCC | run_id | 日期 |
|---|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| _baseline: Majority_ | — | ⬜ | ⬜ | ⬜ | | |
| _baseline: No-retrieval LLM (14B)_ | ⬜ | ⬜ | ⬜ | ⬜ | | |

### T2A-DIR — 敏感/抗（sensitive/resistant） · yp_matrix_z_haphom（表型命中子集）

| 模型 / baseline | Answered% | 方向Acc | Macro-F1 | MCC | run_id | 日期 |
|---|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| _baseline: Majority_ | — | ⬜ | ⬜ | ⬜ | | |

### T2B — 遗传互作符号（negative/positive） · SGA（补充任务）

| 模型 / baseline | Answered% | Acc | Macro-F1 | MCC | run_id | 日期 |
|---|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ | | |
| _baseline: Majority_ | — | ⬜ | ⬜ | ⬜ | | |

---

## 消融 / 专项（Ablations）

| 消融 | 任务 | 设置对比 | 指标 | 结果 | 结论 |
|---|---|---|---|---|---|
| **Few-shot 标签** | T1a | 真标签 vs 随机(复现 VCWorld bug) | Acc/F1 Δ | ⬜ | 预期：真标签明显更好 |
| **检索** | T1a | 有检索 vs 无检索(仅描述) | Acc/F1 Δ | ⬜ | 检索是否真有用 |
| **规模趋势** | T1a | 4B→7B→14B | Acc | ⬜ | 验证"越强越准"(VCWorld 结论) |
| **上下文** | T1a | 有/无 dataset-context 描述 | Acc | ⬜ | 上下文贡献 |

---

## Run Registry（每次跑一行）

| run_id | 日期 | 任务 | 模型 | 配置(budget/few-shot/context/prompt_ver) | 预测文件 | 主指标 | 备注 |
|---|---|---|---|---|---|---|---|
| _(示例)_ `t1de-qwen14b-b10-truelab-v1-0720` | — | T1a DE | Qwen2.5-14B | b10 / truelab / Deleteome-ctx / v1 | `out/t1de_pred_qwen14b.txt` | Acc=? | 模板 |

---

## 外部参考（VCWorld 人类 GeneTAK，C32 细胞系，**不可与酵母直接比**，仅看趋势）

| Backbone | DE acc (paper) |
|---|---|
| Llama3-8B | 0.37 |
| Qwen2.5-14B | 0.65 |
| Gemini-2.5-Flash（我们不跑） | 0.70 |

趋势：性能随模型推理能力上升 → 我们在酵母上应复现同样的"越强越准"（见消融"规模趋势"）。

---

## Changelog
- 2026-07-20：建表（结构就绪，等 Phase 0 pipeline + 数据落地后开跑）。
