# AAAI 稿件骨架

`main.tex` 是章节骨架占位，**尚未套用官方 `aaai.sty`**。当前只写了内容展开说明（LaTeX 注释形式），
**没有写任何正文句子**——按用户要求，正文要一块一块在后续对话里一起写。

## AAAI 官方 Author Kit 可以直接复用

姊妹项目 `yeast-rank-cross-lab` 下的 **`imbalance_study/paper/`**（注意不是
`yeast-vecell/imbalance_study/paper`——那个路径不存在，正确路径在 `yeast-rank-cross-lab` 仓库里）
已经套好了**真实的 AAAI-2027 官方 Author Kit**，且已验证能用 `pdflatex` 编译出干净的 6 页双栏 PDF
（全 Type-1 字体、零 Type-3、无 undefined 引用）：

- `aaai2027.sty` / `aaai2027.bst` — 官方样式文件（取自 https://aaai.org/authorkit27/ ，请勿手改）
- `build.sh` — 一键编译（`pdflatex → bibtex → pdflatex → pdflatex`），本机 TeX Live 装在
  `$HOME/texlive/2026`
- `main.tex` 用 `\usepackage[submission]{aaai2027}`（匿名投稿模式，自动隐藏作者+加匿名版权页脚）

**接入方法**：把 `aaai2027.sty`、`aaai2027.bst`、`build.sh` 从
`/home/zhengz2/projects/yeast-rank-cross-lab/imbalance_study/paper/` 复制到本目录，`main.tex` 的
`\documentclass`/`\usepackage` 那两行按那边 `main.tex` 的实际写法替换即可，不需要重新联网下载。
如果投稿年份变了（AAAI-2027 → 更新版本），才需要去官方渠道重新拿 kit。

## 目录结构
```
paper/
├── main.tex                  # \input 拼接 sections/，标题占位待定
├── sections/
│   ├── abstract.tex          # 结构化占位（问题+重要性+方法+关键数字+意义）
│   ├── introduction.tex      # 动机注释 + 末尾 Contributions bullet list（TODO占位）
│   ├── related_work.tex      # 按主题分 \paragraph，注释里点名要引用哪些工作
│   ├── method.tex             # 按 \subsection 描述该讲的技术内容
│   ├── experiments.tex        # 按 RQ 组织，每节点名要用 RESULTS.md/task_results.md 哪些表
│   └── conclusion.tex
└── references.bib            # 已确认相关的条目 + FIXME 待核实条目
```

## 状态
- **骨架搭建阶段**：所有 section 文件里只有 LaTeX 注释形式的"如何展开"说明，没有一句正文。
- 骨架里点名的很多具体数字来自 `RESULTS.md`（已定稿的主矩阵 16/16）；**A/B prompt 消融、部分
  训练型 ML baseline 在 `docs/task_results.md` 里仍在补充中**（其他 agent 正在跑），Experiments
  节的 RQ3/RQ4 写作前要先去核实哪些行已经从 ⬜ 变成真实数字，不要把骨架说明里提到的"待补充"项
  当成已完成来写。
- RQ4（YEASTRACT 可解释性/机制一致率核查，对应 PLAN.md Phase 5）目前**还没有实测产出**，只是
  PLAN.md 里的待办——写这节正文前需要先确认这项分析是否已经跑过。

## 写作风格提醒
- 每节标题下先用注释写清楚"问题是什么/现有方法是什么/局限是什么/我们做了什么/引用哪些具体
  文件数字"，正文句子留到骨架经确认后再逐块填。
- Introduction 结尾放显式 `\subsection*{Contributions}` bullet list。
- Related Work 按主题分 `\paragraph{}`，每个标题下注释列出要引用的具体工作。
- Experiments 按研究问题（RQ）组织，不按"图1/图2"组织；每个 RQ 点名对应哪份已有结果文档
  （`RESULTS.md`/`docs/task_results.md`）的哪张表。
- 每个实验结果都要多 seed（本项目统一 3 seed）+ mean±std，不能只放单次数字。
- 图表密度参考模板惯例：1张pipeline图 + 若干结果表（T1a/T1b/T2A-DE/T2A-DIR各一张主表）+
  1-2张消融/分解表是合理密度，其余进附录。
- 正文页数硬顶（AAAI-2027 常规轨道通常 7 页正文，以官方 kit 当年实际要求为准），reproducibility
  checklist 和 references 不占页数。
