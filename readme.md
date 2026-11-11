
# FormaCut: 基于形式化验证的静态故障空间筛减工具

## 📖 项目简介
本项目为本科毕业设计《基于形式化验证技术的故障注入缩减技术研究》的核心原型工具。

针对宇航级芯片故障注入验证中“故障数量多、仿真开销大”的痛点，本工具借助开源形式化工具链（Yosys + SymbiYosys + SMT 求解器），实现了对数字电路**内部寄存器级**故障的自动化注入与静态筛减。工具能够在给定的输入约束和观察点下，剔除“已证明无观察影响”的无效故障，从而大幅降低后续故障仿真的时间开销。

## 🏗️ 技术架构与原理
传统 RTL 端口注入存在无法模拟真实 SEU（单粒子翻转）的缺陷。本工具利用 **RTLIL（寄存器传输级中间表示）** 层进行故障建模。

1. **前端解析（Yosys）**：将 Verilog 源码解析为 JSON 网表，精准提取所有输入/输出端口以及底层内部触发器（`$dff` / `$adff`）。
2. **底层注入（µArchiFI `fault_rtlil`）**：在 RTLIL 层对目标寄存器打上标签，并注入参数化故障（支持 `flip` 翻转、`set` 置 1、`reset` 置 0）。
3. **等价验证（Yices / Z3）**：生成正常电路与故障电路的 Miter 对比模型，转换为 SMT2 格式。求解器在设定的验证深度（Depth = 5）内穷举所有输入：
   - 若证明无差异（UNSAT） -> 标记为 **`PRUNED`（缩减）**。
   - 若找到反例（SAT） -> 标记为 **`KEEP`（保留）**。
   - 若超时或未知 -> 标记为 **`TIMEOUT_KEEP`（保守保留）**。

## 📂 目录结构
```text
FormalCut/
├── circuits/          # 测试电路库（包含组合逻辑与时序逻辑）
│   ├── comb_adder/    # 4位加法器
│   ├── comb_alu/      # 带掩码 ALU
│   └── seq_counter/   # 安全计数器与基础计数器
├── core/              # 核心自动化引擎
│   ├── extractor.py   # 端口与寄存器提取
│   ├── miter_builder.py # Miter 生成与 Yosys 注入脚本生成
│   ├── runner.py      # Yosys/Yices 调度与执行
│   ├── reporter.py    # 缩减率与耗时报表生成
│   └── main.py        # 一键执行入口
├── workspace/         # 运行时生成目录（Yosys 脚本、SMT2 模型等，被 git 忽略）
├── reports/           # 最终输出的 CSV 与 JSON 报表（被 git 忽略）
├── docker-compose.yml # Docker 容器统一启动配置
└── docs/              # 相关文献与技术文档
```
## 🛠️ 环境准备 (基于 Docker Compose)

为了保证底层插件（`fault_rtlil`）和 Yosys 环境的绝对一致性，本工具依托 Docker 运行，并使用 `docker-compose` 进行通用化挂载（自动识别当前目录，无需修改本地绝对路径）。

### 步骤 1：获取镜像
请确保本地已存在名为 `uarchifi` 的镜像。若没有，请前往 [CEA-LIST/uArchiFI](https://github.com/CEA-LIST/uArchiFI) 构建：
```bash
git clone https://github.com/CEA-LIST/uArchiFI.git
cd uArchiFI
docker build --tag uarchifi -f Dockerfile .
```

### 步骤 2：启动容器
回到本项目根目录（FormalCut），直接执行：
```bash
docker-compose run formacut bash
```
*（注：此命令会自动将当前项目目录挂载至容器内的 `/workspace/FormalCut`，并在容器内打开终端）*

## 🚀 快速开始

进入容器后，当前路径默认即为 `/workspace/FormalCut`。直接运行以下命令：

### 1. 基础测试（无约束环境）
对计数器进行内部寄存器 SEU 注入：
```bash
python core/main.py circuits/seq_counter/counter.v counter flip
```

### 2. 进阶参数配置
工具支持多维度的参数控制，格式如下：
```bash
python core/main.py <电路路径> <顶层模块名> [故障类型] [是否开启约束] [自定义约束]
```
*   **故障类型**：`flip`（SEU），`set`（SA1），`reset`（SA0）。
*   **是否开启约束**：`true` 或 `false`（若为 true，系统自动约束 `rst`, `en`, `mode` 等信号）。
*   **自定义约束**：直接传入 Verilog 形式的假设语句字符串。

**示例 A：验证特定安全模式（mask/mode）下的故障缩减**
```bash
python core/main.py circuits/seq_counter/safe_counter.v safe_counter flip true "mode == 1'b1"
```

**示例 B：验证系统冻结状态（en=0）下的故障缩减**
```bash
python core/main.py circuits/seq_counter/counter.v counter flip true "en == 1'b0"
```

### 3. 查看结果
运行完成后，结果保存在 `reports/` 目录下：
- `circuit_name_report.csv`：包含每一次故障注入的判定结果（PASS/FAIL）与耗时。
- `circuit_name_summary.json`：统计了总故障数、缩减数（PRUNED）以及最终的**缩减率**。

## 📊 核心实验结论
基于本工具的测试表明：
1. **无约束条件**：求解器穷举所有极端输入，内部故障均会传播至输出，被标记为 `KEEP`（缩减率 0%）。
2. **加入特定环境约束后**（例如 `assume(mode==1)` 或 `assume(en==0)`）：系统成功证明内部翻转被硬件机制掩蔽，标记为 `PRUNED`，实现了 **最高 100% 的故障缩减率**。
*这证明了：静态故障缩减率并非绝对物理属性，而是高度依赖于验证环境约束与观察点定义的数学结论。*

## 📝 后续计划
- [ ] 接入 ITC'99 基准数据集，在更复杂的时序状态机上开展批量缩减实验。
- [ ] 开展不同故障模型（SEU vs Stuck-at）在不同约束下的缩减率对比分析。
- [ ] 开发基于 Web 的可视化 Dashboard（GUI），直观展示各类指标的统计柱状图。

## 📚 参考文献
1. MCY (Mutation Cover with Yosys) 官方文档
2. Tollec, S., et al. "µArchiFI: Formal Modeling and Verification Strategies for Microarchitectural Fault Injections." FMCAD 2023.
3. Nasahl, P., et al. "SYNFI: Pre-Silicon Fault Analysis of an Open-Source Secure Element." IACR TCHES 2022.
```

