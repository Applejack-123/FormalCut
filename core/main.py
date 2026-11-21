import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from extractor import extract_ports, normalize_files
from miter_builder import build_miter
from runner import run_all_tasks
from reporter import save_reports
from toolchain import find_tool


def run_pipeline(circuit_path, top_module, fault_effect="flip",
                 use_constraints=True, custom_assume=None, depth=5,
                 timeout=600, fault_timing="permanent"):
    files = normalize_files(circuit_path)
    if not files:
        print("❌ 没有指定电路文件")
        return []

    display = ", ".join(os.path.basename(f) for f in files)
    print("\n{}".format("=" * 48))
    print("🚀 启动 FormaCut 自动化故障缩减流程")
    print("电路: {} | 顶层: {} | 故障类型: {}".format(
        display, top_module, fault_effect))
    print("工具链: Yosys={} | SBY={}".format(
        find_tool("yosys") or "MISSING", find_tool("sby") or "MISSING"))
    print("时间语义: {} | 深度: {} 拍（注错后） | 单任务超时: {}s".format(
        fault_timing, depth, timeout))
    print("{}\n".format("=" * 48))

    try:
        inputs, outputs, internal_regs = extract_ports(files, top_module)
    except Exception as exc:  # noqa: BLE001 - CLI should print a useful message
        print("❌ 解析失败: {}".format(exc))
        return []

    if not inputs:
        print("❌ 未找到输入端口，无法构建 miter")
        return []

    try:
        tasks = build_miter(
            files, top_module, inputs, outputs, internal_regs,
            fault_effect, use_constraints, custom_assume, depth=depth,
            fault_timing=fault_timing)
    except Exception as exc:  # noqa: BLE001 - CLI should print a useful message
        print("❌ 生成 miter 任务失败: {}".format(exc))
        return []
    if not tasks:
        return []

    results = run_all_tasks(tasks, timeout=timeout)
    save_reports(results, top_module, timeout_sec=timeout)
    return results


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="FormaCut: Yosys native miter based fault pruning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python core/main.py circuits/itc99/observer_test.v "
            "observer_test flip false\n"
            "  python core/main.py circuits/seq_counter/tmr_demo.v "
            "tmr_demo flip false --depth 5\n"
            "  python core/main.py circuits/seq_counter/tmr_demo.v "
            "tmr_demo flip false --fault-timing transient\n"
            "  python core/main.py circuits/seq_counter/counter.v "
            "counter reset true \"en == 1'b0\"\n"
        ),
    )
    parser.add_argument("circuit",
                        help="Verilog 文件，多个文件用逗号分隔")
    parser.add_argument("top", help="顶层模块名")
    parser.add_argument("fault", nargs="?", default="flip",
                        help="故障类型: flip/SEU, set/SA1, reset/SA0")
    parser.add_argument("constraints", nargs="?", default="true",
                        help="是否自动加约束: true/false")
    parser.add_argument("custom", nargs="?", default=None,
                        help="自定义 assume 表达式，例如 \"mode == 1'b1\"")
    parser.add_argument("legacy_depth", nargs="?", type=int, default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--depth", type=int, default=None,
                        help="注错后观察窗口的 BMC 拍数（总深度 = depth + 3）")
    parser.add_argument("--timeout", type=int, default=600,
                        help="单个 SBY 任务的超时时间，单位秒（默认 600）")
    parser.add_argument("--fault-timing",
                        choices=["permanent", "transient"],
                        default="permanent",
                        help="故障时间语义: permanent=从注错拍起持续有效, "
                             "transient=只注错拍有效 1 拍")
    args = parser.parse_args(argv)

    if args.depth is None:
        args.depth = args.legacy_depth if args.legacy_depth is not None else 5
    if args.depth < 1:
        parser.error("--depth 必须大于等于 1")
    if args.timeout < 1:
        parser.error("--timeout 必须大于等于 1")
    return args


if __name__ == "__main__":
    args = _parse_args()
    use_c = args.constraints.lower() == "true"
    results = run_pipeline(
        args.circuit, args.top, args.fault, use_c,
        args.custom, args.depth, args.timeout, args.fault_timing)
    if not results:
        sys.exit(1)
