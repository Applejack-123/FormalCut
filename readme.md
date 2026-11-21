# FormaCut: 基于 Yosys 原生生态的形式化故障空间筛减工具

## 📖 项目简介

本项目为本科毕业设计《基于形式化验证技术的故障注入缩减技术研究》的核心原型工具。

针对宇航级芯片故障注入验证中“故障数量多、仿真开销大”的痛点，本工具借助开源形式化工具链（Yosys + SymbiYosys + SMT 求解器），实现了对数字电路**内部寄存器级**故障的自动化注入与静态筛减。工具能够在给定的输入约束和观察点下，剔除“已证明无观察影响”的无效故障，从而大幅降低后续故障仿真的时间开销。

当前版本已经完全走通 **Yosys 原生工具链**：故障注入使用 Yosys 内置 `mutate`，双副本比较和相等断言使用 Yosys 内置 `miter -equiv -make_assert`，证明使用 SBY + Yices，不再依赖 `fault_rtlil` 等外部插件。Python 只负责生成任务脚本、输入假设和“延迟注错”harness，不手写比较逻辑或断言。故障支持 **单 bit 永久翻转** 和 **单 bit 瞬时翻转** 两种时间语义，详细改造说明见 [docs/fault_timing_changes.md](docs/fault_timing_changes.md)。

## 🏗️ 技术架构与原理

传统 RTL 端口注入无法模拟真实 SEU（单粒子翻转），本工具在 **RTLIL（寄存器传输级中间表示）** 层完成故障建模。

1. **前端解析（Yosys）**：将 Verilog 源码解析为 JSON 网表，提取所有输入/输出端口以及内部触发器（`$dff`、`$adff`、`$sdff`、`$dlatch` 等）。对层级设计先执行 `flatten`，因此 TMR 等子模块内部的寄存器也能被逐个定位。
2. **单 bit 注入（Yosys `mutate -portbit`）**：对目标寄存器的 `Q` 端逐个 bit 注入故障，其他 bit 保持不变：
   - `inv`：SEU / bit-flip
   - `const1`：SA1 / stuck-at-1
   - `const0`：SA0 / stuck-at-0

   时间语义由 `--fault-timing` 控制：
   - `permanent`（默认）：从注错拍开始持续有效，对应永久 bit-flip / 固化 SA0/SA1；
   - `transient`：只在注错拍有效 1 拍，对应单粒子瞬态（SET/SEU 脉冲）。

   每个任务只包含一个 `mutate ... -portbit N`，CSV 中的 `cell,bit,fault,fault_timing` 四列可以直接看到注错位点和时间语义。例如对 `counter` 的 bit0 做 `inv`，变异网表中只有 `assign count[0] = ~...`；bit1 只有 `count[1]`，其余 bit 保持不变，不存在“整个寄存器一起翻转”的情况。
3. **双副本与 Miter（Yosys 内置）**：在同一个 Yosys 会话内分别构造故障副本和黄金副本，再用 `design -stash` / `design -copy-from` 把两者放在同一个设计中，最后用 `miter -equiv -flatten -make_assert` 生成标准等价比较器和相等断言。比较逻辑和 `$assert` 都由 Yosys 生成，不是 Python 手写的。故障副本先于黄金副本执行 `prep`，这样 `$procdff$N` 等自动单元名与 `extractor.py` 的解析结果完全一致。
4. **共同初态 + 延迟注错**：
   - `setundef -init -zero` 把两个副本中未显式初始化的触发器统一为 0，保证共同初态；
   - 对时序设计，故障副本增加一个 `formacut_fault_en` 控制端，黄金副本也通过 `add -input` 补上同名端口，保证 `miter -equiv` 的接口一致；
   - wrapper 用 `init_counter` 让 `formacut_fault_en` 在前 3 拍保持 0：`permanent` 模式下第 3 拍起一直为 1；`transient` 模式下第 3 拍为 1、第 4 拍回到 0；
   - 前 3 拍两个副本逻辑完全一致，因此**不可能在注错之前出现断言失败**；
   - 若开启自动约束且存在高有效 `rst`/`reset`，同样用这 3 拍完成复位，然后才释放复位并注入故障。
5. **等价验证（SBY + Yices）**：SBY 以 BMC 模式在指定深度内穷举输入，检查 Yosys miter 生成的 `$assert`：
   - 证明始终无差异（UNSAT） → **`PASS` / `PRUNED`（缩减）**
   - 找到反例（SAT） → **`FAIL` / `KEEP`（保留）**
   - 超时或未知 → **`UNKNOWN` / `TIMEOUT_KEEP`（保守保留）**

> `PASS` 的含义是“在给定约束和深度内不存在可观察差异”，是一种有界形式化证明。`--depth` 指**注错后**的观察拍数，SBY 总深度 = `depth + 3`（3 拍共同初态窗口）；遇到更大的电路时可以降低深度换时间，或增大 `--timeout` 换覆盖率。

## 📂 目录结构

```text
FormalCut/
├── circuits/              # 测试电路库（组合逻辑与时序逻辑）
│   ├── comb_adder/        # 4 位加法器
│   ├── comb_alu/          # 带掩码 ALU
│   ├── comb_test/         # 掩码测试
│   ├── itc99/             # ITC'99 基准（b01、observer_test 等）
│   └── seq_counter/       # 计数器、安全计数器、TMR 计数器、TMR 演示电路
├── core/                  # 核心自动化引擎
│   ├── extractor.py       # 端口与寄存器提取（prep + flatten + write_json）
│   ├── miter_builder.py   # 生成 Yosys mutate/miter 脚本与 SBY 任务
│   ├── runner.py          # 调用 SBY + Yices，解析 PASS/FAIL
│   ├── reporter.py        # 缩减率与耗时报表生成
│   ├── toolchain.py       # 自动定位 yosys/sby/yices（原生 OSS CAD Suite）
│   └── main.py            # 一键执行入口
├── workspace/             # 运行时生成目录（Yosys 脚本、SMT2 模型等，被 git 忽略）
├── reports/               # 最终输出的 CSV 与 JSON 报表（被 git 忽略）
├── docs/                  # 改造说明与设计文档
└── docker-compose.yml     # 可选的 Docker 统一启动配置
```

## 🛠️ 环境准备

### 方式一：原生 OSS CAD Suite（推荐）

安装 [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)，确保 `yosys`、`sby`、`yices-smt2` 在 `PATH` 中。工具也会自动探测以下安装位置：

```text
D:\EDA\oss-cad-suite\bin
C:\EDA\oss-cad-suite\bin
C:\oss-cad-suite\bin
/opt/oss-cad-suite/bin
/usr/local/bin
```

如果安装在其他位置，设置环境变量即可：

```powershell
$env:FORMACUT_TOOLCHAIN = "D:\path\to\oss-cad-suite\bin"
```

验证：

```powershell
yosys -V
sby --version
yices-smt2 --version
```

### 方式二：Docker（可选）

任何包含 `yosys`、`sby`、`yices` 的镜像都可以使用。以当前目录挂载到 `/workspace/FormalCut`：

```bash
docker-compose run formacut bash
```

`toolchain.py` 会自动在容器内的 `PATH` 中找到工具，脚本中的文件路径也全部相对项目根目录，因此原生环境和 Docker 环境可以共用同一套代码。

## 🚀 快速开始

### 1. 掩码观察点：100% 缩减

`observer_test` 的内部寄存器通过 `dummy & 1'b0` 接到输出，任何寄存器翻转都不会影响观察点：

```bash
python core/main.py circuits/itc99/observer_test.v observer_test flip false
```

预期结果：

```text
任务数: 2
PASS (PRUNED): 2
缩减率: 100.00%
```

### 2. 冻结状态下的 SA0：100% 缩减

计数器在 `en == 0` 时保持 0；对任意 bit 注入 SA0 都不会改变输出：

```bash
python core/main.py circuits/seq_counter/counter.v counter reset true "en == 1'b0"
```

预期结果：

```text
任务数: 4
PASS (PRUNED): 4
缩减率: 100.00%
```

### 3. 同一电路的 SEU：全部保留（验证 Miter 不是“永远 PASS”）

去掉约束后，bit-flip 在注错拍之后会传播到输出：

```bash
python core/main.py circuits/seq_counter/counter.v counter flip false
```

预期结果：

```text
任务数: 4
FAIL (KEEP): 4
缩减率: 0.00%
```

### 4. TMR 单 bit SEU：12/12 缩减

三模冗余的多数表决器会掩盖任意单个计数器的单 bit 翻转。用逗号分隔多个源文件：

```bash
python core/main.py "circuits/seq_counter/counter.v,circuits/seq_counter/tmr_counter.v" tmr_counter flip false
```

预期结果：

```text
内部寄存器: 3 个（每个 4 bit）
任务数: 12
PASS (PRUNED): 12
缩减率: 100.00%
```

### 5. TMR + 无保护输出：12 PRUNED / 4 KEEP（75% 缩减）

`circuits/seq_counter/tmr_demo.v` 是专门为直观展示筛减效果写的演示电路：三路计数器经过多数表决器输出 `out`，另有一个无保护的计数器输出 `raw`。单 bit SEU 在 TMR 侧被掩盖，在 `raw` 侧可观察，因此报表会同时出现 PASS 和 FAIL：

```bash
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false
```

预期结果：

```text
内部寄存器: 4 个（每个 4 bit，共 16 个 bit 位点）
TMR 的 12 个 bit 位点: PASS (PRUNED)
raw 的  4 个 bit 位点: FAIL (KEEP)
缩减率: 75.00%
BMC 深度: 8（3 拍初态窗口 + 5 拍注错后观察）
```

CSV 中每一行都有 `cell,bit,fault,status,decision,time,depth,inject_cycle`，可以直接看出“哪个寄存器的哪个 bit 被筛掉/保留”。16 行对应 4 个寄存器 × 4 个 bit，每个任务只改动一个 bit；如果整个寄存器一起翻转，就不会是 16 个独立的 PASS/KEEP 结果。

### 6. 瞬时 SEU 与永久翻转

同一个 `tmr_demo` 电路，用 `--fault-timing` 切换时间语义：

```bash
# 永久翻转：从第 3 拍起持续有效
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false --fault-timing permanent

# 瞬时翻转：只在第 3 拍有效 1 拍
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false --fault-timing transient
```

两种模式结果都是 12 个 TMR bit PRUNED、4 个 raw bit KEEP、缩减率 75%；差别在 `formacut_fault_en` 波形：

```text
permanent: 第 3 拍起一直为 1
transient: 第 3 拍为 1，第 4 拍回到 0
```

同一 `counter` 上的补充验证：

| 命令 | 结果 |
| --- | --- |
| `counter reset true "en == 1'b0" --fault-timing transient` | 4/4 PRUNED，100% |
| `counter flip false --fault-timing transient` | 4/4 KEEP，0% |

CSV 的 `fault_timing` 列会记录 `permanent` 或 `transient`。瞬时模式的详细实现、VCD 验证方法和语义边界见 [docs/fault_timing_changes.md](docs/fault_timing_changes.md)。

> 工具每次按顶层模块名覆盖 `<top>_report.csv`。本次为了保留对比，另存了 `reports/tmr_demo_transient_report.csv` 和 `reports/tmr_demo_transient_summary.json`；重跑时以主报表为准。

### 7. 安全模式下的 SA0

```bash
python core/main.py circuits/seq_counter/safe_counter.v safe_counter reset true "mode == 1'b1"
```

预期结果：

```text
任务数: 4
PASS (PRUNED): 4
缩减率: 100.00%
```

## ⚙️ 参数说明

```text
python core/main.py <电路文件[,电路文件2]> <顶层模块名> [故障类型] [是否加约束] [自定义约束] [--depth N] [--timeout S] [--fault-timing permanent|transient]
```

| 参数 | 说明 |
| --- | --- |
| 电路文件 | 单个文件，或用逗号分隔的多个 Verilog 文件 |
| 顶层模块名 | 电路的 top module |
| 故障类型 | `flip`（SEU）、`set`（SA1）、`reset`（SA0） |
| 是否加约束 | `true` / `false`；为 `true` 时自动加 `en == 1`，若存在 `rst`/`reset` 则先保持 3 拍复位再释放 |
| 自定义约束 | 原 Verilog 信号名书写的假设表达式，例如 `"mode == 1'b1"`；如果表达式中出现 `en`/`rst`，则不再自动添加对应约束，避免冲突 |
| `--depth N` | 注错后的观察拍数，默认 `5`；SBY 总深度为 `N + 3` |
| `--timeout S` | 单个 SBY 任务超时时间，默认 `600` 秒；超时按 `UNKNOWN / TIMEOUT_KEEP` 保守保留 |
| `--fault-timing {permanent,transient}` | 故障时间语义：`permanent` 从注错拍起持续有效（默认），`transient` 只在注错拍有效 1 拍 |

> 自动复位序列假设 `rst` / `reset` 为**高有效**。如果设计使用低有效复位（例如 `rst_n`），工具不会自动驱动它；请用自定义约束显式控制复位，或把端口命名为 `rst_n` 以避免被自动约束。

> **大电路的时间/收益权衡**：建议先用较小的 `--depth`（例如 3）跑一轮，拿到“当前深度下可缩减的故障下界”和逐任务耗时；再对感兴趣的故障或电路逐步增大 `--depth`。报表中的 `bmc_depth`、`inject_cycle`、`formal_time_sec` 和 CSV 的逐任务 `time` 可以直接用来评估继续加深是否值得。超时的任务会以 `TIMEOUT_KEEP` 保守保留，不会被误删。

## 📊 结果判定

| status | decision | 含义 |
| --- | --- | --- |
| `PASS` | `PRUNED` | 在约束和深度内证明触发条件不可满足，故障可被删掉 |
| `FAIL` | `KEEP` | 找到反例，故障可观察，必须保留 |
| `UNKNOWN` | `TIMEOUT_KEEP` | 求解超时或未知，保守保留 |
| `ERROR` | `ERROR` | 工具链、脚本或解析错误 |

报表输出：

- `reports/<top>_report.csv`：逐故障的 `task,cell,bit,fault,fault_timing,status,decision,time,depth,inject_cycle`
- `reports/<top>_summary.json`：故障模型、时间语义、总故障数、缩减/保留/未知/错误数、缩减率、BMC 深度、注错拍数、超时和总耗时

## 🧪 与旧版实现的差异

旧版 `miter_builder.py` 先用 `mutate` 写出一份 mutated Verilog，再在第二个 Yosys 进程里读回，并手写 wrapper 连接 `miter_circuit`。这带来两个实际问题：

1. **端口名不匹配**：`miter -equiv` 会把输入改名为 `in_<name>`，旧 wrapper 却连接 `.clk(clk)`、`.rst(rst)`，导致 miter 没有真正接上。
2. **初态不一致**：黄金副本和故障副本的触发器各自从任意初态出发，BMC 会在第一个比较点就产生与故障无关的反例。

当前实现改为：

- 在**同一个 Yosys 会话**中通过 `design -stash` / `design -copy-from` 保留两份 RTLIL；
- 用 `miter -equiv -flatten -make_assert` 生成标准 miter，比较逻辑和相等断言都由 Yosys 生成，wrapper 严格连接 `in_*`；
- 用 `mutate -port Q -portbit N` 做**逐 bit**注入，不再让整个寄存器一起翻转；
- 用 `setundef -init -zero` 对齐初态，并让 `formacut_fault_en` 在前 3 拍保持 0，保证**注错前不会出现断言失败**；
- 支持 `--fault-timing permanent`（注错拍起持续有效）和 `--fault-timing transient`（只持续 1 拍），分别对应永久翻转和单粒子瞬态；
- 不再有独立的 `yosys -p mutate` 步骤，`sby` 一次性完成“注入 + miter + 求解”。

## 🔎 故障注入工具调研

- **Yosys `mutate`**：本次采用的方案。`-port Q -portbit N` 直接选中寄存器 Q 端的单个 bit，`-ctrl` 提供外部使能，适合“同初态、延迟注错”的形式化流程；MCY 的变异覆盖同样基于这套 `mutate` 基础设施（[MCY Methodology](https://yosyshq.readthedocs.io/projects/mcy/en/latest/methodology.html)）。
- **uArchiFI `fault_rtlil`**：面向微架构级故障注入，支持对选中信号做故障注入和时序控制，但定位对象是 RTLIL 信号/线网，通常只能在 D/Q 端做整端口或信号级注入（[uArchiFI](https://github.com/CEA-LIST/uArchiFI)）。它更适合系统级、带时序攻击模型的实验，不是“寄存器单 bit”场景的最短路径。
- 结论：当前需求不需要额外引入插件；Yosys 内置 `mutate -portbit` 已经能做到单 bit。单周期瞬态已经通过 `--fault-timing transient` 的 `fault_pulse` 控制端实现；如果后续要求“严格翻转 FF 状态位、且与 D 无关也持续”，需要进一步做状态级注入（见 [docs/fault_timing_changes.md](docs/fault_timing_changes.md) 第 6 节）。

## 📊 核心实验结论

1. **观察点决定可缩减性**：`observer_test` 中寄存器物理上存在，但输出恒为 0，因此 2/2 故障被证明不可观察，缩减率 100%。
2. **环境约束决定可缩减性**：`counter` 在 `en == 0` 冻结时，SA0 故障全部被掩盖（4/4 PASS）；同一电路去掉约束后，SEU 故障全部可观察（4/4 KEEP）。
3. **冗余结构决定可缩减性**：纯 TMR 计数器对任意单 bit SEU 都能被多数表决器掩盖（12/12 PASS）；`tmr_demo` 同时包含 TMR 输出和无保护输出，结果为 **12 PRUNED + 4 KEEP = 75%**，能直观看出哪些故障被冗余掩盖、哪些仍然可见。
4. **时间语义可切换**：`tmr_demo` 在 `--fault-timing permanent` 和 `transient` 两种模式下都得到 12 PRUNED / 4 KEEP；瞬时模式的 `fault_pulse` 只在第 3 拍为 1，负向 raw 位的失败点仍在 `step 3`，第 0–2 拍没有失败。
5. **注错时刻可对齐**：在 `tmr_demo` 的负向用例中，SBY 的失败断言出现在 **step 3**，即 3 拍共同初态窗口之后；step 0–2 的断言全部通过，说明前 3 拍没有“未注错就失败”的假反例。
6. **缩减率是“约束 + 观察点 + 冗余结构 + 深度 + 时间语义”的联合结论**，不是电路的绝对物理属性。

## 📝 后续计划

- [ ] 接入 ITC'99 基准数据集，在更复杂的时序状态机上开展批量缩减实验。
- [ ] 开展持续型 bit-flip、单周期瞬态 SEU、状态级 SEU 三种模型在不同约束下的缩减率对比分析。
- [ ] 研究更严格的状态级 SEU 注入：直接翻转触发器状态位，使 D 与 Q 无关时也能持续，并与 uArchiFI 的时序故障模型做对比。
- [ ] 为大电路提供自适应深度策略：根据寄存器宽度、可达状态和单任务耗时自动选择 `--depth`，在时间成本与证明强度之间取折中。
- [ ] 开发基于 Web 的可视化 Dashboard（GUI），直观展示各类指标的统计柱状图。

## 📚 参考文献

1. Yosys `mutate` / `miter` 官方文档
2. SymbiYosys (SBY) 官方文档
3. Tollec, S., et al. "µArchiFI: Formal Modeling and Verification Strategies for Microarchitectural Fault Injections." FMCAD 2023.
4. Nasahl, P., et al. "SYNFI: Pre-Silicon Fault Analysis of an Open-Source Secure Element." IACR TCHES 2022.
