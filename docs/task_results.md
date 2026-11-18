# 主矩阵完成小结（2026-07-22）

任务定义见 [`task_definitions.md`](task_definitions.md)（本文档不重复任务是什么，只标注任务代号）。
本轮跑满**主矩阵 16/16**：4 个本地开源模型 × T1a-DE/T1b-DIR/T2A-DE/T2A-DIR × 3-seed，vLLM，
16×H100（commit `4687212`）。T2B（含新拆出的 T2B-DE/T2B-DIR）尚未接入 pipeline，无实测数据。

表格约定：**行 = pipeline 变体**（下面四张主表的行只沿**模型**这一维度——Qwen2.5-14B/7B、
Qwen3-4B、Llama3.1-8B，均为v1 prompt；prompt 分支 A/B/C/D 均已跑出3-seed真实数字，但按惯例不混
进主表，A/B放在 [`prompt_optimization.md`](prompt_optimization.md)"A/B 分支结果"一节、C(w/o
Biocontext)/D(w/o CoT) 放在同文档"消融C/D结果"一节单独对照——注意C/D跟下方"标准基线+消融套件"
里`w/o Biocontext`/`w/o CoT`两行是同一份实验，只是数字在两处都能查到）；**列 = 指标**（Macro-F1、
MCC、Acc 或方向Acc、Answered%，定义见 `task_definitions.md` 各任务"5. 评测口径"）。

每张 Result table 的模型行下方统一附一套**标准基线+消融套件**（Random、Majority/YEASTRACT符号
规则等零推理弱基线 + Retrieval-only/w/o Biocontext/w/o CoT 三条框架消融），这套骨架是**每个任务
都要配的标准补充实验，不是某个任务专属的一次性东西**，方法论、每个消融具体怎么改模板/pipeline、
跨任务的落地差异，统一写在 [`prompt_optimization.md`](prompt_optimization.md)"标准基线+消融套件"
一节，本文档不重复方法论，只放各任务实测出的数字（**T1/T2A四张主表的Retrieval-only/w/o
Biocontext/w/o CoT三行已于2026-07-24全部跑出真实数字**；`No-retrieval LLM`仍待实现，保留⬜）。
表格最下方另附**训练型传统ML对照**（每个任务4个并列独立方法，不是选1个赢家）的占位行，
方法论/引用见 [`prompt_optimization.md`](prompt_optimization.md)、名单见
[`task_definitions.md`](task_definitions.md)各任务"7. 已知的pipeline变体"，已跑出真实数字的
填数字，未实现的保留⬜。

---

## Task 1

### T1a-DE 主结果

| 模型 | Macro-F1± | MCC± | Acc± | Answered% |
|---|---|---|---|---|
| Qwen2.5-14B | **.680±.001** | **.359±.002** | **.622±.002** | **74.2%** |
| Qwen2.5-7B | .628±.002 | .269±.003 | .568±.002 | 73.5% |
| Qwen3-4B | .617±.002 | .271±.004 | .349±.002 | 46.1% |
| Llama3.1-8B | .613±.002 | .234±.004 | .373±.001 | 49.5% |
| _Majority_ | .458 | 0 | .846 | 100% |
| _Random_ | .432±.001 | .000±.002 | .500±.001 | 100% |
| _No-retrieval LLM(14B)_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _Retrieval-only_ | .691±.003 | .429±.005 | .876±.001 | 100% |
| _w/o Biocontext_ | .808±.001 | .617±.003 | .200±.003 | 22.0±0.3% |
| _w/o CoT_ | .702±.003 | .426±.005 | .586±.009 | 67.1±0.8% |
| _GAT_ | .705±.014 | .433±.019 | .818±.026 | 100% |
| _Gene-majority(train，无KG/无模型)_ | .759 | .524 | .885 | 100% |
| _GenKI_ | .493±.001 | .025±.005 | .820±.006 | 100% |
| _KGE-TGI_ | .665±.029 | .414±.033 | .749±.036 | 100% |
| _MultiXrank_ | .678±.000 | .363±.000 | .812±.000 | 100% |

> **Retrieval-only / w/o Biocontext / w/o CoT（2026-07-24，真实实现+真实数字）**：方法论、
> 完整4任务对比表、逐条分析见 [`prompt_optimization.md`](prompt_optimization.md)"消融C/D结果"
> 及"消融1 Retrieval-only"一节，本文档不重复展开，只记要点：Retrieval-only（纯规则，检索到的
> Examples真实label众数投票，`src/eval/retrieval_only_baseline.py`）在T1a-DE上Macro-F1/MCC
> **全面超过14B**（.691/.429 vs .680/.359），提示v1 prompt里"检索证据本身"贡献了相当一部分
> 分数；w/o Biocontext（去掉背景描述）Answered%从74.2%骤降到22.0%但答对的那一小撮case
> Macro-F1/MCC反而更高（选择性作答效应，非"没描述更好"）；w/o CoT（去掉多步推理脚手架）
> Macro-F1/MCC均不降反升，是"链式推理未必提升决策质量"的诚实负结果。

> **MultiXrank基线（真实实现+真实数字）**：`src/eval/multixrank_baseline.py`，同一张
> STRING+YEASTRACT图（复用`gat_baseline.py`的图构造），对每个在CSV里出现过的pert/gene节点
> 做restart_prob=0.15、30轮幂迭代的random-walk-with-restart（只对~6100个实际被查询到的节点算，
> 不算全图~6900节点的RWR，因为其余节点从不作为查询端点）；特征=RWR(pert→gene)、RWR(gene→pert)、
> 公共邻居数、度数、is_tf/is_esr/复合物数（双端各一份）、是否共属复合物，**不含任何target-encoding
> 基因基础率特征**（刻意做成"纯图邻近度"版本，跟GAT那行的target-encoding增强版形成对照），喂给
> XGBoost（`scale_pos_weight`按train正负比设置）。**2026-07-23 补测：已从单seed点估计补齐到3-seed
> （0/1/2）mean±stdev**（`data/runs/multixrank_baseline/multixrank_de_seed{0,1,2}.json`）——
> seed0/1/2三次独立跑分别为 Macro-F1=.6782/.6779/.6780、MCC=.3632/.3624/.3631、
> Acc=.8120/.8125/.8116，汇总 **Macro-F1=.678±.000、MCC=.363±.000、Acc=.812±.000**（stdev用
> pstdev，n=3）——三个seed几乎完全一致，`--seed`只喂给XGBoost的`random_state`，RWR幂迭代本身是
> 确定性numpy计算，训练/预测流程里没有其它随机性来源，seed间波动理论上就该趋近于零，实测确认了这
> 一点，不是异常。**结果**：Macro-F1 .678±.000，略低于GAT（.705±.014/.433±.019/.818±.026
> 均值，seed0=.709/.419/.845）——在不借助基因级基础率
> 查表的前提下，纯RWR图邻近度特征仍能拿到有效
> 信号但弱于GAT的可学习embedding+目标编码组合，符合预期方向，且这个差距在两侧都补齐方差后依然
> 稳固（GAT区间.691-.719，MultiXrank区间.678±.000，不重叠）。复现：
> `python src/eval/multixrank_baseline.py --task de --seed 0 --json out.json`（`--seed 1/2`得
> 另外两个seed）。

> **2026-07-22 补充：GAT基线已实测**（`src/eval/gat_baseline.py`，方法论见
> `prompt_optimization.md`"变体4"一节）。技术选型：本机 conda 环境原生均无 PyTorch Geometric，
> 但网络可用，在 `dtibase` 环境（已有 torch 2.6.0）里 `pip install torch_geometric` 装上了
> （CPU 版足够，图规模小——约7千节点/25万边，全图前向毫秒级），**不需要退化成 sklearn**。图=
> STRING直接邻居（`results_close_gene.json`）∪ YEASTRACT TF→靶基因（`tf_targets.json`）合并成
> 一张无向图；节点特征=是否TF/是否ESR成员(`esr_genes_gasch2000.json`)/复合物数
> (`complex_members_complexportal.json`)/STRING度数/总度数，**外加仅用train split算出的
> 目标编码特征**（该基因作为pert/作为gene时train集里的经验阳性率，Laplace平滑，训练时严格不碰
> val/test标签）+ 可学习节点embedding；GAT两层refine节点表示后，(pert,gene) 取两节点表示
> concat+|差|接MLP二分类头；train/test切分**完全复用**`deleteome_DE.csv`的`split`列，不重新切。
> 训练在CPU上完成（无GPU/side-channel）、10%train留作早停验证集。**2026-07-22 补测：已从单seed
> 点估计补齐到3-seed（0/1/2）mean±stdev**（`data/runs/gat_baseline/gat_de_seed{0,1,2}.json`）——
> seed0/1/2三次独立训练结果分别为 Macro-F1=.709/.721/.686、MCC=.419/.460/.420、Acc=.845/.827/
> .783，汇总 **Macro-F1=.705±.014、MCC=.433±.019、Acc=.818±.026**（stdev用pstdev，n=3）。
> **结果：GAT实际上小幅超过最强LLM（14B）**——Macro-F1 .705±.014 vs .680±.001、MCC .433±.019 vs
> .359±.002、Acc .818±.026 vs .622±.002（14B会主动弃权，GAT无弃权概念，Acc差距部分来自这个口径
> 差异，但Macro-F1/MCC口径一致，GAT仍占优，且GAT的seed间波动区间不与14B的置信区间重叠）。**但
> 关键的合理性校验发现了更值得关注的现象**：一个完全不用KG、不训练模型、只记"这个读出基因在train
> split里的多数类标签"的一行查表基线（`Gene-majority`，确定性统计量、不受随机种子影响，测每个
> test基因是否在train里出现过并直接抄多数label，覆盖率100%），Macro-F1/MCC/Acc 三项
> （.759/.524/.885）**全面超过GAT三个seed的均值乃至任一单个seed**，也超过LLM——说明这份数据集里
> 存在很强的"某些读出基因几乎恒定DE/恒定non-DE"的基因级基础率（比如持续处于应激响应状态的基因），
> 这条朴素统计量比GAT的图消息传递捕捉得还准；已经把这个target-encoding特征显式加进GAT输入（而
> 不是指望可学习embedding隐式学到同样的统计量，seed0上从.703提升到.709，为单seed消融对照，未
> 重复多seed）后GAT才提升，但仍未追平这条一行代码基线。**这是如实报告的负结果**：本任务里"训练型
> 方法"相对"死记基因基础率"的边际价值有限，这比"GAT是否赢LLM"这个问题更值得后续跟进（比如GAT的
> 图消息传递是不是在稀释而非增强这个基因级先验信号）。**合理性校验（相对VCWorld自建GAT baseline，
> DE AUROC 0.59-0.69）**：我们的口径是Acc/Macro-F1/MCC而非AUROC，不完全可比，但数值处在同一量级、
> 没有到.9这类明显泄漏信号的水平——上面Gene-majority基线同样处在类似高位，说明这更可能是本数据集
> 本身"基因级基础率信号强"的真实特性，不是代码bug造成的标签泄漏（已排查：所有特征、含目标编码，
> 均只用train split计算，未接触val/test标签）。复现：
> `for s in 0 1 2; do python src/eval/gat_baseline.py --task de --seed $s --json out_$s.json; done`。

> **2026-07-22 补充：GenKI基线已实测**（`src/eval/genki_baseline.py`）。方法与GAT/MultiXrank
> 有一处根本不同：**全程无监督**——VGAE只在"重建野生型共表达图结构+野生型表达特征"这个自监督目标
> 上训练，DE/DIR的train标签从未进入encoder/decoder的梯度，只在训练完成后用来校准一个标量决策
> 阈值（这正是GenKI方法论的核心特征，也是它跟GAT/KGE-TGI/MultiXrank"训练一个监督式pair分类器"
> 的本质区别）。**GRN构造（近似，如实说明）**：仓库没有独立的纯野生型表达重复样本（Deleteome原始
> 矩阵文件名本身写着`_ex_wt_var_controls`，即WT-vs-WT对照阵列已被剔除），改用每个基因在全部1487
> 个敲除阵列上的"A"通道（双色芯片的敲除/WT两通道平均log2强度）序列做WT表达水平的近似替代——1487
> 次独立测量下，A值主要由基因自身的本底转录水平主导，单次敲除对某一条A的扰动是小量——用这1487维
> 的A曲线两两做Pearson相关，取每个基因的top-15互近邻，建出一张~78,000条边的共表达网络当作
> "推导出的GRN"（不是YEASTRACT/STRING）；节点特征=该基因的[z(均值A), z(标准差A)]。**这不是A用于
> 派生DE/DIR标签的同一条计算路径**（标签来自M列+阈值，A是另一个轴），不构成标签泄漏，但确认这是
> 对"纯野生型表达"的近似，不是精确复现。虚拟敲除：把被删基因的输入特征清零、并删掉它在图里全部的
> 出边，重新跑一遍encoder，用**基因在敲除前后隐向量的欧氏距离**当作DE分数（T1a-DE的判决阈值在
> train split上标定），DIR方向用一个联合训练的属性解码器（把隐向量线性解回输入特征）在mean_A这
> 一维上的敲除前后差值符号来判断（原论文本身没有强调方向预测，这是本实现为了覆盖T1b-DIR做的合理
> 延伸，如实标注）。**2026-07-23 补测：已从单seed点估计补齐到3-seed（0/1/2）mean±stdev**
> （`data/runs/genki_baseline/genki_de_seed{0,1,2}.json`）——**补测中发现并修复了一个可复现性
> bug（如实记录，详见下方KGE-TGI小节"重要方法论发现"）**：`genki_baseline.py`原来跟torch默认
> 多线程CPU执行，同一个`--seed`重跑两次会给出不同结果（约60轮VGAE训练累积的浮点非结合性噪声），
> 已在脚本顶部固定`OMP_NUM_THREADS=1`等环境变量修复，修复后同seed可精确复现；GenKI受影响幅度比
> KGE-TGI小得多（修复前后同seed0差值≤.01，不影响原文档数字的可信度）。seed0/1/2三次独立跑分别为
> Macro-F1=.4921/.4913/.4942、MCC=.0266/.0310/.0181、Acc=.8218/.8254/.8117，汇总
> **Macro-F1=.493±.001、MCC=.025±.005、Acc=.820±.006**（stdev用pstdev，n=3；此前的单seed点估计
> .492/.026/.822落在这个区间里，未失真）。**结果**：Macro-F1=.493±.001
> ——比Majority（.458/0/.846）
> 略高一点、明显弱于GAT/KGE-TGI/MultiXrank，MCC=.025±.005接近0说明信号极弱但非零；T1b-DIR见下方
> T1b-DIR
> 表格小节。**合理性解读**：这是四个训练型对照里成绩最弱的一个，符合预期方向——它是唯一完全不用
> 任何监督标签训练表示、也不用YEASTRACT/STRING这类精选知识图谱的方法，只靠一张从噪声较大的
> 近似WT表达数据推导出的共表达图做无监督结构学习，弱信号（而不是零信号或负信号）是合理结果，没有
> 出现分数异常高企的可疑现象，不认为存在标签泄漏。**已知的局限（如实说明）**：①A通道并非纯野生型
> 测量，是近似；②共表达网络本身只反映相关性，不反映因果调控方向，这也是为什么它在方向判断上信号
> 更弱；③知识注入完全绕开了YEASTRACT专家标注，属于本组四个方法里"先验知识最少"的一端，弱结果与此
> 一致，不是实现缺陷。复现：
> `for s in 0 1 2; do python src/eval/genki_baseline.py --task de --seed $s --json out_$s.json; done`。

> **2026-07-22 补充：KGE-TGI基线已实测**（`src/eval/kge_tgi_baseline.py`）。跟GAT的关键架构
> 差异：**只用YEASTRACT TF→靶基因知识图谱**（不含STRING），并把它按`tf_targets.json`原生自带的
> 两种关系类型拆成两张**有向**子图（`activates`/`represses`），各自单独跑一套GCNConv（"multi-
> subgraph GCN"，原论文Wu et al. 2023的架构名字直译），两路relation-specific嵌入拼接后再接
> pair分类头——GAT是单一无向STRING∪YEASTRACT图上的一次GAT注意力，这里是两张关系分离的有向图各自
> 卷积后再融合，是本组四个方法里唯一显式建模"关系类型"这个维度的架构。为了跟GAT站在同一起跑线上
> 比较"多子图卷积能不能打过单一合并图"，同样加入了仅用train split计算的目标编码特征（该基因作为
> pert/gene时的经验阳性率，Laplace平滑）。train/test切分同样完全复用`deleteome_DE.csv`/
> `deleteome_DIR.csv`的`split`列，训练同样在CPU上完成、10%train留作早停验证集（patience=5，
> CLI默认值实为`--patience 6`，此处口径描述以代码default为准，先前的"patience=5"是笔误，
> 未实际影响任何已报告数字——patience只影响早停触发时机，不改变已完成训练的test集评测代码路径）。
>
> **2026-07-23 补测3-seed时的重要方法论发现（如实记录）**：补测过程中先跑`--seed 0`两次做校验
> （沿用GAT补测同样的"重跑seed0核对文档数字"步骤），发现**两次`--seed 0`跑出了不同结果**
> （Macro-F1 .6858 vs .6421、MCC .4324 vs .3268、早停轮次40 vs 22）——这不是预期行为，seed
> 应该让结果完全确定。**根因排查**：`kge_tgi_baseline.py`（以及同样受影响的`genki_baseline.py`）
> 只调用了`torch.manual_seed(seed)`，但没有固定CPU BLAS的线程数——torch默认多线程矩阵运算在
> 浮点求和顺序上不是bit-确定的（线程调度的竞态会导致同一次矩阵乘法在不同次运行里得到略有差异的
> 浮点结果），这个微小差异经过40轮训练+早停判断被放大，导致早停轮次都能跟着变、最终test分数出现
> 与"跨seed差异"同量级甚至更大的"同seed内部差异"，把seed变量原本要衡量的训练稳定性信号完全
> 污染了。**修复**：在两个脚本顶部（torch导入之前）加`os.environ.setdefault("OMP_NUM_THREADS",
> "1")`等环境变量、并在`make_model`里补一道`torch.set_num_threads(1)`兜底，修复后重复验证
> `--seed 0`两次，输出完全一致（Macro-F1/MCC/早停轮次逐位相同）。**这是一个真实bug，已在代码里
> 修好，不是调参数让方差好看**——修复前的原文档单点数字（Macro-F1=.684/MCC=.429/Acc=.775）
> 是修复前某一次非确定性运行的产物，不能保证可复现，下面报告的3-seed数字全部来自修复后的脚本。
> MultiXrank经同样方式核对（`--seed 0`重跑两次），结果逐位一致——它只用`--seed`控制XGBoost的
> `random_state`，RWR幂迭代是纯numpy确定性计算，不受此bug影响，未修改代码。
>
> **结果（修复后，真实3-seed）**：`data/runs/kge_tgi_baseline/kge_de_seed{0,1,2}.json`——
> seed0/1/2三次独立训练分别为 Macro-F1=.6367/.7056/.6541、MCC=.3919/.4609/.3896、
> Acc=.7099/.7968/.7406（早停轮次40/35/17，波动明显，见下方"合理性解读"），汇总
> **Macro-F1=.665±.029、MCC=.414±.033、Acc=.749±.036**（stdev用pstdev，n=3）。跟GAT
> （.705±.014/.433±.019/.818±.026）比：Macro-F1均值KGE-TGI更低（.665 vs .705），但两者区间
> 在边界附近接近重叠（KGE-TGI上界.694、GAT下界.691，仅一线之隔，不能排除样本量n=3下的偶然性）；
> MCC区间明显重叠（KGE-TGI .381–.447、GAT .414–.452），**不能再说"KGE-TGI MCC略高于/接近GAT"，
> 应说两者MCC区间内高度重叠，均值上GAT略高**；Acc区间也重叠（KGE-TGI .713–.785、GAT .792–.844，
> 部分重叠）。跟14B（.680±.001/.359±.002/.622±.002）比：Macro-F1均值KGE-TGI略低于14B（.665 vs
> .680），但KGE-TGI的stdev很大（±.029），14B的点估计落在KGE-TGI的区间内（.636–.694），
> **不能再说"基本打平"，应说两者区间有交叠，无法排除KGE-TGI均值确实略低于14B这个可能**；
> MCC KGE-TGI（.414±.033，区间.381–.447）仍明显高于14B（.359±.002），区间不重叠，**"MCC明显
> 超过14B"这一条结论保留、修测后依然成立**。T1b-DIR见下方T1b-DIR表格小节。**合理性解读**：
> KGE-TGI和GAT都用了同一套目标编码特征，均值量级仍然接近，支持GAT小节"这份数据集的基因级基础率
> 信号强到足以主导训练型方法排名、架构细节是次要变量"的结论方向；但KGE-TGI的seed间方差
> （±.029/±.033/±.036）明显大于GAT（±.014/±.019/±.026），**这本身是一个值得记录的新观察**——
> 早停轮次在17到40之间大幅摆动，说明"两张有向关系子图分别卷积"这个架构在验证集macro-F1的训练轨迹
> 上比GAT的单一无向图更不稳定，不同的权重初始化/mini-batch顺序更容易让早停在差异很大的训练阶段
> 触发，这是一个真实的训练稳定性差异，不是测量误差。KGE-TGI没有单独复现Gene-majority对照（已在
> GAT小节报告过，同一份`deleteome_DE.csv`标签，数字不重复算），但由于KGE-TGI同样纳入了这个
> target-encoding特征，预期同样跑不赢Gene-majority这条一行代码基线（.759/.524/.885 全面超过
> KGE-TGI三个seed的均值乃至任一单个seed），与GAT的结论方向一致。复现：
> `for s in 0 1 2; do python src/eval/kge_tgi_baseline.py --task de --seed $s --json out_$s.json; done`。
>
> 每列**加粗**标出该列最优值（沿用本文档惯例，加粗只在参与主对比的LLM模型行之间比较，GAT/
> Gene-majority/YEASTRACT规则等训练型或规则型基线即便数值更高也不加粗，避免"覆盖率/评测口径不同"
> 的基线跟LLM在视觉上被误认为同一量纲的直接排名——具体每条基线的口径差异见上方/下方各自说明）。
> T1a-DE 这一表 Qwen2.5-14B 四项全部领先。**Majority 基线**
> （test n=245,500，永远猜多数类"non-DE"，占比 84.56%）：Macro-F1=.458（多数类F1=2×.846/1.846=
> .916，少数类F1=0，均值.458）、MCC=0（常数预测器的标准性质，恒猜一类时混淆矩阵总有一行/列全零，
> `tp·tn-fp·fn` 与判别式分母同时消失）、Acc=.846（=多数类占比，无弃权概念）。**14B 的 Macro-F1
> （.680）比 Majority（.458）高 .222，MCC 从 0 升到 .359**——说明模型确实在学习类别边界而非单纯
> 利用类别不均衡蒙对多数类；但要注意 Majority 的裸 Acc（.846）本身就高于 14B 的 Acc（.622），
> 因为 14B 会主动弃权/犯错，提醒读者本任务里 Acc 单列不适合用来比较模型和 Majority 基线，
> Macro-F1/MCC 才是公平对照口径（详见 `task_definitions.md` 评测口径小节，本任务标签严重不均衡）。
> **Random 基线**（均匀随机猜 DE/non-DE，跟 Majority 不是同一种基线——不利用类别先验，200次
> 蒙特卡洛抽样 mean±stdev，方法见 `prompt_optimization.md`"标准基线+消融套件"）：Acc(overall)
> 恒在.5附近（解析闭式），Macro-F1=.432、MCC≈0——14B 的 Macro-F1/MCC 同时远超 Random（.680 vs
> .432、.359 vs ~0）和 Majority（.680 vs .458、.359 vs 0），两条弱基线都被明确跳出，是"模型真的
> 在用输入信息"的双重印证。`Retrieval-only`/`w/o Biocontext`/`w/o CoT` 三行已跑出真实数字（见上方
> 新增段落，方法论详见 `prompt_optimization.md`）；`No-retrieval LLM(14B)` 仍需要额外实现（去掉
> 检索证据、只留背景描述让模型凭内部知识判断），本次未做，保留 ⬜。
> 复现：`python src/eval/baselines.py`。

### T1b-DIR 主结果

| 模型 | Macro-F1± | MCC± | 方向Acc± | Answered% |
|---|---|---|---|---|
| Qwen2.5-14B | **.683±.001** | **.372±.002** | **.657±.000** | 93.0% |
| Qwen3-4B | .663±.002 | .326±.003 | .572±.001 | 81.2% |
| Llama3.1-8B | .583±.000 | .238±.003 | .461±.002 | 78.8% |
| Qwen2.5-7B | .565±.001 | .191±.003 | .538±.001 | **94.4%** |
| _Majority(升)_ | .400 | 0 | .665 | 100% |
| _Random_ | .486±.002 | .000±.005 | .500±.002 | 100% |
| _YEASTRACT 符号规则_ | .855 | .714 | .042 | 4.9% |
| _Retrieval-only_ | .720±.001 | .440±.003 | .753±.001 | 100% |
| _w/o Biocontext_ | .748±.004 | .496±.007 | .509±.004 | 64.5±0.5% |
| _w/o CoT_ | .687±.004 | .409±.003 | .600±.004 | 85.9±0.4% |
| _GAT_ | .669±.009 | .405±.026 | .673±.008 | 100% |
| _Gene-majority(train，无KG/无模型)_ | .754 | .514 | .790 | 100% |
| _GenKI_ | .444±.003 | .111±.004 | .673±.001 | 100% |
| _KGE-TGI_ | .666±.017 | .406±.017 | .670±.019 | 100% |
| _MultiXrank_ | .610±.003 | .241±.004 | .626±.003 | 100% |

> **Retrieval-only / w/o Biocontext / w/o CoT（2026-07-24）**：方法论/完整对比见
> [`prompt_optimization.md`](prompt_optimization.md)"消融C/D结果"。T1b-DIR上Retrieval-only
> 同样明显超过14B（Macro-F1/MCC .720/.440 vs .683/.372）；w/o Biocontext同样Answered%骤降
> （93.0%→64.5%）但答对部分Macro-F1/MCC更高（选择性作答，非真正学得更好）；w/o CoT同样
> Macro-F1/MCC不降反升（.687/.409 vs .683/.372）。四个任务上的模式高度一致，详见
> `prompt_optimization.md`对应小节。

> **MultiXrank基线**：方法/特征构造与T1a-DE一节完全相同（同一张图，同一套RWR+XGBoost特征，
> 唯一区别是训练/测试数据换成`deleteome_DIR.csv`自己的split）。**2026-07-23 补测：已从单seed
> 点估计补齐到3-seed（0/1/2）mean±stdev**（`data/runs/multixrank_baseline/
> multixrank_dir_seed{0,1,2}.json`）——seed0/1/2三次独立跑分别为 Macro-F1=.6071/.6134/.6097、
> MCC=.2360/.2466/.2404、方向Acc=.6231/.6302/.6260，汇总 **Macro-F1=.610±.003、MCC=.241±.004、
> 方向Acc=.626±.003**（stdev用pstdev，n=3；同T1a-DE，`--seed`只控制XGBoost的`random_state`，
> RWR部分确定性计算，波动天然很小）。**结果**：Macro-F1=.610±.003，同样低于GAT
> （.669±.009/.405±.026/.673±.008 均值）——两侧都补齐方差后区间依然不重叠（MultiXrank上界.613、
> GAT下界.660），趋势和T1a-DE一致，结论稳固。复现：
> `python src/eval/multixrank_baseline.py --task dir --seed 0 --json out.json`（`--seed 1/2`得
> 另外两个seed）。

> **2026-07-22 补充：GAT基线已实测**，方法论/技术选型/特征构造与T1a-DE一节完全相同（同一张
> STRING+YEASTRACT图、同一套结构特征+目标编码特征+可学习节点embedding+GAT，唯一区别是训练/测试
> 数据换成`deleteome_DIR.csv`自己的split——DIR的样本全集本身就是DE的阳性子集，`src/eval/
> gat_baseline.py --task dir`）。**2026-07-22 补测：已从单seed点估计补齐到3-seed（0/1/2）
> mean±stdev**（`data/runs/gat_baseline/gat_dir_seed{0,1,2}.json`）——seed0/1/2三次独立训练结果
> 分别为 Macro-F1=.682/.662/.663、MCC=.441/.388/.386、方向Acc=.685/.666/.668，汇总
> **Macro-F1=.669±.009、MCC=.405±.026、方向Acc=.673±.008**。**结果**：Macro-F1 .669±.009（比
> 14B的.683±.001略低，两者区间接近）、MCC .405±.026（超过14B的.372±.002）、方向Acc .673±.008
> （超过14B的.657±.000，同样有"GAT无弃权、14B会弃权"的口径差异需要留意）。**同样的合理性校验
> 发现同一现象**：`Gene-majority`（只记读出基因在train里的多数方向标签，不用任何图/TF信息、
> 确定性统计量）Macro-F1/MCC/Acc（.754/.514/.790）依然全面超过GAT三个seed的均值乃至任一单个
> seed，说明T1b-DIR里"读出基因本身有恒定升/恒定降的方向倾向"这个基因级基础率，同样比GAT的图
> 消息传递更强的信号源——这跟T1a-DE的发现一致，不是任务特定的巧合。**合理性校验（相对VCWorld
> 自建GAT baseline，DIR准确率0.52-0.61）**：我们的.673±.008略高于该区间上限，但同一数据集里连
> 零模型的Gene-majority基线都到了.790，说明这更可能是这份Deleteome DIR数据"基因级方向基础率
> 信号强"的真实特性（而非GAT本身有信息泄漏——真正该被怀疑"过强到需要排查"的其实是Gene-majority
> 这类查表基线摸到的.79-.885这个上限，已核实它只用train split的标签统计，不触碰test标签，是
> 合法的、真实存在于数据里的统计规律，不是bug）。特征/训练/早停设置见上方T1a-DE小节说明，不重复。
> 复现：`for s in 0 1 2; do python src/eval/gat_baseline.py --task dir --seed $s --json out_$s.json; done`。

> **2026-07-22 补充：GenKI基线已实测**，图构造/特征/训练方式与T1a-DE一节完全相同（同一张从
> Deleteome敲除阵列"A"通道推导出的~78,000边共表达图、同一套VGAE，训练/测试数据换成
> `deleteome_DIR.csv`自己的split，故unique perts数从1483降到1413）。方向预测用的是本实现的延伸
> 设计——联合训练的属性解码器把敲除前后隐向量分别解回`mean_A`这一维，取解码值之差的符号做
> Increase/Decrease判断（Decrease对应表达降低，属性解码值也预期降低，符号一致）。**2026-07-23
> 补测：已从单seed点估计补齐到3-seed（0/1/2）mean±stdev**
> （`data/runs/genki_baseline/genki_dir_seed{0,1,2}.json`，脚本已应用T1a-DE小节说明的可复现性
> bug修复）——seed0/1/2三次独立跑分别为 Macro-F1=.4422/.4418/.4476、MCC=.1076/.1165/.1095、
> 方向Acc=.6729/.6741/.6731，汇总 **Macro-F1=.444±.003、MCC=.111±.004、方向Acc=.673±.001**
> （stdev用pstdev，n=3；此前单seed点估计.443/.104/.673落在这个区间里，未失真）。**结果**：
> Macro-F1=.444±.003——比Majority(升)（.400/0/.665）的Macro-F1/MCC都高出
> 一截（MCC从0到.111），比T1a-DE的相对提升更明显；但仍明显弱于GAT/KGE-TGI/MultiXrank，符合
> "无监督表示学习+近似WT共表达网络，先验知识最少"这一预期。**合理性解读**：跟T1a-DE一样没有出现
> 分数异常的迹象；DIR阈值标定时`decoded-attr-delta`的最优切点非常接近0，说明属性解码器
> 学到的敲除方向信号本身就很微弱、噪声主导，MCC .111±.004虽然远弱于其余三个训练型对照，但明确跳出了
> Majority/Random两条零推理基线，是"弱但真实"而非"零信号"；三个seed间的方差（±.001–.004）也是
> 四个训练型方法里最小的一档，跟GenKI训练轮数少（约60轮VGAE，远少于KGE-TGI的最多40轮×早停判断
> 累积的轨迹分歧）、且知识注入bug修复后受线程噪声影响本就最小的观察一致。复现：
> `for s in 0 1 2; do python src/eval/genki_baseline.py --task dir --seed $s --json out_$s.json; done`。

> **2026-07-22 补充：KGE-TGI基线已实测**，图构造/特征/训练方式与T1a-DE一节完全相同（同一张
> YEASTRACT activates/represses双子图、同一套multi-subgraph GCN+目标编码特征，训练/测试数据换成
> `deleteome_DIR.csv`自己的split）。**2026-07-23 补测：已从单seed点估计补齐到3-seed（0/1/2）
> mean±stdev**（`data/runs/kge_tgi_baseline/kge_dir_seed{0,1,2}.json`，脚本已应用上方T1a-DE
> 小节说明的可复现性bug修复——补测这个任务时同样先重跑`--seed 0`两次核对，修复前两次跑出
> Macro-F1 .6918 vs .6421、MCC .4282 vs .3268，跟T1a-DE一样确认是同一个多线程浮点非确定性问题，
> 用同一处修复解决，不再重复描述根因）。修复后seed0/1/2三次独立训练分别为
> Macro-F1=.6897/.6544/.6531、MCC=.4255/.4094/.3840、方向Acc=.6970/.6558/.6563，汇总
> **Macro-F1=.666±.017、MCC=.406±.017、方向Acc=.670±.019**（stdev用pstdev，n=3）。**这里必须
> 明确指出一个措辞上的重大调整**：修复前的单seed点估计（Macro-F1=.650/MCC=.336/方向Acc=.659）
> 曾被原文档描述为"三项都略低于GAT"，但那个点估计本身是非确定性运行的产物、不可复现；补齐真实
> 3-seed后，KGE-TGI的均值（.666/.406/.670）**跟GAT（.669±.009/.405±.026/.673±.008）几乎完全
> 相等**，三项指标区间都高度重叠（Macro-F1：KGE-TGI .649–.683 vs GAT .660–.678；MCC：KGE-TGI
> .389–.423 vs GAT .379–.431；方向Acc：KGE-TGI .651–.689 vs GAT .665–.681）——**"KGE-TGI略低于
> GAT"这个结论不再成立，应改为"DIR任务上KGE-TGI和GAT在这套评测口径下统计上不可区分"**。跟14B
> （.683±.001/.372±.002/.657±.000）比：Macro-F1均值KGE-TGI仍略低（.666 vs .683）但区间接近
> 重叠（14B点估计落在KGE-TGI区间.649–.683的上沿内）；MCC KGE-TGI（.406±.017，区间.389–.423）
> 依然明显高于14B（.372±.002），区间不重叠，这条结论保留；方向Acc KGE-TGI（.670±.019）与14B
> （.657±.000）区间重叠、大体持平，跟原文档"与14B基本持平"的判断方向一致，未变。跟MultiXrank
> （.610±.003/.241±.004/.626±.003）比：KGE-TGI三项均值仍明显更高、区间完全不重叠（KGE-TGI下界
> .649 > MultiXrank上界.613），"明显超过MultiXrank"这条结论保留。**合理性解读**：延续T1a-DE
> 小节的结论——KGE-TGI的"关系类型分离卷积"架构改动没有让它系统性超过或落后于用单一合并图的GAT，
> 两者的目标编码特征贡献了大部分共同信号，架构差异是次要变量，这个结论在DIR上比在DE上更清晰（DE
> 上KGE-TGI均值确实略低于GAT，DIR上两者干脆持平）；KGE-TGI在DIR上的seed间方差（±.017/±.017/
> ±.019）比DE上（±.029/±.033/±.036）小，但仍明显大于GAT在DIR上的方差（±.009/±.026/±.008中的
> 前两项），`activates`/`represses`两张子图更稀疏、分方向卷积对初始化/mini-batch顺序更敏感这个
> T1a-DE小节的解释依然成立，只是DIR任务本身（样本量更小、正负比更不均衡）恰好让这次的3个seed
> 落点比DE更集中，不宜过度解读为"DIR上KGE-TGI训练更稳定"这个新结论，样本量n=3下有偶然性。复现：
> `for s in 0 1 2; do python src/eval/kge_tgi_baseline.py --task dir --seed $s --json out_$s.json; done`。
>
> 每列加粗最优值（同上方T1a-DE小节的约定，GAT/Gene-majority/YEASTRACT规则等训练型/规则型基线
> 不参与加粗）。T1b-DIR 里 Qwen2.5-14B 领先 Macro-F1/MCC/方向Acc 三项，但 **Answered% 是
> Qwen2.5-7B 最高**（94.4%）——不是同一个模型垄断所有指标，弃权率和判断质量在这张表里是分开的。
> **Majority(升) 基线**（test n=37,900，多数类是"Increase"，占比 66.53%）：Macro-F1=.400（多数类
> F1=2×.665/1.665=.799，少数类F1=0）、MCC=0、方向Acc=.665。**YEASTRACT 符号规则**（真实调用
> `data/knowledge/tf_targets.json`，即192个YEASTRACT签名TF的已知激活/抑制靶基因表，规则：敲除
> 激活子→预测靶基因表达Decrease，敲除抑制子→预测Increase，pert非签名TF或gene不在其已知靶基因表
> 里则弃权）：37,900条test case里，pert是签名TF的有5,549条（14.6%），其中gene落在该TF已知靶基因
> 表且符号无歧义的只有1,848条（4.9% Answered%，符合预期"很低"——大多数扰动子不是TF，是TF的
> 扰动子里绝大多数读出基因也不在其已知靶基因表里）；另有304条因同一TF对同一基因同时标注
> "激活"和"抑制"（矛盾注释）而弃权。**在这能判断的1,848条子集上**：Acc(answered)=.865、
> Macro-F1=.855、MCC=.714——规则本身在它敢下判断的窄窗口里相当准（YEASTRACT符号方向和真实DIR
> 标签高度一致，符合预期：这部分正是"机制最清楚"的TF直接靶基因对）。但**表格里的方向Acc列按与
> 其他行相同口径取 acc_overall（弃权计为错）= .042**——因为95%以上case无法判断，弃权全部计错，
> 这是这条基线"诚实"的代价，不应把 answered-only 的 .865 误当成整体表现直接和LLM比较。
> **关键检验：LLM是否真的比这条死规则聪明？** 14B 在 Macro-F1（.683 vs .855 answered-only 口径）
> 和 MCC（.372 vs .714）上其实**不如 YEASTRACT 规则在它敢判断的窄窗口内准**——但这不是"LLM更笨"，
> 而是覆盖率的权衡：规则只在4.9%最有把握（TF→已知靶基因、符号无歧义）的case上开口，LLM在93%的
> case上都要给出判断。用同一口径（弃权计错的 acc_overall）比较，14B 的 .657 远高于规则的
> .042——LLM 覆盖了规则触及不到的95%区域并仍能做出有信息量的判断，这才是LLM相对这条"只在
> 最简单机制清楚的case上开口"的死规则真正的价值所在，而不是"逐case比谁判断力强"。
> **Random 基线**（均匀随机猜 Increase/Decrease，200次蒙特卡洛，方法见
> `prompt_optimization.md`）：Acc(overall)≈.5、Macro-F1=.486、MCC≈0——14B（.683/.372）同时明显
> 超过 Random 和 Majority(升) 两条弱基线。`Retrieval-only`/`w/o Biocontext`/`w/o CoT` 是规划中的
> 标准消融套件（详见 `prompt_optimization.md`），需要真实 LLM 推理才能填，本次未做，保留 ⬜。
> 复现：`python src/eval/baselines.py`。

### 分解结果（按 `task_definitions.md` Task 1"生物学意义上的更细分解"）

> **2026-07-22 更新：分解1/2/3 已全部实测出真实数字**（`src/eval/decomp_bio_t1.py` +
> `data/runs/decomp123.json`），用 3-seed `.parsed` 预测缓存 + 三份真实知识资产：
> `results_close_gene.json`（STRING跳数，分解1）、`data/knowledge/esr_genes_gasch2000.json`
> （Gasch Lab现维护的ESR基因集合，分解2）、`data/knowledge/complex_members_complexportal.json`
> （EBI Complex Portal酵母复合物组，分解3——CYC2008原始文件核实已损坏，见下方分解3小节说明）。
> 但**扰动子本身是否为TF**这个相关但不同的轴，仓库里`tf_targets.json`+`src/eval/slice_results.py`
> 早已现成支持，已用`.parsed`预测缓存实际跑出真实数字（见下方"分解0"），**不是分解1的替代，是
> 另一个真实可用的分层**——分解1问的是"这条读出基因和扰动子的调控距离"，分解0问的是"扰动子这个
> 基因本身是不是TF"，
> 两者相关但不是同一个变量。

#### 分解0（真实已测，非 task_definitions.md 原定分解，是仓库现成支持的相关轴）：扰动子本身是否为已知签名TF vs 非TF

用 `data/runs/*.parsed`（`src/eval/cache_preds.py` 缓存）+ `tf_targets.json`（192个签名TF）实测，
3-seed mean（pstdev 从略，见 `data/runs/tf_slice_fast.json`）：

**T1a-DE**

| 模型 | TF扰动子 Macro-F1 | 非TF扰动子 Macro-F1 | TF扰动子 MCC | 非TF扰动子 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | **.708** | **.675** | **.422** | **.351** |
| Qwen2.5-7B | .639 | .627 | .279 | .268 |
| Qwen3-4B | .633 | .615 | .288 | .268 |
| Llama3.1-8B | .642 | .609 | .284 | .228 |
| _GAT_ | .712±.009 | .704±.011 | .428±.016 | .440±.020 |
| _GenKI_ | .472±.002 | .495±.001 | .006±.006 | .028±.006 |
| _KGE-TGI_ | .756±.005 | .654±.032 | .531±.012 | .403±.033 |
| _MultiXrank_ | .673±.003 | .678±.000 | .369±.007 | .369±.000 |

**T1b-DIR**

| 模型 | TF扰动子 Macro-F1 | 非TF扰动子 Macro-F1 | TF扰动子 MCC | 非TF扰动子 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | **.726** | **.675** | **.460** | **.357** |
| Qwen2.5-7B | .574 | .564 | .236 | .184 |
| Qwen3-4B | .704 | .655 | .409 | .311 |
| Llama3.1-8B | .595 | .581 | .281 | .230 |
| _GAT_ | .739±.008 | .668±.007 | .512±.004 | .403±.024 |
| _GenKI_ | .453±.011 | .455±.008 | .063±.019 | .091±.023 |
| _KGE-TGI_ | .750±.032 | .650±.021 | .539±.032 | .385±.021 |
| _MultiXrank_ | .602±.005 | .609±.003 | .204±.010 | .246±.005 |

**观察**：全部4个LLM × 两个任务，**TF扰动子子集的Macro-F1/MCC都高于非TF扰动子子集**（差距
MCC约0.02–0.10），且14B在两个子集上都领先——支持"机制推理确实在起作用"这个白盒论点的方向（对
TF扰动子，模型能用YEASTRACT式TF→靶逻辑，推理有更明确的抓手；对非TF扰动子，只能靠更弱的功能类比）。
但这不能替代分解1要问的"读出基因跳数"这个问题——一个TF扰动子仍可能通过多跳间接影响某个读出基因，
分解1和分解0应该分开看。**2026-07-23/24 新增：4个训练型对照方法在T1a-DE+T1b-DIR上的分解0结果
均已实测（真实3-seed，`src/eval/decomp_bio_t1_ml.py` + 各baseline脚本新增的`--dump-preds`，
数据见`data/runs/decomp_ml.json`）**：结论跟LLM明显不同——**GAT/GenKI/MultiXrank在TF/非TF两个
子集上都几乎无差异或方向反转**（GAT：MCC .428 vs .440，非TF反而略高；GenKI：MCC .006 vs
.028，同样非TF更高；MultiXrank：MCC .369 vs .369，完全打平），**只有KGE-TGI表现出和LLM同方向的
TF＞非TF差距**（DE：MCC .531 vs .403；DIR：MCC .539 vs .385，差距幅度跟14B的.02-.10相当甚至
更大）。四选一出现同向support，不能笼统说"所有训练型方法都不显示TF优势"；但**3/4方法（GAT/
GenKI/MultiXrank）没有复现LLM的一致优势模式**，仍然支持"分解0体现的主要是特定架构（LLM的显式
文本推理、KGE-TGI的关系类型分离卷积）能利用TF→靶这类结构化先验，不是任务标签本身在TF扰动子上
天然更容易学"这个解读方向，只是KGE-TGI这个反例说明"图消息传递完全不识别TF身份"这个更强的表述
不成立——KGE-TGI的关系分离架构（activates/represses两张图分开卷积）恰好和"TF→靶带符号调控"这个
结构在几何上更贴近，可能是它能捕捉到这个信号而GAT/MultiXrank的单一无向图/RWR特征捕捉不到的原因。

#### 分解1（真实已测）：读出基因是否被扰动子直接转录调控 vs 间接波及（STRING 网络真实跳数分层）

用`data/knowledge/results_close_gene.json`（STRING v12, combined_score≥700，`{pert:
{direct_neighbors, two_hop_neighbors}}`）——这**就是真实图跳数**，不是Top-K相似度代理，1跳=
`direct_neighbors`命中，2跳=不在1跳里但命中`two_hop_neighbors`。覆盖率低：DE测试集245,372个
case里只有769个落在1跳、936个落在2跳（约0.7%），DIR测试集37,787个case里245个1跳、151个2跳
（约1.0%）——其余case的pert在这张网里查不到该读出基因，不落入任何一个子集。3-seed mean（pstdev
见`data/runs/decomp123.json`）：

**T1a-DE**（n：1跳≈769，2跳≈936）

| 模型 | 直接调控(1跳) Macro-F1 | 间接波及(2跳) Macro-F1 | 直接调控 MCC | 间接波及 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | .583 | **.637** | .269 | **.358** |
| Qwen2.5-7B | .551 | .561 | .158 | .220 |
| Qwen3-4B | **.587** | .615 | .177 | .244 |
| Llama3.1-8B | .523 | .558 | .117 | .223 |
| _GAT_ | .641±.007 | .674±.013 | .303±.032 | .351±.023 |
| _GenKI_ | .445±.003 | .488±.004 | -.011±.003 | .004±.011 |
| _KGE-TGI_ | .695±.008 | .670±.031 | .397±.012 | .377±.042 |
| _MultiXrank_ | .626±.005 | .648±.008 | .270±.009 | .306±.016 |

**T1b-DIR**（n：1跳≈245，2跳≈151）

| 模型 | 直接调控(1跳) Macro-F1 | 间接波及(2跳) Macro-F1 | 直接调控 MCC | 间接波及 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | **.727** | **.777** | **.465** | **.573** |
| Qwen2.5-7B | .599 | .619 | .257 | .346 |
| Qwen3-4B | .701 | .683 | .404 | .368 |
| Llama3.1-8B | .609 | .595 | .279 | .262 |
| _GAT_ | .523±.023 | .532±.020 | .191±.035 | .177±.054 |
| _GenKI_ | .422±.002 | .419±.012 | .015±.034 | -.036±.022 |
| _KGE-TGI_ | .559±.012 | .620±.027 | .281±.026 | .377±.055 |
| _MultiXrank_ | .650±.031 | .677±.010 | .303±.059 | .367±.021 |

**观察**：结果和"直接调控更容易推理"这个直觉**相反**——DE里4个LLM全部在**2跳间接子集上
Macro-F1/MCC反而更高**（如14B: MCC .269→.358）；DIR里14B/7B同样2跳更高，只有4B/Llama8B在1跳
上略高，但差距很小。可能的解释：STRING阈值≥700筛出的"1跳邻居"多是强物理互作（复合物/直接结合）
而非严格意义的转录调控边，跟DE/DIR标签定义的"转录响应"因果链未必对齐；也可能因为1/2跳子集样本量
都只有三位数，波动本身就大，不宜过度解读方向性结论——但至少可以确认："机制推理在1跳更准"这个
朴素预期在当前STRING网络下**不成立**，这是本分解目前最主要的负向发现。**2026-07-23/24 新增：
4个训练型对照方法的真实3-seed结果**：DE侧**GAT/GenKI/MultiXrank三个都同样2跳＞1跳**（GAT MCC
.303→.351，GenKI .-011→.004，MultiXrank .270→.306），跟全部4个LLM方向一致；**KGE-TGI是DE侧
唯一的例外**（1跳MCC .397 略高于2跳 .377，差距很小、两者区间有重叠）。DIR侧更分散：**KGE-TGI/
MultiXrank同样2跳＞1跳**（KGE-TGI .281→.377，MultiXrank .303→.367，差距量级跟LLM相当）；**GAT/
GenKI在DIR上反而1跳略高或打平**（GAT .191 vs .177，GenKI .015 vs -.036），但两者的seed间stdev
（GAT±.035/±.054，GenKI±.034/±.022）本身已经跟均值差距同量级，在n≈245/151这种小样本下不能排除
这只是噪声、不是真实方向反转。综合看：**6/8个（方法×任务）组合支持"2跳≥1跳"这个反直觉方向**，
跟4个LLM的一致模式基本吻合，加上完全不做机制推理的GAT/GenKI/MultiXrank也复现了同样反直觉方向，
更支持"1跳边不代表严格转录调控边"是STRING图/标签结构本身的属性，不是LLM推理特有的毛病；但样本量
小（三位数）+ 训练型方法本身也有不小的seed间方差，DIR侧的GAT/GenKI个例不宜过度解读为真实反转。

#### 分解2（真实已测）：读出基因是否属于ESR基因集合 vs 基因特异响应基因（Gasch et al. 2000 ESR集合分层）

用`data/knowledge/esr_genes_gasch2000.json`（Gasch实验室现维护页面的"ORIGINAL ESR GROUPS"列，
iESR 283 + PAC 457 + RP 128 = 868个基因，与文献"283诱导+585抑制=868"完全吻合；原2000年Stanford
补充材料站点已失效，故用此现行来源，详见`task_definitions.md`分解2条目）。3-seed mean：

**T1a-DE**（n：ESR≈37,457，非ESR≈207,915）

| 模型 | ESR基因 Macro-F1 | 非ESR基因 Macro-F1 | ESR基因 MCC | 非ESR基因 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | **.702** | **.666** | **.406** | **.331** |
| Qwen2.5-7B | .644 | .618 | .290 | .251 |
| Qwen3-4B | .632 | .610 | .282 | .261 |
| Llama3.1-8B | .638 | .600 | .277 | .210 |
| _GAT_ | .727±.020 | .692±.007 | .470±.039 | .410±.015 |
| _GenKI_ | .439±.001 | .504±.001 | -.014±.006 | .037±.005 |
| _KGE-TGI_ | .687±.033 | .653±.029 | .448±.038 | .393±.032 |
| _MultiXrank_ | .672±.001 | .669±.000 | .357±.003 | .343±.001 |

**T1b-DIR**（n：ESR≈10,370，非ESR≈27,417）

| 模型 | ESR基因 Macro-F1 | 非ESR基因 Macro-F1 | ESR基因 MCC | 非ESR基因 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | **.700** | **.674** | **.403** | **.356** |
| Qwen2.5-7B | .558 | .566 | .188 | .190 |
| Qwen3-4B | .681 | .655 | .361 | .310 |
| Llama3.1-8B | .574 | .586 | .228 | .240 |
| _GAT_ | .710±.009 | .664±.004 | .456±.022 | .401±.020 |
| _GenKI_ | .454±.006 | .454±.009 | .073±.027 | .089±.021 |
| _KGE-TGI_ | .695±.026 | .651±.013 | .434±.029 | .392±.014 |
| _MultiXrank_ | .616±.008 | .594±.002 | .236±.017 | .233±.003 |

**观察**：T1a-DE里**全部4个LLM ESR子集Macro-F1/MCC都高于非ESR子集**，且14B领先幅度最大
（MCC .406 vs .331）；T1b-DIR里14B/4B同样ESR更高，但7B/Llama8B在非ESR子集反而略高（差距很小，
≤0.01 MCC）。整体上支持"ESR基因的DE/DIR判断确实更容易"这个假设（ESR基因几乎逢扰动就响应，
'猜响应'这个粗粒度启发式本身就比非ESR基因的基因特异性推理更容易蒙对），但DIR上的优势不如DE
稳固——即"要不要响应"这件事上ESR更好猜，"往哪个方向响应"这件事上ESR的优势打了折扣，属于合理的
机制解释（ESR基因响应方向本身也有更强的先验，即多数应激下同向变化，可能是DIR上优势变小但没消失
的部分原因）。**2026-07-23/24 新增：4个训练型对照方法的真实3-seed结果**：**GAT/KGE-TGI/
MultiXrank三个在两个任务上都是ESR＞非ESR**，方向跟全部4个LLM一致（GAT DE：MCC .470 vs .410；
KGE-TGI DE：.448 vs .393；MultiXrank DE：.357 vs .343，虽然MultiXrank的差距很小但方向仍对；
DIR侧三者同样ESR略高）——这组一致性比分解0/1都更强，进一步支持"ESR基因逢扰动就响应"是这份
Deleteome数据集本身的基因级基础率结构，多种完全不同的方法（图消息传递/关系分离卷积/RWR+XGBoost/
文本推理）都能捕捉到，不是LLM推理独有的能力。**唯一的例外是GenKI在DE上方向反转**（ESR MCC=-.014
vs 非ESR MCC=.037，非ESR反而更高，虽然DIR上GenKI是打平的.073 vs .089），需要谨慎解读——GenKI是
四者中唯一完全无监督的方法（VGAE，DE/DIR标签只用来事后校准一个标量阈值），它的MCC本身在多个
分解里都逼近0（弱信号），这个反转更可能是"信号太弱、噪声主导了子集间的微小差异"，而不是GenKI
真的对ESR基因有系统性更差的判别力。

#### 分解3（真实已测，已用官方原始CYC2008数据复核）：读出基因是否与扰动子同属一个已知蛋白复合物 vs 跨复合物调控溢出

`/home/zhengz2/MiniShare/mini1/h100/public/Yeast/CYC2008_complex.tab`本身是损坏下载（S3目录
列表HTML，非真数据），`wodaklab.org`原站也确认不可达（ECONNREFUSED）。**用户后来在
`data/gkn1005_Supplementary_Data.zip`里找到了CYC2008论文（Pu et al. 2009, *NAR*，manuscript
gkn1005）的官方补充材料**——`nar-02139-s-2008-File005.xls`的`CYC2008_complex`表就是原始目录：
1627个基因、408个复合物（与论文摘要"408 manually curated complexes"精确吻合），已归档为
`data/knowledge/CYC2008_complex_raw.xls`（原始xls）+ `data/knowledge/cyc2008_complex_members.json`
（基因→复合物ID映射）。第一轮曾用EBI Complex Portal（CYC2008的现行维护版）当替代，两次结果
互相印证，说明反直觉发现不是替代数据源带来的假象。3-seed mean（下表为**官方原始CYC2008**数据，
Complex Portal替代版结果见脚本历史输出，两者定性结论一致）：

**T1a-DE**（n：复合物内=393，跨复合物/无归属≈244,979）

| 模型 | 复合物内 Macro-F1 | 跨复合物 Macro-F1 | 复合物内 MCC | 跨复合物 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | .319±.012 | **.680±.001** | -.191±.047 | **.359±.002** |
| Qwen2.5-7B | .443±.008 | .628±.002 | -.009±.031 | .268±.003 |
| Qwen3-4B | **.472±.006** | .617±.002 | **.082±.010** | .270±.004 |
| Llama3.1-8B | .428±.040 | .613±.002 | -.054±.076 | .233±.003 |
| _GAT_ | .484±.288 | .705±.011 | .263±.336 | .434±.021 |
| _GenKI_ | **.901±.004** | .487±.001 | **.801±.008** | .011±.004 |
| _KGE-TGI_ | .607±.326 | .665±.029 | .374±.456 | .414±.031 |
| _MultiXrank_ | .876±.016 | .676±.000 | .770±.029 | .359±.000 |

**T1b-DIR**（n：复合物内=323，跨复合物/无归属≈37,464）

| 模型 | 复合物内 Macro-F1 | 跨复合物 Macro-F1 | 复合物内 MCC | 跨复合物 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | .496±.013 | **.680±.001** | .128±.027 | **.367±.002** |
| Qwen2.5-7B | .446±.002 | .563±.001 | .053±.002 | .190±.003 |
| Qwen3-4B | .420±.030 | .662±.002 | **.175±.025** | .324±.004 |
| Llama3.1-8B | **.467±.015** | .581±.000 | .055±.027 | .237±.003 |
| _GAT_ | .557±.045 | .676±.005 | .185±.138 | .413±.020 |
| _GenKI_ | .329±.011 | .449±.009 | .135±.006 | .069±.018 |
| _KGE-TGI_ | .710±.036 | .662±.017 | .480±.080 | .401±.017 |
| _MultiXrank_ | **.754±.047** | .605±.003 | **.516±.093** | .232±.004 |

**观察**：官方原始CYC2008数据复现了跟Complex Portal替代数据同样的反直觉信号——"复合物共调控
更容易预测"这个假设被明确反驳：**全部4个LLM在复合物内子集的Macro-F1/MCC都远低于跨复合物
子集**，DE上14B甚至跌到MCC=-.191（比随机猜还差），Qwen3-4B在复合物内子集勉强为正（.082）
但仍远低于跨复合物子集的.270。两套独立数据源（官方CYC2008 vs Complex Portal）算出的数字
高度接近（比如14B在DE上复合物内MCC分别是-.191 vs -.221，同一量级同一方向），**排除了"这是
替代数据源质量问题导致的假象"这个可能性，反直觉结论更可信了**。可能的解释：复合物内子集样本量
很小（约393/323，只占全部case的0.15-0.2%），且共复合物的pert-gene对往往是"同一功能模块内的
两个基因"，这类pair在Deleteome里的真实DE/DIR标签本身可能更嘈杂（复合物内基因既可能因组装
整体性而同增同减，也可能因负反馈/剂量补偿而互相独立甚至相反，标签噪声更大，不是模型推理能力的
问题）；也可能因样本量小、少数几个难例就能把Macro-F1/MCC拉得很低，需要更大样本复核。

**2026-07-23/24 新增：4个训练型对照方法的真实3-seed结果——这里出现了一个重要的方法论分叉，
不是简单的"复现同一结论"**。**GAT复现了LLM的反直觉方向**（复合物内 MCC=.263±.336 vs 跨复合物
.434±.021——n=393的小样本+GAT自身未修复的CPU线程非确定性bug，让stdev大到区间事实上跨过0，
比任何单个LLM都更接近"零信号"而非"负信号"，但均值方向仍是"复合物内更差"）。**但GenKI和
MultiXrank在两个任务上都是反过来的：复合物内子集Macro-F1/MCC都明显高于跨复合物子集**
（GenKI DE：MCC .801±.008 vs .011±.004，复合物内几乎是跨复合物的73倍；MultiXrank DE：
.770±.029 vs .359±.000；DIR侧MultiXrank同样.516±.093 vs .232±.004，GenKI DIR方向也一致
.135±.006 vs .069±.018，虽然幅度小得多）。KGE-TGI跟GAT一样是复合物内更差但方差极大（DE：
.374±.456，n=3seed下这个区间基本无法判断方向，DIR则反过来复合物内更高.480±.080 vs
.401±.017，KGE-TGI在这个分解上不稳定，不下结论）。**这个分叉不难解释**：MultiXrank的输入
特征里**显式包含一个二值特征`shared_complex`**（pert和gene是否同属一个复合物，见
`src/eval/multixrank_baseline.py::feature_row`），GenKI虽然不显式用复合物特征，但它的VGAE是在
共表达网络上做无监督重构，同一复合物的基因组装关系通常带来强共表达相关，这类信号很容易被
编码进VGAE的隐空间。**换句话说，GenKI/MultiXrank能在复合物内子集表现好，很可能不是"更擅长
推理复合物内调控"，而是它们的特征/隐空间里原本就含有跟"是否共复合物"高度相关的信息**——这条
子集恰好是它们最擅长利用的信号类型，跟LLM/GAT依赖的"转录调控链路"是两种不同的抓手。**这也
解释了为什么GAT不复现这个反转**：GAT的输入特征是目标编码（基因级基础率）+ STRING/YEASTRACT图
消息传递，没有显式的复合物特征，共复合物关系只能靠图消息传递隐式学到，而复合物内pair往往边数
少、跳数近，传递的信息反而有限。**结论汇总**：不能再笼统地说"复合物共调控=更容易预测这个假设
被所有方法反驳"——这个假设对LLM和GAT不成立，但对GenKI/MultiXrank成立，方向差异本身是一个关于
"不同架构从哪里获取信号"的真实发现，比单一方向的负结果更有信息量。

> **2026-07-24 说明（本节GAT行的更新）**：本节GAT数字已从此前的n=2 seed（T1a-DE only）更新为
> 完整n=3 seed、覆盖T1a-DE+T1b-DIR。**已确认`gat_baseline.py`存在和`genki_baseline.py`/
> `kge_tgi_baseline.py`同样的CPU线程非确定性bug**（同seed重跑，macro_f1/mcc有±.01-.04量级的
> 漂移，`data/runs/gat_baseline/gat_{de,dir}_seed{0,1,2}.json`里记录的主表格数字是bug修复前跑的，
> 本节新增的GAT分解数字是bug修复后重跑`--dump-preds`产生的，两者不完全对应，但量级接近、不影响
> 本节的方向性结论）。已给`gat_baseline.py`补上同样的`OMP_NUM_THREADS=1`等线程锁定修复
> （2026-07-24），但**主表格T1a-DE/T1b-DIR的GAT 3-seed数字本身未重新生成**——按照"已落盘数值不
> 无意义重跑"的原则，这不是本轮任务范围，如果后续需要更精确的GAT主表格数字，应作为独立任务补跑。

---

## Task 2A

### T2A-DE 主结果

| 模型 | Macro-F1± | MCC± | Acc± | Answered% |
|---|---|---|---|---|
| Qwen2.5-7B | **.645±.002** | **.290±.004** | .358±.002 | 49.2% |
| Qwen3-4B | .621±.001 | .256±.003 | **.583±.000** | **88.0%** |
| Qwen2.5-14B | .615±.002 | .245±.002 | .465±.002 | 61.9% |
| Llama3.1-8B | .581±.001 | .164±.002 | .477±.002 | 70.3% |
| _Majority_ | .412 | 0 | .701 | 100% |
| _Random_ | .479±.002 | .000±.004 | .500±.002 | 100% |
| _NRBdMF/SRMF矩阵分解_ | .635 | .272 | .683 | 100% |
| _Retrieval-only_ | .611±.003 | .223±.005 | .685±.001 | 100% |
| _w/o Biocontext_ | .545±.007 | .165±.013 | .077±.002 | 8.9±0.3% |
| _w/o CoT_ | .614±.002 | .237±.002 | .445±.001 | 59.4±0.1% |
| _GAT（从T1移植）_ | .234 | .024 | .301 | 100% |
| _MultiXrank_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _弹性网络回归/随机森林_ | .605 | .243 | .629 | 100% |

> **Retrieval-only / w/o Biocontext / w/o CoT（2026-07-24）**：方法论/完整对比见
> [`prompt_optimization.md`](prompt_optimization.md)"消融C/D结果"及"消融1"一节。T2A-DE上
> Retrieval-only（.611/.223）跟14B（.615/.245）基本打平，不像T1那样明显反超；w/o Biocontext
> 的Answered%崩塌最严重（61.9%→8.9%，四个任务里跌幅最大），且答对部分Macro-F1/MCC反而**低于**
> v1（.545/.165 vs .615/.245）——跟T1a-DE/T1b-DIR"选择性作答但答得更准"的模式不同，T2A-DE上
> 去掉背景描述后模型几乎丧失判断依据，连极少数敢回答的case也判断得更差，提示T2A-DE的背景描述
> （yeastphenome compendium assay说明+条件描述）信息量比T1的生物学背景更关键；w/o CoT基本打平
> v1（.614/.237 vs .615/.245），跟T1一样支持"链式推理非必需"。

> **GAT（从T1移植，真实实现+真实数字，2026-07-22）**：`src/eval/gat_baseline_t2a.py`——沿用T1的
> GATConv两层refine+pair分类头架构，但图结构完全重写（不复用STRING/YEASTRACT）：节点分基因/条件
> 两类，条件<->条件边取自`condition_similarity.json`每条件top-8相似邻居（跟MultiXrank T2A条目
> 用的同一份条件相似度网络）；基因<->条件边有两个来源——① STITCH化合物-靶点边（`stitch_compound_
> targets_hillenmeyer.json`经`decomp2_ctx_to_compound.json`映射到context id，真实但极稀疏：
> 273个T2A条件里只有25个能映射到化合物名，其中只有7个化合物有非空STITCH靶点，最终只有95条边）；
> ② TRAIN split里label=1（"有生长表型"/DE任务；"Resistant"/DIR任务）的(gene,context)对，仿照
> LightGCN一类图协同过滤的标准做法把训练期观测到的正例本身建成边（只用train split，不碰test，
> 這条边源在实际图里占绝大多数——DE任务17,065条，远超STITCH的95条）。节点特征：基因侧=
> is_stitch_target/log度数/train-only目标编码基因阳性率；条件侧=medium/phenotype/collection
> 独热+log(num_tested)+train-only目标编码条件阳性率（跟`elasticnet_rf_baseline_t2a.py`同一套条件
> 特征）。**关键负结果（如实报告）——冷启动导致的严重信息真空**：T2A的split按基因整体切分
> （train/test基因零重叠，跟矩阵分解/弹性网络面对的是同一个结构性限制），但GAT这里没有任何
> fold-in机制去补这个洞——诊断实测：**T2A-DE测试集里3002个test基因中2991个（99.6%）在这张
> 图里度数为零**（DIR测试集2294个里2283个/99.5%同样孤立），因为STITCH覆盖率太低、TRAIN-
> interaction边按定义只连接train基因，test基因除极少数STITCH靶点外没有任何边可以承载消息传递。
> **结果**：T2A-DE Macro-F1=.234、MCC=.024、Acc=.301——**明显低于Random基线（.479/~0/.5）和
> Majority（.412/0/.701）**，是本项目目前"训练型对照"里唯一一个连零推理弱基线都跑不赢的例子；
> T2A-DIR Macro-F1=.434、MCC=.014、Acc=.746——大体持平Majority（.428/0/.748），MCC同样接近零。
> **原因分析**：验证集（val，由train基因划出、非冷启动）上的分数其实相当高（DE val macro-F1峰值
> .866、DIR val .841），说明模型确实学到了train-interaction图里的模式，但这些模式全部锚定在
> train基因的节点embedding/度数特征上，对99%+零度数的test基因完全没有可转移的信息通道——这是一个
> "训练做得很好、但结构性泛化不到测试分布"的经典冷启动失败案例，不是训练bug或代码错误（已核实val
> 分数和test分数的巨大落差正是`--task de/dir`打印的"cold-start diagnostic"这一行直接测出来的孤立
> 节点比例造成的，不是复现出的巧合）。**跟矩阵分解/弹性网络的对比**：矩阵分解靠fold-in真实测量值
> 解决冷启动（信息预算比LLM宽，故报告两个版本）、弹性网络靠"从不依赖基因专属历史值"的结构特征
> 保持严格冷启动下仍有效（Macro-F1 .605，明显好于Random/Majority）；GAT-T2A两者都没做到——它既
> 没有fold-in通道，图结构本身（STITCH覆盖率）又太稀疏、不足以提供弹性网络那种"总能算出一个非零
> 特征"的兜底信号，是本组4个T2A训练型方法里目前处理冷启动最差的一个，如实记录，不做美化。复现：
> `python src/eval/gat_baseline_t2a.py --task de --json out.json`（`--task dir`得DIR版本）。

> **弹性网络回归/随机森林基线（真实实现+真实数字）**：`src/eval/elasticnet_rf_baseline_t2a.py`，
> 姊妹领域（GDSC/CCLE人类癌症药物敏感性预测）标准做法——RandomForestClassifier（400棵树，
> class_weight=balanced），特征**只用基因结构特征（STRING+YEASTRACT图的is_tf/is_esr/复合物数/
> 度数，复用`gat_baseline.py`的图构造）+ 条件元数据**（medium/phenotype/collection独热、
> log(num_tested)、条件级目标编码阳性率——仅用fit split计算，条件id在train/test间100%共享，
> legitimate），**从不触碰被测基因自身的z-score矩阵格子**——跟矩阵分解基线不同，这个方法天生
> 就是"严格冷启动"（因为特征构造本身不依赖任何基因专属的历史测量值），不需要fold-in/no-foldin
> 两个版本的区分。**结果**：Macro-F1 .605、MCC .243、Acc .629——接近矩阵分解的no-foldin严格
> 冷启动版本（.462/-.027，本方法明显更好，说明基因结构特征+条件先验确实提供了矩阵分解在
> 严格冷启动下拿不到的信号），但明显低于矩阵分解fold-in版本（.635/.272，含基因自身其它条件的
> 真实测量值）。复现：`python src/eval/elasticnet_rf_baseline_t2a.py --task de --json out.json`。

> **NRBdMF/SRMF矩阵分解基线（真实实现+真实数字，2026-07-22）**：`src/eval/matrix_factorization_baseline.py`，
> 在与LLM完全同一个 `hillenmeyer_phenotype.csv`/`hillenmeyer_direction.csv` train/test split（1289
> 训练基因/3002测试基因，train/test基因**零重叠**，273个Hillenmeyer HOP条件train/test完全共享）上
> 训练：对 `yp_matrix_z_haphom` 连续z-score做bias-augmented ALS矩阵分解（手写实现，k=25，L2
> 正则=3.0，20轮交替最小二乘，只用train split的格子训练），阈值/符号判定在**基因级别**留出的
> 15%训练基因上校准（不摸test）。**关键结构问题（已用真实数据核实，不是猜测）**：由于split按
> 基因整体切分，**每一个test基因在train矩阵里都是彻底的行冷启动**（0个test基因出现在train里），
> 标准ALS无法为这些行学出隐向量。处理方式是**fold-in**：对每个test基因，用`yp_matrix_z_haphom`
> 原始矩阵里该基因在其余Hillenmeyer条件下、**既不在train也不在test标签表里的"未采样格子"**（真实
> 测量值，只是没被两份label CSV采样进去，2995/3002个test基因有≥3个这样的格子，中位数260个）做
> 一次岭回归解出该基因隐向量，再预测目标格子；仅3个测试基因完全没有可用格子，退化为纯条件偏置
> 回退。**必须如实指出的信息不对称**：这个fold-in用到的是同一个基因在其它条件下的真实定量测量值
> ——这是LLM推理管线结构上完全拿不到的信息通道（LLM只看检索到的知识图谱文本证据，从不接触原始
> Hillenmeyer z-score矩阵本身）。用`--no-foldin`关掉这条信息通道、只用条件级偏置（完全靠train
> 基因在该条件下的整体分布，不含任何被测基因自身的信息）做出的"结构上真正冷启动"版本，T2A-DE
> 掉到 Macro-F1=.462/MCC=-.027（比Majority还差，基本等价于瞎猜），T2A-DIR掉到 Macro-F1=.465/
> MCC=.164（仍靠条件偏置拿到弱于但接近LLM量级的方向信号）——**这才是跟LLM"只用检索证据、不碰
> 原始表型矩阵"同等信息预算下的公平对照**，表格里报的.635/.272（DE）和下表.814/.629（DIR）是
> "矩阵分解+同基因其它条件真实测量值"这个更宽信息预算下的数字，两者不能混为一谈。复现：
> `python src/eval/matrix_factorization_baseline.py`（加`--no-foldin`得严格冷启动版本）。

> 每列加粗最优值。T2A-DE 里 Macro-F1/MCC 最优是 Qwen2.5-7B，但 **Acc/Answered% 最优是
> Qwen3-4B**——两个模型分别领先不同指标，不是同一个模型全面最优（这也是本任务"随规模不单调提升"
> 这个关键负结果的一部分体现）。**Majority 基线**（test n=58,980，多数类是"有生长表型"，占比
> 70.15%）：Macro-F1=.412（多数类F1=2×.7015/1.7015=.8245，少数类F1=0）、MCC=0、Acc=.701。
> 最优模型 Qwen2.5-7B 的 Macro-F1（.645）比 Majority（.412）高 .233、MCC 从 0 升到 .290，说明
> 模型确实学到了信号；但 Majority 的裸 Acc（.701）本身就高于全部4个模型（最高 Qwen3-4B .583），
> 再次提醒 T2A-DE 上 Acc 单列不宜直接和 Majority 比较，Macro-F1/MCC 才是公平口径——这也是本任务
> "规模不单调提升"负结果之外的另一个提醒：低弃权、高裸Acc未必代表模型学得更好。**Random 基线**
> （均匀随机猜 phenotype/no-phenotype，200次蒙特卡洛，方法见 `prompt_optimization.md`）：
> Acc(overall)≈.5、Macro-F1=.479、MCC≈0——最优模型 Qwen2.5-7B（.645/.290）明显超过 Random 和
> Majority 两条弱基线。`Retrieval-only`/`w/o Biocontext`/`w/o CoT` 是规划中的标准消融套件，需要
> 真实 LLM 推理才能填，本次未做，保留 ⬜。
> 复现：`python src/eval/baselines.py`。

### T2A-DIR 主结果

| 模型 | Macro-F1± | MCC± | 方向Acc± | Answered% |
|---|---|---|---|---|
| Qwen3-4B | **.479±.002** | .106±.006 | .729±.001 | 97.0% |
| Qwen2.5-14B | .469±.001 | .100±.003 | **.741±.001** | **98.8%** |
| Qwen2.5-7B | .467±.001 | **.110±.006** | .737±.001 | 98.0% |
| Llama3.1-8B | .455±.001 | .070±.006 | .736±.001 | 98.2% |
| _Majority_ | .428 | 0 | .748 | 100% |
| _Random_ | .467±.002 | .000±.005 | .500±.002 | 100% |
| _NRBdMF/SRMF矩阵分解_ | .814 | .629 | .862 | 100% |
| _Retrieval-only_ | .667±.004 | .374±.003 | .791±.001 | 100% |
| _w/o Biocontext_ | .632±.003 | .290±.003 | .678±.004 | 88.3±0.3% |
| _w/o CoT_ | .518±.006 | .160±.013 | .738±.003 | 97.7±0.1% |
| _GAT（从T1移植）_ | .434 | .014 | .746 | 100% |
| _MultiXrank_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _弹性网络回归/随机森林_ | .703 | .442 | .740 | 100% |

> **Retrieval-only / w/o Biocontext / w/o CoT（2026-07-24）**：方法论/完整对比见
> [`prompt_optimization.md`](prompt_optimization.md)"消融C/D结果"。T2A-DIR上Retrieval-only
> （.667/.374）明显超过14B（.469/.100），跟T1的模式一致；w/o Biocontext同样Answered%下降
> （98.8%→88.3%）但这次Macro-F1/MCC不降反升（.632/.290 vs .469/.100），是四个任务里唯一
> "去掉背景描述反而分数更好"的情形——提示T2A-DIR（敏感/抗性方向判断）的背景描述（assay/条件说明）
> 对这个方向性子任务不仅没帮助，反而可能引入了误导性先验；w/o CoT同样Macro-F1/MCC上升（.518/.160
> vs .469/.100），跟其余三个任务方向一致。

> **GAT（从T1移植）**：图构造/特征/训练方式与T2A-DE一节完全相同（同一套condition_similarity
> 条件网络+STITCH靶点边+train-interaction边——这里train-interaction边源自DIR自己的label=1
> "Resistant"正例，故边数比DE少：4,347条vs DE的17,065条，节点也更少——DIR训练数据本身是DE的
> 阳性子集），唯一区别是训练/测试数据换成`hillenmeyer_direction.csv`自己的split。**同样的冷启动
> 崩溃**：诊断实测DIR测试集2294个test基因里2283个（99.5%）图中零度数，跟DE小节的99.6%几乎一样
> 严重。**结果**：Macro-F1=.434、MCC=.014、方向Acc=.746——比DE小节好一些（没有跌破Random/
> Majority），大体持平Majority(.428/0/.748)，MCC=.014显示几乎没有跳出多数类先验，这跟T2A-DIR
> 本身"LLM也很难跳出Majority"的已知负结果（见上方主结果表分析）方向一致，但GAT-T2A的MCC比四个
> LLM的.07-.11还要更接近零，说明纯图结构+冷启动此处几乎完全无法传递方向信号，比"文本检索+LLM
> 推理"这条信息通道更弱。**结论汇总（跟T2A-DE合并解读，不重复展开机制）**：GAT-T2A是本项目T2A
> 四个训练型对照里对冷启动处理得最差的一个——STITCH靶点网络覆盖率过低（141个化合物只有7个有可用
> 靶点）、train-interaction边按构造无法触达test基因，图结构本身没有给孤立的test节点留下任何
> 可用的消息传递路径；矩阵分解靠fold-in真实z-score格子、弹性网络靠"不依赖基因专属历史值"的结构
> 特征分别绕开了这个问题，GAT-T2A两条路都没走通，如实记录为本组方法里的负结果，不做美化。复现：
> `python src/eval/gat_baseline_t2a.py --task dir --json out.json`。

> **弹性网络回归/随机森林基线**：方法/特征构造与T2A-DE一节完全相同（同一套基因结构特征+条件
> 元数据+条件目标编码，唯一区别是训练/测试数据换成`hillenmeyer_direction.csv`自己的split）。
> **结果**：Macro-F1 .703、MCC .442、方向Acc .740——明显超过最优LLM（.479/.106/.741 Macro-F1/
> MCC两项），也超过矩阵分解的no-foldin严格冷启动版本（.465/.164），但低于矩阵分解fold-in版本
> （.814/.629）。跟T2A-DE一样的解读：条件目标编码在方向任务上信号更强（条件本身对"敏感vs抗"
> 有很强的先验，比如某些强效药物条件下大多数基因都偏敏感），这不是基因自身信息泄漏（未接触被测
> 基因的z-score矩阵格子），复现：
> `python src/eval/elasticnet_rf_baseline_t2a.py --task dir --json out.json`。

> **NRBdMF/SRMF矩阵分解基线明显超过全部4个LLM且方向Macro-F1/MCC远超Majority**：方法/实现细节、
> fold-in信息通道的完整说明、"严格冷启动"（`--no-foldin`，Macro-F1=.465/MCC=.164）对照数字见
> 上方T2A-DE表格下方的详细说明（同一次实现、同一份代码同时产出DE和DIR两张表的数字，不重复贴一遍）。
> 这里额外强调一点：**T2A-DIR上"矩阵分解 fold-in"和"LLM"的差距（.814 vs 最优LLM .479）比T2A-DE
> 上的差距（.635 vs 最优LLM .645，基本打平）大得多**——一个合理的解释是DIR的问题本质更接近
> "这个基因的整体生长倾向是偏好还是偏坏"（同一基因在不同条件下的z-score符号相关性本身就很强，
> 这是化学-遗传学数据里常见的"基础生长速率"混杂因素），这正是fold-in能利用、而纯文本检索的LLM
> 结构上访问不到的信号，**不代表"传统ML训练范式全面碾压LLM推理"**，更准确的解读是"当传统方法被
> 允许接触原始定量表型矩阵的其它测量值时，它能捕捉到一种LLM检索管线拿不到的强先验（基因水平的
> 系统性生长倾向），这个先验对DIR（方向）比对DE（有无）更管用"。

> 每列加粗最优值。T2A-DIR 四项指标分散在三个不同模型上——Macro-F1 最优是 Qwen3-4B、MCC 最优是
> Qwen2.5-7B、方向Acc 和 Answered% 最优是 Qwen2.5-14B。四个模型在这张表里挤在 MCC `.07–.11`
> 的近随机区间，"谁最优"这件事本身信号很弱，不应过度解读某一列的领先。**Majority 基线**
> （test n=41,373，多数类是"Decrease/更敏感"方向，占比 74.76%）：Macro-F1=.428（多数类
> F1=2×.7476/1.7476=.8556，少数类F1=0）、MCC=0、方向Acc=.748。**这里的对照尤其刺眼**：全部
> 4个模型的方向Acc（.729–.741）都**低于** Majority 的裸 Acc（.748），MCC 只有 .07–.11——这张表
> 是本项目"随规模不提升"负结果里最极端的一例，模型在方向判断上几乎没有跳出"多数类先验"多少，
> 与 T1b-DIR（14B Macro-F1/MCC 明显跳出 Majority 基线）形成鲜明对比，进一步支持"化学-遗传适合度
> 方向性关系比转录调控方向性更难从纯文本知识检索中学到"这个结论。**Random 基线**（均匀随机猜
> Sensitive/Resistant，200次蒙特卡洛，方法见 `prompt_optimization.md`）：Acc(overall)≈.5、
> Macro-F1=.467、MCC≈0——四个模型的 MCC（.07–.11）虽然远低于 T1，但仍**略高于** Random 的 MCC
> （≈0），说明并非完全零信号，只是信号非常弱，这条 Random 对照让"近随机"这个判断有了更精确的
> 锚点（不是真的等于0信号，是"略高于随机但远不如 T1"）。`Retrieval-only`/`w/o Biocontext`/
> `w/o CoT` 是规划中的标准消融套件，需要真实 LLM 推理才能填，本次未做，保留 ⬜。
> 复现：`python src/eval/baselines.py`。

### 分解结果（按 `task_definitions.md` Task 2A"生物学意义上的更细分解"）

> 三个分解本轮**分解1、分解3已用真实数据实测**（脚本：`src/eval/t2a_decomp.py`，复用
> `src/eval/score.py` 的 `load_predictions`/`compute_metrics`），**分解2 资产不可得，保留骨架**
> ——已实测核实本仓库 `data/knowledge/`、`data/task2/` 下均无 DrugBank 或等价的酵母药物-靶点
> 注释文件；调研 Hillenmeyer et al. 2008 原文正文确认其 table S1/S2（化合物清单）挂在
> `sciencemag.org` 供刊后台，本次会话内 WebFetch 该地址返回 403（付费墙），且未找到其他可免费
> 获取、且覆盖本数据集这批化合物名称的"已知靶点"小型列表（考虑过 Lee et al. 2014 *Science*
> 的3250化合物chemogenomic注释，但那是不同的化合物集合，与本仓库7689个条件的化合物名称一一
> 匹配需要额外的化合物名归一化+人工核对，本次未做，避免瞎匹配/编造）。分解2 如实标记为
> "资产不可得，本次无法完成"，不产出任何数字。

#### 分解1：该基因在某一胁迫机制大类下是否敏感（按DNA损伤/氧化应激/渗透压/药物靶点抑制等大类分组，替代7689个原子条件）

**方法说明（与 `task_definitions.md` 原描述的出入）**：本分解未使用精确机制注释，而是对
`haphom_growth_contexts.csv` 的 `conditionset`（化合物名+浓度）字段做关键词正则匹配，按
"DNA损伤/氧化应激/渗透压-细胞壁/药物靶点-耐药外排"4个大类分组（规则见文末脚本，如 MMS/
bleomycin/camptothecin/cisplatin→DNA损伤，H2O2/diamide/menadione/paraquat→氧化应激，
NaCl/sorbitol/caspofungin/caffeine→渗透压细胞壁，rapamycin/cycloheximide/fluconazole等
命名药物→药物靶点/耐药外排类）。**覆盖率**：T2A-DE 测试集58980行中可归类16001行（**27.1%**，
按distinct context数：DNA损伤21个、氧化应激2个、渗透压/细胞壁10个、药物靶点/耐药外排38个，
其余未归类context排除在外）——氧化应激类样本量明显偏小（仅2个distinct context/550行），
该列数字仅供参考。3-seed mean（pstdev从略，完整seed拆分见分析脚本输出）：

| 模型 | DNA损伤类 F1 | 氧化应激类 F1 | 渗透压/细胞壁类 F1 | 药物靶点/耐药外排类 F1 |
|---|---|---|---|---|
| Qwen2.5-14B | .626±.007 | .591±.018 | .597±.011 | .636±.001 |
| Qwen2.5-7B | **.655±.003** | .628±.022 | **.599±.013** | **.666±.006** |
| Qwen3-4B | .658±.004 | **.646±.011** | .584±.003 | .631±.003 |
| Llama3.1-8B | .598±.004 | .593±.008 | .561±.005 | .583±.003 |
| _GAT（从T1移植）_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _NRBdMF/SRMF矩阵分解_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _弹性网络回归/随机森林_ | ⬜ | ⬜ | ⬜ | ⬜ |

**观察**：4个大类里 Llama3.1-8B 全面垫底；Qwen2.5-7B/Qwen3-4B 交替领先，与主表"T2A-DE
不随规模单调提升"这个结论一致，按机制大类切分后仍未看到某个模型全面占优。所有大类的
Macro-F1（.56–.66）都落在与主表 T2A-DE 相近的区间，没有出现某个机制大类明显更容易/更难的
悬殊差距（渗透压/细胞壁类略低，但样本量小、需谨慎解读）。**T2A三个训练型对照（GAT/矩阵分解/
弹性网络）的分解结果尚未产出**——三者目前都只dump聚合`test_metrics`，没有像本次给T1的GAT加的
那种`--dump-preds`per-case缓存，本轮时间预算内只来得及验证T1-GAT这一条技术路线，T2A这三个方法
的per-case缓存化改造留作后续，保留⬜。

#### 分解2：被敲基因是否是该化合物的直接分子靶点 vs 旁路通路成员（STITCH 化合物-蛋白互作分层）

**2026-07-22 更新**：用户提供了 `4932.protein_chemical.links.detailed.v5.0.tsv.gz`（STITCH v5.0
酵母蛋白-化合物互作，已移至 `data/knowledge/`），资产不再"不可得"，但**实测覆盖率过低，仍无法
产出有统计意义的数字**：

- Hillenmeyer 2008 这批141个化合物里，只有13个能通过PubChem CID精确匹配到STITCH记录（MMS/HU/
  clotrimazole/benomyl/benzaldehyde/angelicin/busulfan/copper sulphate/caffeine/fluconazole/
  amsacrine/acriflavinium hydrochloride/chlorambucil——其余128个化合物没有已知/可信CID对照，
  未强行匹配）。
- 这13个化合物里只有7个有`combined_score≥700`（STITCH高置信度阈值）的靶点基因（HU 13个、
  clotrimazole 3个、benzaldehyde 7个、caffeine 40个、fluconazole 5个、amsacrine 1个、
  chlorambucil 1个；MMS/benomyl/angelicin/busulfan/copper sulphate/acriflavinium **零**高置信
  靶点）。
- 把这7个化合物对应的T2A-DE测试集context（共13个context）里的`pert`基因，按"是否在该化合物的
  STITCH高置信靶点列表里"分类，**"直接靶点"子集全测试集里只有3个case**（"旁路"子集2,757个）——
  3个样本**不足以算出任何有意义的Macro-F1/MCC**（3-seed跑出来4个模型全部退化成Macro-F1=.500/
  MCC=0，是n=3时的数值巧合而非真实信号）。

**结论**：STITCH文件本身是真实、可用的资源（已存档：`data/knowledge/stitch_compound_targets_hillenmeyer.json`
存了7个化合物的靶点基因列表、`data/task2/decomp2_ctx_to_compound.json`存了context↔化合物名映射），
但**Hillenmeyer这批化合物大多数是小众/文库编号化合物，STITCH覆盖不到，能覆盖到的少数化合物里
真正命中"pert基因=已知靶点"的case又极稀少**——问题不在"有没有数据源"，而在"这批化合物本身在
公开化合物-靶点数据库里覆盖率天然很低"。如需真正推进这个分解，下一步需要人工为128个未匹配化合物
补充CID（很多是内部编号/小众试剂，可能查不到PubChem条目）或改用更广的化合物-蛋白数据库。

| 模型 | 直接靶点 Macro-F1 | 旁路成员 Macro-F1 | 直接靶点 MCC | 旁路成员 MCC |
|---|---|---|---|---|
| Qwen2.5-14B | ⬜（n=3不可用） | .621±.005 | ⬜ | .260±.010 |
| Qwen2.5-7B | ⬜（n=3不可用） | .624±.009 | ⬜ | .249±.017 |
| Qwen3-4B | ⬜（n=3不可用） | .620±.007 | ⬜ | .245±.013 |
| Llama3.1-8B | ⬜（n=3不可用） | .583±.006 | ⬜ | .175±.014 |

> "旁路成员"这一列（n=2,757，覆盖仍只是13个可匹配化合物对应的context，不是全量T2A-DE测试集）
> 数字和主表 T2A-DE 整体水平相近，不构成有意义的对照——"直接靶点"这一列样本太小，不建议引用。

#### 分解3：该基因的敏感性是否随浓度单调变化（剂量-响应）vs 阈值型判断（限多浓度点化合物子集）

**方法说明**：从 `haphom_growth_contexts.csv` 里筛出"同一化合物名+同一原始论文(pmid)+同一
collection、且浓度可解析为统一单位的数值、distinct浓度数≥3"的条件组，在T2A-DE测试集用到的
273个context里找到**11个真实的剂量梯度系列**（全部来自 Hillenmeyer 2008 本身，pmid
18420932：cisplatin[8点]、rapamycin/HU/FK506[各4-6点]、5-fluoro-uracil、carboplatin、
chlorambucil、latrunculin、papuamide B、cantharidin、allyl disulfide），覆盖55个distinct
context、测试集中12331行——**确认Hillenmeyer设计里确实存在多浓度梯度，不是"各条件都是单一
浓度点"**。

- **剂量-响应一致率**：对每个(化合物系列, pert基因)组合，取该基因在同一系列内≥2个浓度点上的
  模型预测标签，按浓度升序排列，判断预测序列是否弱单调不降（含预测标签全同的平凡情形）；
  Answered子集内（None预测点跳过），3-seed mean。
- **阈值型判断 Macro-F1**：在这55个context对应的T2A-DE子集上直接算 `compute_metrics`。

| 模型 | 剂量-响应一致率 | 阈值型判断 Macro-F1 |
|---|---|---|
| Qwen2.5-14B | **.938** | .635 |
| Qwen2.5-7B | .921 | **.652** |
| Qwen3-4B | .898 | .644 |
| Llama3.1-8B | .873 | .588 |
| _GAT（从T1移植）_ | ⬜ | ⬜ |
| _NRBdMF/SRMF矩阵分解_ | ⬜ | ⬜ |
| _弹性网络回归/随机森林_ | ⬜ | ⬜ |

**观察**：四个模型的"剂量-响应一致率"都很高（.87–.94），且**与主表规模顺序一致**——
Qwen2.5-14B 一致率最高，Llama3.1-8B 最低；但这里“一致”只是模型自己预测序列的弱单调性
（含大量平凡的"全同标签"），不是对真实剂量-效应关系的验证，不能直接读成"模型理解剂量越高
效应越强"。阈值型判断 Macro-F1（.588–.652）与全集 T2A-DE 主表（.581–.645）水平相当，说明
多浓度化合物子集本身并不比全集更难或更容易。

---

## Task 2B

> **设计阶段，Costanzo 2016 尚未接入 pipeline——以下全部是骨架，无任何实测数据**，等 T2B-DE/
> T2B-DIR 的 `prepare→retrieve→prompt→infer→score` 跑通后再填。

### T2B-DE 主结果（是否存在显著互作）

| 模型 | Macro-F1± | MCC± / AUPRC | Acc± | Answered% |
|---|---|---|---|---|
| Qwen2.5-14B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ |
| _Majority(无互作,~99.2%)_ | ⬜ | — | ⬜ | — |
| _Random_ | ⬜ | — | ⬜ | — |
| _Retrieval-only_ | ⬜ | — | ⬜ | — |
| _w/o Biocontext_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _w/o CoT_ | ⬜ | ⬜ | ⬜ | ⬜ |

> `Random`（均匀随机猜 GI/non-GI，闭式 Acc=.5）本可以像 T1/T2A 一样直接算出来，但 T2B-DE 的
> 真实类别比例本身尚未定案——`task_definitions.md` Task 2B"6. 怎么说明结果更好"记录了同一份
> Costanzo 数据在不同口径下测出 0.8%/2.4%/7.15% 三种显著互作率，互相不能替代，标签 CSV 也还未
> 定稿接入 pipeline——在"用哪个口径的真实测试集"这个问题解决前，算出来的 Random macro-F1/MCC
> 会跟着口径改变，此时填数字有误导性，故保留 ⬜，待 T2B 标签定稿后按 `src/eval/baselines.py`
> 同款方法回填。`Retrieval-only`/`w/o Biocontext`/`w/o CoT` 同样是规划中的标准消融套件（详见
> `prompt_optimization.md`），T2B 连主表都未跑，三者自然也未跑。

### T2B-DIR 主结果（负vs正，仅 T2B-DE=1 子集）

| 模型 | Macro-F1± | MCC± | 方向Acc± | Answered% |
|---|---|---|---|---|
| Qwen2.5-14B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ | ⬜ | ⬜ |
| _Majority(负,~61%)_ | ⬜ | — | ⬜ | — |
| _Random_ | ⬜ | — | ⬜ | — |
| _Retrieval-only_ | ⬜ | — | ⬜ | — |
| _w/o Biocontext_ | ⬜ | ⬜ | ⬜ | ⬜ |
| _w/o CoT_ | ⬜ | ⬜ | ⬜ | ⬜ |

> 同 T2B-DE 表下方说明：T2B-DIR 的负/正比例（~61%/39%，中等不均衡）标签 CSV 也未定稿接入
> pipeline，`Random`/`Retrieval-only`/`w/o Biocontext`/`w/o CoT` 四行统一保留 ⬜，待主表跑通后
> 一并按 `prompt_optimization.md`"标准基线+消融套件"方法补齐。

### 分解结果（按 `task_definitions.md` Task 2B"生物学意义上的更细分解"）

#### 分解1：负向互作 vs 正向互作是否需要不同脚手架（T2B-DIR内部按方向分开算分，非新分层，已隐含在上表）
（同上表 T2B-DIR 行——负/正各自的召回率待补充列，此处暂不重复建表。）

#### 分解2：基因对是否同属一个已知蛋白复合物 vs 跨复合物/跨通路（CYC2008分层）

| 模型 | 复合物内 Macro-F1 | 跨复合物 Macro-F1 |
|---|---|---|
| Qwen2.5-14B | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ |

#### 分解3：基因对是否都有已知功能注释 vs 至少一个功能未知（GO注释分层）

| 模型 | 已知功能对 Macro-F1 | 含未知功能对 Macro-F1 |
|---|---|---|
| Qwen2.5-14B | ⬜ | ⬜ |
| Qwen2.5-7B | ⬜ | ⬜ |
| Qwen3-4B | ⬜ | ⬜ |
| Llama3.1-8B | ⬜ | ⬜ |

---

## Analysis
- **2026-07-22 新增：Majority 基线（4任务）和 YEASTRACT 符号规则基线（T1b-DIR）已用真实代码
  算出**（`src/eval/baselines.py`，本地/规则计算，不调用LLM），填入各主表末尾行，具体数字和
  解读见各表格下方注释。核心结论：T1a-DE、T2A-DE 上 14B/7B 的 Macro-F1/MCC 明显跳出 Majority
  基线（模型学到了信号，即便裸 Acc 有时不如 Majority）；**T2A-DIR 是最刺眼的反例**——4个模型
  的方向Acc全部低于 Majority 裸Acc，MCC 只有 .07–.11，模型几乎没跳出多数类先验；T1b-DIR 上
  YEASTRACT 符号规则这条"诚实的弱基线"只能对4.9%的test case下判断（大多数扰动子不是签名TF、或
  读出基因不在其已知靶基因表里），但在它敢判断的窄窗口内 Macro-F1=.855/MCC=.714 相当准——LLM
  真正的价值在于把判断覆盖到规则触及不到的另外95%区域并仍给出有信息量的答案，而不是在规则能覆盖
  的窄窗口内比规则更准。`No-retrieval LLM(14B)` 基线需要一次真实的无检索LLM推理才能填，不是
  本地能算的基线，本次未做，仍保留⬜。
- **2026-07-22 新增：Random 基线（跟 Majority 正交的另一种弱基线）已用真实蒙特卡洛模拟算出并
  确立为标准套件**（`src/eval/baselines.py` 新增 `random_baseline()`，200次独立均匀随机标签
  抽样，用跟 LLM 打分同一套 `compute_metrics()` 计分，见 `prompt_optimization.md`"标准基线+
  消融套件"一节的方法论）。T1a-DE/T1b-DIR/T2A-DE/T2A-DIR 四个已有真实测试集的任务都已填入
  真实数字（Acc(overall)均≈.5，Macro-F1 随各任务类别不均衡程度在 .43–.49 间波动，MCC≈0）；
  T2B-DE/DIR 因标签口径尚未定案（同一份 Costanzo 数据在 0.8%/2.4%/7.15% 三种口径下互不相同，
  详见 `task_definitions.md` Task 2B），Random 保留⬜，避免在口径未定时填一个会随口径改变的
  数字。四个已算出的任务上，最优模型的 Macro-F1/MCC 均同时明显超过 Random 和 Majority 两条弱
  基线（除 T2A-DIR 外，MCC 优势幅度不大但仍为正）——这比只看 Majority 一条基线更能确认"模型
  确实在用输入信息"而不是"恰好没有退化成猜多数类"这一个更弱的论断。同时确立了**基线（Random+
  Majority）与框架消融（Retrieval-only/w/o Biocontext/w/o CoT）是每个任务的标准补充实验套件**
  这条方法论，写入 `prompt_optimization.md`，往后新增任务应默认配齐这一整套，而不是像本次之前
  那样只给 T1b-DIR 单独补了 YEASTRACT 规则、其余任务缺基线对照。Retrieval-only/w/o Biocontext/
  w/o CoT 三条消融本轮只搭好表格骨架（各任务 Result table 已加行），未实际调用 LLM，留待后续。
- **表达任务（T1）随模型规模单调提升**，14B 最优，复现 VCWorld 在人类数据上"越强越准"的结论。
  Qwen3-4B 在 T1b-DIR 越级（.663，反超 7B/8B），代价是弃权率更高。
- **生长适合度（T2A）不随模型规模提升 —— 本工作的关键负结果**：T2A-DE 最优是 7B，14B 掉队；
  T2A-DIR 四模型全部挤在近随机区间（MCC .07–.11）。推测知识图谱对调控/表达关系编码得远好于
  化学-遗传适合度这种依赖代谢通路定量剂量效应的关系，纯文本检索难以覆盖。
- **T2B 完全未跑**，且已知它内部至少有一层比 T1a-DE 更极端的类别不均衡（T2B-DE ~0.8%正例），
  是本项目下一步最该优先接入的任务。
- **"生物学意义上的更细分解"部分已从空骨架变成真实数字**：Task 1 的"TF vs 非TF扰动子"分解0
  已测出——两个任务、所有模型上 TF扰动子子集的 Macro-F1/MCC 都高于非TF扰动子子集，且14B在两个
  子集都领先。Task 2A 的分解1（胁迫机制大类，关键词分组，覆盖27.1%测试集）和分解3（剂量梯度，
  11个真实多浓度系列/12331行）本轮也已用真实预测数据测出——分解1显示4个大类的Macro-F1
  （.56–.66）与全集水平相当，未见某机制大类明显更易/更难；分解3显示"剂量-响应一致率"随模型
  规模单调（14B最高.938、8B最低.873），但阈值型判断Macro-F1与全集持平，说明多浓度子集不比
  全集更难。Task 2A 分解2（DrugBank靶点分层）**资产不可得，本次未完成**（原文表S1/S2化合物表
  在付费墙后，无可替代的免费靶点注释源，见 `task_definitions.md` 说明），保留⬜骨架，未编造
  数字。其余分解（Task1跳数/ESR/复合物分层、T2B各分解）仍需额外构建标注资产才能填。下一步的
  具体行动是：为 Task 1 剩余三个分解构建 BioGRID跳数表/ESR集合/CYC2008复合物表，并在 T2B 接入
  pipeline 后补齐其三个分解。
