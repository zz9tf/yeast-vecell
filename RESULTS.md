# Yeast-vecell 跑分记录（Results Tracking）

> **AAAI 主实验记录。** 目标 = **全量 T1 + T2-A（生长适合度）× 4 本地模型 × 3 seed → `mean ± std`**，
> 用 **vLLM** 推理（HF generate 全量太慢）。每格主指标 **Macro-F1**（类别不均衡下比 Acc 可信），
> 并列记 MCC / Acc(弃权记错) / Answered%；原始预测文件留存在 `data/runs/`、`data/task2/`。

相关：[`PLAN.md`](PLAN.md) · [`docs/pipeline.md`](docs/pipeline.md) · 规模对标 VCWorld Table 5。

## 约定
- **模型**（本地，去 API Gemini）：`Qwen2.5-14B` · `Qwen2.5-7B` · `Qwen3-4B` · `Llama3.1-8B`；`temp=0.6, top_p=0.9`。
- **切分**：扰动子 30:70，检索只读 train；few-shot 带**真标签**。**3 seed（0/1/2）** 取 mean±std。
- **推理**：vLLM（cu12.x，匹配 8s-06 驱动）；`prepare→retrieve→prompt→infer(vLLM)→score`。
- **状态**：`✅ · 🟡跑中 · ⬜待跑`。

---

## 任务 & 数据（全量规模）

| 任务 | 数据 | test 规模 | 正例率 | 状态 |
|---|---|---|---|---|
| **T1a** DE（是否差异表达） | Deleteome | **245,500** | ~14% | ⬜ 待跑(vLLM) |
| **T1b** DIR（升/降） | Deleteome(DE命中) | **37,900** | 升66/降34 | ⬜ |
| **T2A-DE** 生长适合度(有无表型) | Hillenmeyer 2008 (273 条件, hom) | **58,980** | 采样后~0.70 | ⬜ |
| **T2A-DIR** 敏感/抗 | Hillenmeyer 2008 | **41,373** | 抗25/敏75 | ⬜ |
| (T2B 遗传互作 neg/pos) | Costanzo SGA | — | — | 🟡 后续 |

> T2-A 缩到 Hillenmeyer 2008（单篇 chemical-genomics，纯合 HOP 库；hap 不含——见 pipeline 讨论）。

---

## 主结果（全量 · 3-seed · `Macro-F1 mean±std`；括号内 MCC）— 待跑

### T1a — 表达 DE
| 模型 | Macro-F1 ± | MCC ± | Acc ± | Answered% | 原始输出 |
|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | DE_pred_qwen14b_s{0,1,2}.txt |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | DE_pred_qwen7b_s* |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | DE_pred_qwen4b_s* |
| Llama3.1-8B | **.613±.002** | **.234±.004** | .373±.001 | 49.5% | DE_pred_llama8b_s* |
| _Majority_ | ⬜ | — | ⬜ | — | — |
| _No-retrieval LLM(14B)_ | ⬜ | ⬜ | ⬜ | ⬜ | — |

### T1b — 表达 DIR
| 模型 | Macro-F1 ± | MCC ± | 方向Acc ± | Answered% | 原始输出 |
|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | DIR_pred_qwen14b_s* |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | DIR_pred_qwen7b_s* |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | DIR_pred_qwen4b_s* |
| Llama3.1-8B | **.583±.000** | **.238±.003** | .461±.002 | 78.8% | DIR_pred_llama8b_s* |
| _Majority(升)_ | ⬜ | — | ⬜ | — | — |
| _YEASTRACT 符号规则_ | ⬜ | ⬜ | ⬜ | — | — |

### T2A-DE — 生长适合度：有无表型
| 模型 | Macro-F1 ± | MCC ± | Acc ± | Answered% | 原始输出 |
|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | t2de_pred_qwen14b_s* |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | t2de_pred_qwen7b_s* |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | t2de_pred_qwen4b_s* |
| Llama3.1-8B | **.581±.001** | **.164±.002** | .477±.002 | 70.3% | t2de_pred_llama8b_s* |
| _Majority_ | ⬜ | — | ⬜ | — | — |

### T2A-DIR — 生长适合度：敏感/抗
| 模型 | Macro-F1 ± | MCC ± | 方向Acc ± | Answered% | 原始输出 |
|---|---|---|---|---|---|
| **Qwen2.5-14B** | ⬜ | ⬜ | ⬜ | ⬜ | t2dir_pred_qwen14b_s* |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ | t2dir_pred_qwen7b_s* |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ | t2dir_pred_qwen4b_s* |
| Llama3.1-8B | .455±.001 | **.070±.006** | .736±.001 | 98.2% | t2dir_pred_llama8b_s* |
| _Majority_ | ⬜ | — | ⬜ | — | — |

---

## Pilot 参照（500 例 · 单 seed · HF；**仅看趋势，非最终结果**）

首轮小规模验证（seed 0，v1 prompt，真标签检索），证明"越强越准"成立、pipeline 通：

| 模型 | T1a DE (F1/MCC/已答) | T1b DIR (F1/MCC/已答) |
|---|---|---|
| Qwen2.5-14B | .71 / **.42** / 77% | .73 / **.46** / 96% |
| Llama3.1-8B | .64 / .28 / 56% | .61 / .31 / 80% |
| Qwen2.5-7B | .62 / .25 / 76% | .63 / .29 / 97% |
| Qwen3-4B | .56 / .17 / 46% | .69 / .38 / 82% |

**趋势**：DE & DIR 的 MCC 均随模型能力上升（4B→14B），复现 VCWorld 人类结论。T2A 的 500-pilot 正在跑。

---

## 后续轮次（登记，暂不做）
- **Baselines**：Majority · No-retrieval LLM · Network-neighbor · YEASTRACT 符号规则(DIR) · LogReg。
- **消融**：真标签 vs 随机 few-shot · 有/无检索 · prompt 分支 A(机制)/B(校准) · 规模趋势。
- **扩展任务**：T2B SGA 遗传互作 · het/HIP · IDEA 时序。

## 外部参考（VCWorld 人类 GeneTAK，规模见 Table 5：DE test 每系 7.2万–11.6万）
Llama3-8B `0.37` → Qwen2.5-14B `0.65` → Gemini-2.5-Flash `0.70`（趋势，不可与酵母直接比）。

## Changelog
- 2026-07-20：改成"每模型一个填空、保留原始结果"。
- 2026-07-20：填入 500-pilot T1a/T1b（4 模型）。
- 2026-07-20：**重构为 AAAI 主实验结构** —— 全量 T1 + T2-A(Hillenmeyer) × 3 seed(mean±std) × vLLM；旧 500 结果降为 pilot 参照。
