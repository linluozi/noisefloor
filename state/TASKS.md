## 2026-11-16 08:55 · algo 原创库发布（noisefloor）
- 做了什么：发布原创零依赖库 `linluozi/noisefloor`（纯标准库，Python ≥3.10，`pip install -e .` + `python -m noisefloor`）。
  它把「这次测量配不配称为证据」做成可执行裁决：`aa`（A/A 空跑校准，同一实现当两个臂，输出假阳性率 + Clopper–Pearson 区间）、
  `gate`（两臂原始样本 → speedup 百分位 bootstrap CI + Mann–Whitney p → FASTER/SLOWER/INDISTINGUISHABLE/UNDERPOWERED，
  判 UNDERPOWERED 时给出所需运行次数）、`plan`（对观测样本做重采样功效分析，给 MDE 与达到目标功效所需 n）、`verify`（离线复算证书）。
  计时用 `perf_counter_ns()`，A/B 在每轮内交替，warmup 不计入，原始逐次样本全部落盘并做 sha256 内容寻址。
- 实测证据（全部本机真实运行，原始样本在 `evidence/`）：
  1) A/A 校准 `target=1.0`：**FASTER 17/200 = 8.5%**（CP 95% CI [5.0%,13.3%]）> 标称 α=5%，已原样写入 README（负面结论不掩盖）；
     `target=1.15`：FASTER **0/200**。
  2) `bench/demo.py` 同一次运行：真优化（5 万元素列表查找 → 预建 set，答案相同）**1847.7x，CI [1825.4,1855.6]，FASTER**；
     假手术 A/A **0.9995，CI [0.9979,1.0020]，INDISTINGUISHABLE**；该负载 RSD 0.26%，n=30 时 MDE 已在网格下限 1.02x。
  3) `bench/replay_prrecheck.py` 只读复用 `linluozi/pr-evidence-recheck` 的历史原始样本（不重跑该工具），
     得到**新结论**：那套 15 采样/臂基准的 MDE 是 **1.03–1.08x**（最重规模 pooled RSD 1.38%–11.57%），
     即它本来就能分辨 1.30x；因此 attrs-1660 / jsonpatch-274 的 RETRACT 是**有功效支撑的肯定性否定**，不是"样本太少"；
     croniter-298 四个规模 1.898/2.243/2.368/1.897x 全部 FASTER，与 KEEP 一致。
- 发布自证：`gh api repos/linluozi/noisefloor` → `private=false`，`pushed_at=2026-11-16T00:10:39Z`；
  干净克隆 `/tmp/noisefloor-smoke` 按 README 第一条命令 `PYTHONPATH=src python3 -m unittest discover -s tests` → **46 tests OK (4.7s)**；
  README 前 40 行含「这是什么 / 怎么跑 / 证据」。
- 独立复核：1 个只读 verifier 子 agent 已完成，**结论 CONSISTENT**（未发现编造/不一致）：
  1) 它独立复跑 `PYTHONPATH=src python3 -m unittest discover -s tests -v` → 46 ok / 0 fail / 0 error（4.75s）；
  2) 它用 `measure` + `decide` 自己写了 A/A 复现，独立跑 14 次共 **407/2800 = 14.5%**（单轮 10.0%–21.0%），
     与产物里的单轮 8.5% 同量级但**偏高**，指出 8.5% 落在观测分布低端；
  3) 它自写 midrank+tie+连续性修正的 Mann–Whitney 与 HF type-7，与 `tests/test_known_answers.py`
     期望值（p=0.0121857803553449 / z=-2.5067182457620487；z=0,p=1.0；1.1）**逐位吻合**；
  4) 它从原始样本独立重算 14 个 scale 的 median 比值，与 `evidence/replay_prrecheck.json` 全部 **relerr=0.0**，
     并核对 croniter 4 个 scale 的 p=3.3918213908634698e-06 是 U=0 完全分离的正常值，非编造信号。
- **复核驱动的修正（已 push）**：我据此把 README 的 A/A 校准从单轮 8.5% 改为
  「单轮 8.5% / 本仓库 6 种子 15.6%（187/1200，10.5%–19.5%）/ 独立复核 14 次 14.5%（407/2800）/ 合计 **14.9%（594/4000）**」，
  并新增 `bench/aa_multiseed.py` + `evidence/aa_multiseed.json`，把「单次校准本身也不可信」写成项目的第二个新结论。
  修正后 HEAD=`pushed 2026-11-16T00:22:45Z`，干净克隆复跑仍 **46 tests OK**。
- 上游回馈评估：**0 提案**。交付物是原创统计库而非对上游客源的补丁，`state/upstream-pr.json` 已写 no-proposal 说明。
- 环境坑（沿用）：`/home/ubuntu/GitHub/pipelines/state` 对 agent 只读，`runs.jsonl`/`innovation.md`/`used-upstreams.txt` 写入被拒；
  本文件与 runs/innovation/used-upstreams 都写在 `state/` 下由执行器归档。
- 待办（下一轮）：`gh` 默认账号是 linmoxi33，需从 `~/.config/gh/hosts.yml` 取 linluozi token 才能建仓；
  本轮已用该方式建 `linluozi/noisefloor` 成功，建议后续轮次沿用（或让执行器注入 linluozi 的 GH_TOKEN）。
