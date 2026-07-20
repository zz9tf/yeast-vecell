# yeast-vecell 全套流程说明

白盒虚拟细胞：结构化酵母知识 + LLM 因果推理，预测**基因扰动→转录组响应**。逐 `(扰动ORF, 读出ORF, 上下文)`
三元组回答 DE（是否差异表达）/ DIR（升/降），套 VCWorld 的检索增强 + 5 步推理脚手架。

```
Deleteome矩阵 ──prepare──▶ {DE,DIR}.csv(pert,gene,label,split)
                                 │
知识资产(自建) ──────────────────┤ retrieve  (pert-sim SGA + gene-sim STRING, 带真标签)
  gene_alias/gene_desc            ▼
  results_close_gene(STRING)   retrieval.json [{test_case, retrieved_pairs:[[pert,gene,label]]}]
  perturbagen_similarity(SGA)     │ prompt  (yeast 模板 + 描述, 显示"STD (ORF)")
  tf_targets(YEASTRACT)           ▼
                              prompts.txt  ──infer(GPU/8s-06)──▶ predictions.txt ──score──▶ Acc/F1/MCC → RESULTS.md
```

标识符规范：**一律系统 ORF 名**（`YFL039C`）。扰动子在 Deleteome 里是小写标准名(`sla1`)，`prepare` 用
`gene_alias.json` 归一到 ORF；描述/相似度全按 ORF 键。

---

## 0. 仓库关键文件
```
src/cli_pipeline/cli.py                 # 唯一入口: de|dir prepare|retrieve|prompt|infer  (从 src/cli_pipeline 下跑)
src/cli_pipeline/stages/{prepare,retrieve,prompt,infer,infer_api}.py
src/cli_pipeline/utils/alias.py         # to_systematic / to_standard / display_name (读 gene_alias.json)
src/knowledge/build_all.py              # -> gene_alias.json + gene_desc.json
src/knowledge/build_gene_sim.py         # -> results_close_gene.json (STRING)
src/knowledge/build_pert_sim.py         # -> perturbagen_similarity.json (SGA)
src/knowledge/build_regulatory.py       # -> tf_targets.json (YEASTRACT, 带符号)
src/task2/build_growth_labels.py        # -> Task2 生长表型标签 (yp_matrix_z_haphom)
src/eval/score.py                       # 打分: 解析预测 -> Acc/answered%/macro-F1/MCC
support/{DE,DIR}_template.py            # v1 yeast 模板; support/variants/{A_mechanism,B_calibration}/ 为 prompt 优化分支
data/perturbation/ data/knowledge/ data/runs/   # 数据/知识/运行产物 (全部 gitignore)
```
解释器：知识/pipeline 的 CPU 步骤用 `/usr/bin/python3.12`（有 pandas）；GPU 推理用 conda env
`inplacettt`（torch 2.8 / transformers 4.57 / accelerate）。

---

## 1. 数据与知识资产（一次性构建，来源全本地）

| 产物 (data/knowledge/) | 脚本 | 本地来源 | 内容/schema |
|---|---|---|---|
| `gene_alias.json` | `build_all.py` | `SGD_features.tab` | `to_systematic`(23937键小写→ORF)、`systematic_to_standard` 等 |
| `gene_desc.json` | `build_all.py` | `gene_function_descriptions.csv`(种子) + SGD + GO gaf | `{ORF: 描述}`, 7166 基因; **读出覆盖 100%、扰动子 99.93%** |
| `results_close_gene.json` | `build_gene_sim.py` | `string_4932_links.txt.gz`(STRING v12) | `{ORF:{direct_neighbors,two_hop_neighbors}}`, 5791 基因, 阈值 combined_score≥700 |
| `perturbagen_similarity.json` | `build_pert_sim.py` | `folder1_GI_raw/Genetic.interaction.score.tsv`(Costanzo SGA) | `{ORF:[相似ORF...]}` top-25, 遗传互作 profile Pearson; 覆盖 Deleteome 扰动子 86% |
| `tf_targets.json` | `build_regulatory.py` | YEASTRACT(逐 TF 查询) | `{TF_ORF:{activates,represses,targets}}`, 192 TF / 179k 带符号边 |

> VCWorld 的人类 JSON（`gene_output.json` 等）**一律弃用**，以上全部酵母自建。

---

## 2. prepare —— Deleteome 矩阵 → DE/DIR 标签
`stages/prepare.py:process_deleteome`。输入 `deleteome_all_mutants_ex_wt_var_controls.txt`
（行=6112 读出 ORF；列=每条件 3 列 M/A/p；1484 敲除 + 3 对照）。**不跑差异分析，直接阈值化**：
- 跳过 3 个对照（LHS 无 `-del`）；`pert` = 标准名 `-del` 前缀 → `to_systematic()` 归一 ORF（1483/1484，`hsn1` 无解保留原名）。
- **DE**: label=1 若 `p<fdr(0.05) & |M|>lfc(0.766)`(=Deleteome 原生 FC>1.7)；label=0 从 `p>pval-neg(0.1)` 每扰动子抽 `n-neg(200)`。
- **DIR**: DE 命中里 `M>0→1(Increase) 否则 0(Decrease)`。
- 按扰动子 `train-fraction(0.3)`, `seed(42)` 切 train/test。

```bash
cd src/cli_pipeline
python cli.py de prepare --out-dir ../../data/runs --name deleteome   # --input默认捆绑文件, --alias默认gene_alias.json
```
产出 `deleteome_DE.csv`(350,241 行: 正53,441/负296,800)、`deleteome_DIR.csv`(53,441: 升35,234/降18,207)；列 `pert,gene,label,split`；1484 扰动 → 445 train / 1039 test。`dir` 与 `de` 共用同一份 CSV。

---

## 3. retrieve —— 挖类比证据（带真标签）
`stages/retrieve.py`。对每个测试 `(pert,gene)`：取 top-`budget` 相似扰动子(pert-sim)与相似读出基因(gene-sim)，
从 **train** 的 `seen` 结构按优先层（共享扰动子 / 共享基因 / 两者相似 / 回填）挖类比对。
**关键修正（vs VCWorld bug）**：每个类比对携带其真 train 标签 → `retrieved_pairs=[[pert,gene,label],...]`；
`--shuffle-labels` 复现随机标签做消融。
```bash
python cli.py de retrieve --data-csv ../../data/runs/deleteome_DE.csv \
  --out ../../data/runs/DE_retr500.json --budget 10 --max-cases 500 --seed 0
```
> **抽样必需**：DE 测试集 ~24 万案例，全量 LLM 不现实 → `--max-cases` 抽 N（首轮 500）。评测复用同一 retrieval.json。

---

## 4. prompt —— 拼 yeast 提示
`stages/prompt.py` + `support/{DE,DIR}_template.py`。模板 exec 出 `contexts`(数据集/扰动类型上下文)、
5 步脚手架(function→specificity→cascade via YEASTRACT→causal bridge→final)、`choices_*`。
证据块用 `retrieved_pairs` 的**真标签**（非随机）；扰动子经 `alias.display_name` 显示为 `STD (ORF)`，描述仍按 ORF 查。
保留 `[Start of Prompt]…[End of Prompt]`(system)/`[Start of Input]…[End of Output]`(user) 标记供 infer 解析。
```bash
python cli.py de prompt --retrieval ../../data/runs/DE_retr500.json \
  --out ../../data/runs/DE_prompts500.txt --context-idx 0
# 换 prompt 分支: --template ../../support/variants/A_mechanism/DE_template.py
```

---

## 5. infer —— GPU 推理（side-channel → 8s-06）
`stages/infer.py`：解析每块为 system+user → `apply_chat_template` → `model.generate`（默认 `temperature=0.6, top_p=0.9`）。
**GPU 派发要点**（HPC 惯例）：
- side-channel `task` 只在**登录节点**起 tmux；GPU 在计算节点 `h100-8s-06`（=“06 组”, 8×H100-80G）。命令须 `ssh h100-8s-06 "..."`。
- 计算节点**无外网** → 必须 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 且 `--model` 传**本地 snapshot 目录路径**（不是 repo-id，否则 transformers 查 hub 报 `OfflineModeIsEnabled`）。
- 权重先在**登录节点**下到共享 NFS 缓存 `~/.cache/huggingface/hub`（`snapshot_download`），计算节点直接读。
- 脚本放**共享 home**（如 `data/runs/`），`/tmp` 是节点本地不可见。

单模型脚本 `data/runs/run_eval.sh <hub_dirname> <gpu> <tag> <batch>`（内部对 DE、DIR 各跑一次 infer，log 落 `eval_<tag>.log`）：
```bash
task run 'yvc_eval_qwen14b' 'ssh h100-8s-06 "bash /home/zhengz2/yeast-vecell/data/runs/run_eval.sh \
  models--Qwen--Qwen2.5-14B-Instruct 0 qwen14b 8"'
```
4 模型并行占 GPU0-3。模型：`Qwen2.5-14B/7B-Instruct`、`Qwen3-4B-Instruct-2507`、`NousResearch/Meta-Llama-3.1-8B-Instruct`(官方 Llama gated 故用免 gate 镜像)。注意 NFS 加载慢(~60s/shard)。产出 `DE_pred_<tag>.txt`/`DIR_pred_<tag>.txt`（块间 80×`=` 分隔，`--- Query for Prompt N ---`）。

---

## 6. score —— 解析 → 指标
`src/eval/score.py`：末次匹配取胜解析闭集答案（DE: Yes/No/insufficient；DIR: Increase/Decrease/insufficient），
**按顺序** join 预测↔retrieval.json↔标签 CSV。手写指标(无 sklearn)。
```bash
python src/eval/score.py --task de \
  --predictions data/runs/DE_pred_qwen14b.txt \
  --retrieval  data/runs/DE_retr500.json \
  --labels-csv data/runs/deleteome_DE.csv --json data/runs/DE_score_qwen14b.json
```
报 `answered%`(非弃权)、`Acc`(弃权记错)、`Acc(已答)`、**`macro-F1`/`MCC`**(类别不均衡下的主指标)、混淆。
→ 数字填入 `RESULTS.md`（对应 scoreboard 格 + Run Registry 一行 + 原始 `*_pred_*.txt` 路径留存）。

---

## 7. 关键设计与坑（务必记住）
- **别名归一化是硬前提**：不做则 `pert`(sla1) 对不上 ORF 键的 pert-sim → 相似度检索层休眠（做后命中 0→95%）。
- **真标签 few-shot**：VCWorld 批量 prompt 例子标签是随机的；此处带真标签，是最大质量杠杆。跨源阈值差异靠**同上下文真标签例子 in-context 自校准**吸收，故各源用原生阈值即可、无需全局对齐。
- **指标**：采样后 CSV 基率失真（DE 读着 15%、真~0.6%），**别看裸 Acc**，看 macro-F1/MCC，且**按数据集分开报**。
- **DIR 用 LoF 干净**：删激活子→降、删抑制子→升（YEASTRACT 符号）；Deleteome 去抑制不对称 66%升/34%降，多数基线=66%，故必须 macro-F1/MCC。分支 A 模板已编码此逻辑。
- **infer 必用本地 snapshot 路径 + offline**，否则计算节点无网报错。

---

## 8. 从零复现顺序
1. 建知识：`python src/knowledge/build_all.py` → `build_gene_sim.py` → `build_pert_sim.py` → `build_regulatory.py`。
2. `de prepare`（出 DE/DIR CSV）。
3. 每任务 `retrieve --max-cases N` → `prompt`（得 prompts.txt）。
4. 登录节点 `snapshot_download` 4 个模型到共享缓存。
5. `task run 'ssh h100-8s-06 "bash run_eval.sh ..."'` 并行 4 模型（DE+DIR）。
6. `score.py` 打 8 份 → 填 `RESULTS.md`。
### Task2（扰动→生长表型）—— 已一等公民化
读出是**条件(screen)**而非基因，用同一套 CLI + 复用件：
- 标签 `src/task2/build_growth_labels.py`（yp_matrix_z_haphom）→ `data/task2/haphom_growth_{phenotype,direction}.csv`（列 `pert,context,label,split`）。
- 条件描述 `context_desc.json`（由 `haphom_growth_contexts.csv` 生成）；条件相似度 `src/knowledge/build_condition_sim.py` → `data/knowledge/condition_similarity.json`（yp 矩阵列-列相关，做检索的 readout-邻居）。
- 模板 `support/task2/{DE,DIR}_template.py`（生长表型 yes/no；方向 sensitive/resistant；含 `readout_line_label` 让例子块显示 "Condition"）。
```bash
# retrieve: 读出列=context, gene-sim 换成条件相似度
python cli.py de retrieve --data-csv ../../data/task2/haphom_growth_phenotype.csv --readout-col context \
  --pert-sim ../../data/knowledge/perturbagen_similarity.json --gene-sim ../../data/knowledge/condition_similarity.json \
  --out $R/t2de_retr.json --budget 10 --max-cases 500 --seed 0
python cli.py de prompt --retrieval $R/t2de_retr.json --template ../../support/task2/DE_template.py \
  --gene-desc ../../data/task2/context_desc.json --pert-desc ../../data/knowledge/gene_desc.json --out $R/t2de_prompts.txt
# infer 同 §5; score 用 growth 模式:
python src/eval/score.py --task growth --predictions $R/t2de_pred.txt --retrieval $R/t2de_retr.json \
  --labels-csv data/task2/haphom_growth_phenotype.csv --readout-col context
```
DIR 用 `dir` + `DIR_template.py` + `--task growth_dir`（labels 用 `haphom_growth_direction.csv`）。**Task2-B（SGA 遗传互作）仍列为后续。**
