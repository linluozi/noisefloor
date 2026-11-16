# noisefloor — 先量出基准的噪声地板，再声称加速

`Upstream: none`

**一句话**：`noisefloor` 是一个零依赖的 Python 库 + CLI，它在你说出「这个改动快了 1.15x」之前，
先用 **A/A 空跑校准**（同一实现当两个臂）测出你这条基准的假阳性率，再用**重采样功效分析**算出这条
基准**最小能可靠分辨多大的效应**（MDE）以及**要跑多少次才能分辨 1.15x**。它给的是
`FASTER / SLOWER / INDISTINGUISHABLE / UNDERPOWERED` 四值裁决，而不是一个中位数比值。

这不是又一个 benchmark runner——它不负责跑你的代码（那是 `pyperf` / `asv` / `pytest-benchmark`
的活），它负责回答「**这次测量配不配称为证据**」。

## 为什么需要它

本仓库直接来自一个真实事故：某次优化用 **PyPI wheel 当 baseline、git HEAD 当 patched**，
跨树比较得出 `1.98x`，而同树复跑只有 `0.985x`。事故的根因不是"算错数"，而是**没有先量噪声地板**：
15 次采样/臂、相对标准差 1.4%–11.6% 的情况下，哪些结论站得住、哪些只是噪声，事前没人算过。

`noisefloor` 把这件事变成三条可复现的命令和一个显式裁决。

## 安装

零运行时依赖（纯标准库，Python ≥ 3.10）：

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
noisefloor --version
```

不想安装也可以直接 `PYTHONPATH=src python3 -m noisefloor ...`。

## 四条复现命令

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m noisefloor aa --trials 200 --rounds 30 --terms 3000 --n-boot 400 --target 1.0 --json-out evidence/aa_real_alpha.json
PYTHONPATH=src python3 bench/aa_multiseed.py
PYTHONPATH=src python3 bench/demo.py
```

## 实测结果（全部为本机真实运行，原始样本已落盘）

### 1) A/A 空跑校准（同一实现 vs 自己，200 次试验 × 30 采样/臂）

单次运行（`--target 1.0`）：

| 声明阈值 target | 判为 FASTER | 判为 SLOWER | 判为 INDISTINGUISHABLE | 假阳性率 |
|---|---|---|---|---|
| 1.00（标称 α=0.05） | 17 / 200 | 50 / 200 | 63 / 200（另有 70 UNDERPOWERED） | **8.5%**（Clopper–Pearson 95% CI [5.0%, 13.3%]） |
| 1.15 | 0 / 200 | 17 / 200 | 183 / 200 | **0.0%** |

**但单次 200 次试验本身就是一个噪声很大的估计量**，所以又跑了 6 个种子的多种子校准
（`bench/aa_multiseed.py`，同机同参数）：

| 校准 | FASTER / 试验数 | 假阳性率 | 跨种子波动 | 95% CP 区间 |
|---|---|---|---|---|
| 单次（上面那行，seed 20261116） | 17 / 200 | 8.5% | — | [5.0%, 13.3%] |
| 本仓库 6 种子（`evidence/aa_multiseed.json`） | 187 / 1200 | **15.6%** | 10.5% – 19.5% | [13.6%, 17.8%] |
| 独立复核者另跑 14 次（只读 verifier，非本仓库产物） | 407 / 2800 | **14.5%** | 10.0% – 21.0% | — |
| 合计 | 594 / 4000 | **14.9%** | — | — |

结论（真实测量，不是理论）：在我们这条交替 A/B + 百分位 bootstrap 的规则下，
**`n=30/臂`、`target=1.00` 时实际假阳性率约 13%–18%，是标称 α=5% 的约 3 倍**；
单次 8.5% 那一跑落在分布低端，**不应被当成「这条规则的校准值」**——校准本身也要多轮才可信，
这正是本项目要解决的问题的一个自指实例。阈值抬到 1.15x 后假阳性降到 0/200。
产物：`evidence/aa_real_alpha.json`、`evidence/aa_real.json`、`evidence/aa_multiseed.json`。

### 2) 真实优化 vs A/A 假手术（`bench/demo.py`，同一次运行）

| 臂 | 基线中位数 | 候选中位数 | speedup | 95% CI | 裁决 |
|---|---|---|---|---|---|
| 真实优化（5 万元素列表查找 → 预建 set，答案逐字节相同） | 855.84 ms | 0.463 ms | **1847.7x** | [1825.4, 1855.6] | **FASTER** |
| 假手术（同一实现跑两次） | 855.54 ms | 855.99 ms | 0.9995 | [0.9979, 1.0020] | **INDISTINGUISHABLE** |

同一次运行里同时得到「真优化被认出」和「A/A 不误报」。这条负载的实测噪声地板：
相对标准差 0.26%，`n=30` 时 MDE 已在扫描网格下限 `1.02x`，分辨 1.15x 只需 8 次采样
（网格下限，真实 MDE 更低）。产物：`evidence/demo_real.json`。

### 3) 复用真实历史样本：复核 `linluozi/pr-evidence-recheck` 的 15 采样/臂基准

不重跑那个工具，只读它保留的**原始逐次样本**（`evidence/raw/*.json`），问一个新问题：
*那套 15 采样/臂的基准，当时有没有能力分辨它要判的效应？*（最重规模，重采样功效，80 次试验/点）

| 数据集 | 最重规模 pooled RSD | n=15 时的 MDE | 分辨 1.30x 所需 n | 各规模 speedup | 1.30x 阈值下的裁决 |
|---|---|---|---|---|---|
| attrs-1660 | 11.57% | 1.08x | 8 | 0.965 / 1.023 / 0.985 | INDISTINGUISHABLE ×3（与 RETRACT 一致） |
| attrs-1660-flat | 2.53% | 1.03x | 8 | 0.988 / 0.985 / 0.982 | SLOWER ×1 + INDISTINGUISHABLE ×2 |
| croniter-298 | 1.38% | 1.03x | 8 | 1.898 / 2.243 / 2.368 | **FASTER ×4**（与 KEEP 一致） |
| jsonpatch-274 | 2.19% | 1.05x | 8 | 0.997 / 1.014 / 0.997 / 1.028 | INDISTINGUISHABLE ×4 |

**这是本轮真正的新结论**：那套 15 采样/臂的基准的 MDE 是 **1.03–1.08x**，
即它**本来就有能力分辨 1.30x**。所以 attrs/jsonpatch 的 RETRACT 不是"样本太少、测不出来"，
而是**肯定性的「那个量级的效应不存在」**——把原来只有"实测 0.985x"的结论，
升级成带功效证书的"视网膜上看得见 1.30x，但视野里没有"。
产物：`evidence/replay_prrecheck.json`。

## 证据闸门（每条都给了复现命令）

| 闸门 | 要求 | 实测 | 复现命令 |
|---|---|---|---|
| 测试全绿 | 单元测试 0 失败 | **46 tests, OK**（4.7 s） | `PYTHONPATH=src python3 -m unittest discover -s tests -v` |
| 一刀未剪 | 随机种子/采样数/原始样本全部保留，无事后挑选 | `evidence/*.json` 含逐次原始数组 + `samples_sha256` | `PYTHONPATH=src python3 -m noisefloor verify evidence/demo_real.json` 类证书校验见下 |
| 零依赖 | 不给用户加装包负担 | `dependencies = []`，仅标准库 | `pip install -e .` 后 `pip show noisefloor` |
| 证书可离线复算 | 原始样本 → 结论可重放 | `verify` 重新校验 sha256 与裁决 | 见 `tests/test_cli.py::test_verify_detects_tampered_samples` |
| 负面也要报 | 校准不过就写进结果，不掩盖 | 单次 8.5% → 多种子/独立复核后修正为 **14.9%（594/4000）**，两版都留在 README 与产物里 | `PYTHONPATH=src python3 -m noisefloor aa --target 1.0 ...` + `python3 bench/aa_multiseed.py` |
| 环境可追溯 | CPU/内存/解释器/种子 | AMD EPYC 7K62、3723 MB、Python 3.12.3、seed 20261116/424242 | 见下 |

## 环境

- CPU：AMD EPYC 7K62 48-Core Processor（4 vCPU）
- 内存：3723 MB
- 运行时：Python 3.12.3（本机仅有 3.12；3.10/3.11 不存在，**无法做三解释器交叉**）
- 种子：校准 `20261116`，功效分析 `424242`，demo `20261116`
- 计时：`time.perf_counter_ns()`；先 warmup（A/B 各 3 次，不计入样本）再采样

## 与既有工具的区别（诚实对照）

| 工具 | A/A 假阳性校准 | MDE / 所需运行次数 | 「本次测量能否支持 ≥1.15x」的显式裁决 |
|---|---|---|---|
| `pyperf` | 无 | 无 | 无（只给比值 + t 检验 + `--min-speed` 过滤） |
| `pytest-benchmark` | 无 | 部分（单臂 CI 精度自停） | 部分（`--benchmark-compare-fail` 阈值） |
| `asv` | 无 | 无 | 部分（`--factor` 回归报警） |
| `hyperfine` | 无 | 无 | 无 |
| Go `benchstat` | 无（文档只提醒 5% 名义错误率） | 无 | 无（给 CI + Mann–Whitney p 值） |
| **noisefloor** | **有（A/A 蒙特卡洛假阳性率 + CP 区间）** | **有（重采样功效，无分布假设）** | **有（四值裁决 + `UNDERPOWERED` 时给所需 n）** |

## 本轮创新

**B 档（新意）**：把「A/A 空跑校准」和「重采样功效/MDE」第一次接进微基准的**声明级裁决**，
并用它复核真实历史样本，得到一个可证伪的新结论：`pr-evidence-recheck` 那套 15 采样/臂基准的
MDE 只有 **1.03–1.08x**，因此它的 RETRACT 是**有功效支撑的肯定性否定**，而不是"样本不足"。
第二个新结论是自指的、由独立复核逼出来的：**校准量本身也有噪声**——单次 200 次试验给出 8.5%，
6 种子重跑给 15.6%（10.5%–19.5%），独立复核者另跑 14 次给 14.5%，合并 **14.9%（594/4000）**，
即这条规则的 `target=1.00` 假阳性率约为标称 α 的 **3 倍**，而**任何单次校准都不该被当成校准值**。
与既有工作的差别：`benchstat` 做 Mann–Whitney + CI 但不做 A/A 校准与功效；`pyperf`/`asv` 只做
跨版本比较；`perfclaim-guard`（我们自己的旧项目）是**运行时拒绝伪造的独立样本数/逐字节差分**，
判据是"证据本身是否伪造"，而本项目判据是"**这条基准的分辨率够不够得出这个结论**"——两者互补、不重叠。
`bench/demo.py` 用一次真实运行同时展示"真优化被认出"与"A/A 不误报"，`bench/replay_prrecheck.py`
把历史样本重新变成功效证书，`bench/aa_multiseed.py` 把"单次校准不可信"变成本仓库自己的反例。

## 已知局限（不藏）

- 功效/MDE 用**对观测样本重采样**估计（候选臂 = 基线样本 × 1/effect），假设测量分布形状在
  效应下不变；这是显式假设，不是无假设的真理。
- A/A 校准绑定**具体机器 + 具体 workload + 具体采样数**，换机器必须重跑（这正是要校准的原因）。
- **单次校准不可信**：200 次试验的单轮估计的标准误约 1.5–2.5 个百分点，实测跨种子在 10.5%–21.0%
  之间波动；请用 `bench/aa_multiseed.py` 的多种子合并值，并把它当作区间而不是点值。
- 独立复核（只读 verifier，非本仓库产物）在本轮给出：测试 46/46 通过、四种子的 Mann–Whitney
  known-answer 逐位吻合、14 个历史 scale 的中位数比重算 relerr=0.0、以及上面 407/2800 的 A/A 对照；
  结论 **CONSISTENT**，并指出单轮 8.5% 处于观测分布低端——该指出已被采纳并改写本节。
- 默认功效模拟的 `n_boot`（250–300）低于报告 CI 的 2000，分辨率换取时间，已在代码参数中暴露。

## License

MIT，见 `LICENSE`。本仓库为原创作品，不含任何第三方源码副本；`bench/replay_prrecheck.py`
只读取（不复制）另一个 linluozi 仓库 `linluozi/pr-evidence-recheck` 的公开原始样本。
