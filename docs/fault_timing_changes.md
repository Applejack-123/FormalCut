# 单 bit 瞬时翻转 / 永久翻转改造说明

## 1. 背景与目标

原实现只有一种故障时间语义：`mutate -ctrl formacut_fault_en 1 1`，其中
`formacut_fault_en` 从注错拍开始一直为 1。这更接近“永久 bit-flip / 固化翻转”，
不能表达“某一拍发生、之后不再持续”的瞬态 SEU。

本次改造增加了两种可选的单 bit 故障时间语义：

| 语义 | CLI 参数 | 含义 |
| --- | --- | --- |
| 永久翻转 | `--fault-timing permanent`（默认） | 从注错拍开始，故障一直有效 |
| 瞬时翻转 | `--fault-timing transient` | 只在注错拍有效 1 拍，之后恢复 |

两种语义都只作用于一个寄存器的 **一个 Q 端 bit**，不会整个寄存器一起翻转。

## 2. 时间语义定义

### 2.1 共同初态窗口与注错拍

时序设计默认有 3 拍共同初态窗口（`INIT_CYCLES = 3`）：

- 第 0–2 拍：`formacut_fault_en = 0`，两个副本逻辑完全一致；若开启约束且存在
  高有效 `rst`/`reset`，这 3 拍同时保持复位。
- 第 3 拍：注错拍，`formacut_fault_en` 按所选语义产生波形。
- 第 3 拍之后：进入注错后观察窗口。

因此，断言不可能在注错之前失败；负向用例的失败点固定出现在 `step 3`。

### 2.2 永久翻转（permanent）

```verilog
reg [1:0] init_counter = 2'b00;

always @(posedge clk) begin
    if (init_counter < 2'b11)
        init_counter <= init_counter + 1'b1;
end

wire formacut_fault_en = (init_counter == 2'b11);
```

`init_counter` 饱和在 3；从第 3 拍开始 `formacut_fault_en` 一直为 1。
适合建模：

- `inv`：永久取反 / 固化 bit-flip；
- `const1`：永久 SA1；
- `const0`：永久 SA0。

### 2.3 瞬时翻转（transient）

```verilog
reg [1:0] init_counter = 2'b00;
reg fault_pulse = 1'b0;

always @(posedge clk) begin
    if (init_counter < 2'b11)
        init_counter <= init_counter + 1'b1;
    fault_pulse <= (init_counter == 2'b10);  // 2
end

wire formacut_fault_en = fault_pulse;
```

`fault_pulse` 只在第 3 拍为 1，第 4 拍回到 0：

| 拍数 | init_counter | permanent `fault_en` | transient `fault_en` |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 0 |
| 1 | 1 | 0 | 0 |
| 2 | 2 | 0 | 0 |
| 3（注错拍） | 3 | 1 | 1 |
| 4 | 3 | 1 | 0 |
| 5 | 3 | 1 | 0 |

### 2.4 故障注入命令本身不变

两种时间语义共用同一条 Yosys 注入命令，只是控制端波形不同：

```tcl
mutate -mode inv -module <top> -cell <cell> -port Q -portbit <N> \
       -ctrl formacut_fault_en 1 1
```

`-portbit N` 保证只改目标寄存器的第 N 个 Q 位；`-ctrl` 提供外部使能，
使故障可以在共同初态窗口之后才生效。

## 3. 代码修改点与具体功能

### 3.1 core/miter_builder.py

| 修改点 | 具体功能 |
| --- | --- |
| 新增 `FAULT_TIMINGS`、`FAULT_TIMING_LABELS` | 定义并校验 `permanent` / `transient` 两种语义 |
| `_build_wrapper(..., fault_timing)` | 根据语义生成 `init_counter`、`fault_pulse` 和 `formacut_fault_en` 波形 |
| `_build_ys(..., fault_timing)` | 在任务 `.ys` 注释中记录时间语义；注入命令仍是 `mutate ... -ctrl` |
| `build_miter(..., fault_timing="permanent")` | 校验参数、生成 wrapper、把 `fault_timing` 写入任务元数据并打印 |
| 任务字典 | 新增 `fault_timing`，供 runner/reporter 写入报表 |

永久模式下生成的 wrapper 关键片段：

```verilog
wire formacut_fault_en = (init_counter == 2'b11);
```

瞬时模式下生成的 wrapper 关键片段：

```verilog
reg fault_pulse = 1'b0;
always @(posedge clk) begin
    if (init_counter < 2'b11)
        init_counter <= init_counter + 1'b1;
    fault_pulse <= (init_counter == 2'b10);
end
wire formacut_fault_en = fault_pulse;
```

对组合逻辑设计（没有 `clk`）没有“拍”的概念，wrapper 直接把
`formacut_fault_en` 置 1；`--fault-timing` 对组合逻辑不产生额外差异。

### 3.2 core/main.py

| 修改点 | 具体功能 |
| --- | --- |
| `run_pipeline(..., fault_timing="permanent")` | 把时间语义一路传给 `build_miter` |
| `--fault-timing {permanent,transient}` | 新增 CLI 参数，默认 `permanent` |
| 启动日志 | 打印当前时间语义、注错后深度和单任务超时 |

使用方式：

```bash
# 永久翻转
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false \
    --fault-timing permanent

# 瞬时翻转
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false \
    --fault-timing transient
```

### 3.3 core/runner.py、core/reporter.py

| 修改点 | 具体功能 |
| --- | --- |
| `runner.run_all_tasks` | 每个 result 增加 `fault_timing` 字段 |
| `reporter.save_reports` | CSV 增加 `fault_timing` 列；JSON summary 增加 `fault_timing` |

CSV 目前为：

```text
task,cell,bit,fault,fault_timing,status,decision,time,depth,inject_cycle
```

JSON summary 中包含：

```json
{
  "fault_model": "inv",
  "fault_timing": "transient",
  "bmc_depth": 8,
  "inject_cycle": 3,
  "timeout_sec": 600
}
```

### 3.4 readme.md、circuits/seq_counter/tmr_demo.v

- `readme.md` 增加两种时间语义、`--fault-timing` 参数、报表字段和测试结果。
- `tmr_demo.v` 是本次用于直观展示筛减效果的 TMR 演示电路：
  - `out`：三路计数器 + 多数表决器，TMR 位点应被筛掉；
  - `raw`：无保护计数器，单 bit 故障应保留；
  - 共 4 个 4-bit 寄存器，16 个单 bit 故障位点。

## 4. 实测命令与结果

### 4.1 永久翻转

```bash
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false
```

结果：

```text
fault_timing = permanent
TMR 的 12 个 bit: PASS / PRUNED
raw 的  4 个 bit: FAIL / KEEP
缩减率: 75.00%
BMC 深度: 8（3 拍初态 + 5 拍观察）
```

### 4.2 瞬时翻转

```bash
python core/main.py circuits/seq_counter/tmr_demo.v tmr_demo flip false \
    --fault-timing transient
```

结果：

```text
fault_timing = transient
TMR 的 12 个 bit: PASS / PRUNED
raw 的  4 个 bit: FAIL / KEEP
缩减率: 75.00%
```

负向 raw 位的失败点仍在 `step 3`，即单拍脉冲出现的注错拍；第 0–2 拍没有失败。

> 工具默认按 `<top>_report.csv` 覆盖写主报表。本次为了保留 permanent/transient
> 对比，另外手动保存了 `reports/tmr_demo_transient_report.csv`、
> `reports/tmr_demo_transient_summary.json`、`reports/counter_transient_*` 和
> `reports/counter_flip_transient_*`；重跑时以主报表为准。

### 4.3 永久模式下的其他用例

| 用例 | 结果 |
| --- | --- |
| `counter reset true "en == 1'b0"` | 4/4 PRUNED，100% |
| `observer_test flip false` | 2/2 PRUNED，100% |
| `tmr_counter flip false` | 12/12 PRUNED，100% |
| `safe_counter reset true "mode == 1'b1"` | 4/4 PRUNED，100% |

### 4.4 瞬时模式在 counter 上的补充验证

| 命令 | 结果 |
| --- | --- |
| `counter reset true "en == 1'b0" --fault-timing transient` | 4/4 PRUNED，100% |
| `counter flip false --fault-timing transient` | 4/4 KEEP，0% |

瞬时模式在 SA0 和 SEU 上都能得到与永久模式一致的状态判定；区别只在
`formacut_fault_en` 的有效拍数。

## 5. 如何验证瞬态确实只持续 1 拍

SBY 失败 trace 的 VCD 中可以直接看到：

```text
$var wire 1 n2 fault_pulse $end
$var wire 1 n3 formacut_fault_en $end
$var wire 2 n4 init_counter $end
```

对 `tmr_demo` 的 raw bit0 任务，解析 `engine_0/trace.vcd` 可得到：

| 拍数 | init_counter | fault_pulse | formacut_fault_en |
| --- | --- | --- | --- |
| 0 | 00 | 0 | 0 |
| 1 | 01 | 0 | 0 |
| 2 | 10 | 0 | 0 |
| 3 | 11 | 1 | 1 |

第 3 拍为 1；由于 `fault_pulse <= (init_counter == 2'b10)`，第 4 拍
`fault_pulse` 回到 0（SBY 在 step 3 发现反例后停止，因此 trace 不含第 4 拍，
但 RTL 逻辑由构造保证）。

## 6. 语义边界与后续工作

1. **瞬时翻转是 Q 端单拍脉冲**：故障使能只在注错拍为 1，Q 端 bit 在该拍被取反。
   如果该寄存器的 D 逻辑读取 Q（如计数器），被污染的值可能在下一个时钟沿锁存，
   因而状态可能持续偏差；如果 D 与 Q 无关（如某些流水寄存器），可见影响主要
   局限于注错拍。这属于“寄存器 Q 端单周期瞬态”模型。
2. **不是直接改写 FF 状态位**：当前 `mutate` 作用在 Q 端线网上，不直接改写 FF
   内部状态。若论文要求“严格翻转存储状态位、且与 D 无关也持续”，需要进一步做
   状态级注入（例如在 FF 的 Q 状态上增加 shadow register 或在 D 端构造一致
   的 next-state 注入）；这可以作为下一步工作，并可与 uArchiFI 的时序故障模型
   做对比。
3. **组合逻辑**：没有时钟，不存在单拍瞬态；两种参数都等价于时间 0 起有效。
4. **深度**：`--depth` 仍是注错后观察拍数，总 SBY 深度为 `depth + 3`。

## 7. 修改文件清单

| 文件 | 修改内容 |
| --- | --- |
| `core/miter_builder.py` | 新增时间语义、wrapper 波形生成、任务元数据 |
| `core/main.py` | 新增 `--fault-timing`，传递参数 |
| `core/runner.py` | 结果携带 `fault_timing` |
| `core/reporter.py` | CSV/JSON 增加 `fault_timing` |
| `readme.md` | 使用说明、参数、报表字段、结果 |
| `circuits/seq_counter/tmr_demo.v` | TMR + 无保护输出的演示电路 |
| `docs/fault_timing_changes.md` | 本文档：时间语义、修改点、验证方法与边界说明 |
