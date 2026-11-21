import os
import subprocess
import time

try:  # Support both "python core/main.py" and "import core.runner".
    from .toolchain import find_tool, get_env
except ImportError:  # pragma: no cover - script execution path
    from toolchain import find_tool, get_env


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _classify(output):
    if "DONE (PASS" in output:
        return "PASS", "PRUNED"
    if "DONE (FAIL" in output:
        return "FAIL", "KEEP"
    if "DONE (UNKNOWN" in output or "DONE (TIMEOUT" in output:
        return "UNKNOWN", "TIMEOUT_KEEP"
    return "ERROR", "ERROR"


def run_all_tasks(tasks, timeout=600):
    results = []
    if not tasks:
        return results

    sby = find_tool("sby")
    if not sby:
        print("❌ 找不到 SBY。请安装 OSS CAD Suite，或设置 "
              "FORMACUT_TOOLCHAIN 指向它的 bin 目录。")
        for task in tasks:
            results.append({
                "task": task["task"],
                "status": "ERROR",
                "decision": "ERROR",
                "time": 0,
                "cell": task.get("cell", ""),
                "bit": task.get("bit", ""),
                "fault": task.get("fault", ""),
                "fault_timing": task.get("fault_timing", ""),
                "depth": task.get("depth", ""),
                "inject_cycle": task.get("inject_cycle", ""),
            })
        return results

    env = get_env()
    project_root = _project_root()
    print("🔧 SBY: {}".format(sby))

    for index, task in enumerate(tasks, 1):
        task_name = task["task"]
        sby_file = task["sby"]

        print("\n[{}/{}] {}: SBY + smtbmc/yices".format(
            index, len(tasks), task_name))
        start_time = time.time()
        try:
            res = subprocess.run(
                [sby, "-f", sby_file],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            elapsed = time.time() - start_time
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            status, decision = _classify(output)
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            output = ""
            status, decision = "UNKNOWN", "TIMEOUT_KEEP"
            print("  ⏱️  SBY 超时（{}s），保守保留该故障".format(timeout))
        except Exception as exc:  # noqa: BLE001 - report and keep going
            elapsed = time.time() - start_time
            output = str(exc)
            status, decision = "ERROR", "ERROR"
            print("  ❌ SBY 启动失败: {}".format(exc))

        if status == "ERROR":
            tail = [line for line in output.splitlines() if line.strip()][-12:]
            for line in tail:
                print("     {}".format(line))

        print("  ✅ 结果: {} ({}) | 耗时: {:.2f}s".format(
            status, decision, elapsed))
        results.append({
            "task": task_name,
            "status": status,
            "decision": decision,
            "time": round(elapsed, 2),
            "cell": task.get("cell", ""),
            "bit": task.get("bit", ""),
            "fault": task.get("fault", ""),
            "fault_timing": task.get("fault_timing", ""),
            "depth": task.get("depth", ""),
            "inject_cycle": task.get("inject_cycle", ""),
        })

    return results
