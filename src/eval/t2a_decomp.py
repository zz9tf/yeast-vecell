#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 2A 分解1 & 分解3 的真实计算脚本（分解2 因资产不可得而跳过，见报告）。

分解1：胁迫机制大类分层（关键词规则），对 T2A-DE 重新切子集算 Macro-F1。
分解3：多浓度梯度化合物子集的剂量-响应一致性 + 阈值型判断 Macro-F1（T2A-DE）。
"""
import csv, json, re, statistics as st
from collections import defaultdict, Counter

import sys
sys.path.insert(0, "/home/zhengz2/projects/yeast-vecell/src/eval")
from score import load_predictions, compute_metrics

REPO = "/home/zhengz2/projects/yeast-vecell"
T = f"{REPO}/data/task2"
MODELS = ["qwen14b", "qwen7b", "qwen4b", "llama8b"]
SEEDS = [0, 1, 2]

# ---------- shared: extract (pert, context) test_case order without full json.load ----------

def extract_test_cases(path):
    txt = open(path, encoding="utf-8").read()
    return [(m.group(1), m.group(2)) for m in re.finditer(
        r'"test_case":\s*\{\s*"pert":\s*"([^"]+)",\s*"gene":\s*"([^"]+)"', txt)]


DE_TESTCASES = extract_test_cases(f"{T}/t2de_retr_full_s0.json")
print(f"[info] T2A-DE test_case count = {len(DE_TESTCASES)}")
# sanity check seeds share identical test_case order (verified separately for s1);
# we reuse DE_TESTCASES for all seeds' de scoring order.

# ---------- ground truth ----------

def load_label_map(csv_path):
    m = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m[(row["pert"], row["context"])] = int(row["label"])
    return m


DE_LABELS = load_label_map(f"{T}/hillenmeyer_phenotype.csv")
DE_TRUTH = [DE_LABELS.get(tc) for tc in DE_TESTCASES]

# ==========================================================================
# 分解1：胁迫机制大类关键词分类
# ==========================================================================

RULES = [
    ("DNA损伤类", [
        r"\bmms\b", r"bleomycin", r"camptothecin", r"cisplatin", r"phleomycin",
        r"mitomycin", r"doxorubicin", r"gamma-irradiation", r"4-nitroquinoline",
        r"\b4nqo\b", r"methyl methanesulfonate",
    ]),
    ("氧化应激类", [
        r"hydrogen peroxide", r"\bdiamide\b", r"menadione", r"paraquat",
        r"peroxide", r"tert-butyl hydroperoxide", r"\btbhp\b",
    ]),
    ("渗透压/细胞壁类", [
        r"sodium chloride", r"\bnacl\b", r"sorbitol", r"potassium chloride",
        r"\bkcl\b", r"congo red", r"calcofluor white", r"caffeine\b", r"\bsds\b",
        r"micafungin", r"caspofungin", r"sodium dodecyl sulfate",
    ]),
    ("药物靶点/耐药外排类", [
        r"rapamycin", r"cycloheximide", r"tunicamycin", r"fluconazole",
        r"ketoconazole", r"itraconazole", r"clotrimazole", r"amphotericin",
        r"nystatin", r"terbinafine", r"benomyl", r"nocodazole", r"tubulin",
        r"fk506", r"tacrolimus", r"cyclosporin", r"latrunculin", r"brefeldin",
        r"tamoxifen", r"fluoxetine", r"clozapine", r"haloperidol",
        r"staurosporine", r"geldanamycin", r"radicicol", r"lovastatin",
        r"fluvastatin", r"methotrexate", r"5-fluorouracil", r"5-fluorocytosine",
        r"streptomycin", r"neomycin", r"paromomycin", r"hygromycin",
        r"g418", r"geneticin", r"clioquinol", r"miconazole", r"econazole",
        r"chlorpromazine", r"amiodarone", r"verapamil", r"fluphenazine",
    ]),
]
COMPILED = [(name, [re.compile(p, re.I) for p in pats]) for name, pats in RULES]


def classify(conditionset):
    for name, pats in COMPILED:
        for p in pats:
            if p.search(conditionset):
                return name
    return None


CTX_CLASS = {}
with open(f"{T}/haphom_growth_contexts.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        CTX_CLASS[row["context"]] = classify(row["conditionset"])

CATS = ["DNA损伤类", "氧化应激类", "渗透压/细胞壁类", "药物靶点/耐药外排类"]
masks = {c: [CTX_CLASS.get(ctx) == c for _, ctx in DE_TESTCASES] for c in CATS}
sizes = {c: sum(masks[c]) for c in CATS}
covered = sum(1 for _, ctx in DE_TESTCASES if CTX_CLASS.get(ctx) is not None)
print(f"[分解1] 测试集 {len(DE_TESTCASES)} 行中可归类 {covered} 行 "
      f"({100*covered/len(DE_TESTCASES):.1f}%)，各大类行数: {sizes}")

# distinct contexts per category (of the 273 used contexts)
ctxs_by_cat = defaultdict(set)
for _, ctx in DE_TESTCASES:
    c = CTX_CLASS.get(ctx)
    if c:
        ctxs_by_cat[c].add(ctx)
print("[分解1] 各大类覆盖的 distinct context 数:", {k: len(v) for k, v in ctxs_by_cat.items()})

print("\n===== 分解1结果：T2A-DE 按胁迫机制大类 Macro-F1 =====")
decomp1 = {}
for m in MODELS:
    decomp1[m] = {}
    for cat in CATS:
        f1s = []
        for s in SEEDS:
            path = f"{T}/t2de_pred_{m}_s{s}.txt"
            preds = load_predictions(path, "growth")
            n = min(len(preds), len(DE_TRUTH))
            p_sub = [x for x, k in zip(preds[:n], masks[cat][:n]) if k]
            t_sub = [x for x, k in zip(DE_TRUTH[:n], masks[cat][:n]) if k]
            met = compute_metrics(p_sub, t_sub, "growth")
            f1s.append(met["macro_f1"])
        mean_f1 = st.mean(f1s)
        std_f1 = st.pstdev(f1s) if len(f1s) > 1 else 0.0
        decomp1[m][cat] = (mean_f1, std_f1)
    print(m, {c: f"{v[0]:.3f}±{v[1]:.3f}" for c, v in decomp1[m].items()})

# ==========================================================================
# 分解3：多浓度梯度化合物子集
# ==========================================================================

MODIFIER_WHITELIST = {"time", "temperature", "ph", "growth phase", "oxygen",
                       "radiation", "microgravity"}
UNIT_RE = re.compile(r"^([\d.]+)\s*(nm|um|mm|m|ng/ml|ug/ml|mg/ml|mg/l|%|j/m2|"
                      r"gy|krads|u/ml|pm)$", re.I)


def parse_titration(conditionset):
    parts = [p.strip() for p in conditionset.split(",")]
    first = parts[0]
    m = re.match(r"^(.+?)\s*\[([^\]]+)\]\s*$", first)
    if not m:
        return None
    name, conc = m.group(1).strip().lower(), m.group(2).strip()
    for extra in parts[1:]:
        pfx = extra.split("[")[0].strip().lower()
        if pfx not in MODIFIER_WHITELIST:
            return None
    mm = UNIT_RE.match(conc)
    if not mm:
        return None
    return name, mm.group(2).lower(), float(mm.group(1))


used_contexts = set(ctx for _, ctx in DE_TESTCASES)
ctx_meta = {}
groups = defaultdict(list)  # (name,pmid,collection,unit) -> [(context,val)]
with open(f"{T}/haphom_growth_contexts.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        ctx_meta[row["context"]] = row
        if row["context"] not in used_contexts:
            continue
        p = parse_titration(row["conditionset"])
        if p is None:
            continue
        name, unit, val = p
        groups[(name, row["pmid"], row["collection"], unit)].append((row["context"], val))

gradient_series = {k: sorted(set(v), key=lambda x: x[1])
                    for k, v in groups.items() if len(set(vv for _, vv in v)) >= 3}
print(f"\n[分解3] 找到 {len(gradient_series)} 个>=3浓度点的化合物剂量梯度系列"
      f"（均来自同一paper/collection，within 273 used contexts）:")
for k, v in gradient_series.items():
    print(" ", k, v)

gradient_contexts = set()
for v in gradient_series.values():
    for ctx, _ in v:
        gradient_contexts.add(ctx)
print(f"[分解3] 涉及 distinct context 数 = {len(gradient_contexts)}")

grad_mask = [ctx in gradient_contexts for _, ctx in DE_TESTCASES]
print(f"[分解3] 测试集中命中行数 = {sum(grad_mask)}")

# per-series context order ascending
series_ctx_order = {k: [c for c, _ in v] for k, v in gradient_series.items()}

# index test_case rows by (pert,context)
idx_by_pc = defaultdict(list)
perts_by_ctx = defaultdict(set)
for i, (pert, ctx) in enumerate(DE_TESTCASES):
    idx_by_pc[(pert, ctx)].append(i)
    perts_by_ctx[ctx].add(pert)

print("\n===== 分解3结果 =====")
decomp3 = {}
for m in MODELS:
    consist_rates = []
    f1s = []
    for s in SEEDS:
        path = f"{T}/t2de_pred_{m}_s{s}.txt"
        preds = load_predictions(path, "growth")
        n = min(len(preds), len(DE_TRUTH))

        # 阈值型判断 macro-F1 on gradient-series subset
        p_sub = [x for x, k in zip(preds[:n], grad_mask[:n]) if k]
        t_sub = [x for x, k in zip(DE_TRUTH[:n], grad_mask[:n]) if k]
        met = compute_metrics(p_sub, t_sub, "growth")
        f1s.append(met["macro_f1"])

        # 剂量-响应一致率：per (series, pert) trajectory across ascending dose
        n_traj = 0
        n_consistent = 0
        for key, ctx_order in series_ctx_order.items():
            # build pert -> list of (ctx_rank, pred) using idx_by_pc
            traj = defaultdict(list)
            for rank, ctx in enumerate(ctx_order):
                for pert in perts_by_ctx.get(ctx, ()):
                    for i in idx_by_pc.get((pert, ctx), []):
                        if i < n:
                            traj[pert].append((rank, preds[i]))
            for pert, points in traj.items():
                points.sort()
                vals = [v for _, v in points if v is not None]
                if len(vals) < 2:
                    continue
                n_traj += 1
                if all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)):
                    n_consistent += 1
        rate = n_consistent / n_traj if n_traj else float("nan")
        consist_rates.append((rate, n_traj))

    valid_rates = [r for r, n in consist_rates if n > 0]
    mean_rate = st.mean(valid_rates) if valid_rates else float("nan")
    mean_f1 = st.mean(f1s)
    decomp3[m] = (mean_rate, mean_f1, consist_rates)
    print(m, "dose-consistency=", consist_rates, "mean=", mean_rate,
          " thresholdF1(mean)=", f"{mean_f1:.3f}")

json.dump({"decomp1": {m: {c: decomp1[m][c] for c in CATS} for m in MODELS},
           "decomp1_sizes": sizes, "decomp1_covered": covered,
           "decomp1_total": len(DE_TESTCASES),
           "decomp3_series": {str(k): v for k, v in gradient_series.items()},
           "decomp3": {m: decomp3[m][:2] for m in MODELS}},
          open("/tmp/claude-1784258/-home-zhengz2/44cd04e8-a890-4b4c-abb8-6a667da3c2ea/scratchpad/t2a_decomp_out.json", "w"),
          indent=2, default=str)
print("\ndone.")
