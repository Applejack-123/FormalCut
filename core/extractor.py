import json
import os
import subprocess

try:  # Support both "python core/main.py" and "import core.extractor".
    from .toolchain import get_env, require_tool
except ImportError:  # pragma: no cover - script execution path
    from toolchain import get_env, require_tool


# Cell types that can hold a state bit.  ``prep`` normally produces ``$dff``
# (synchronous reset is lowered to muxes) and ``$adff`` (asynchronous reset),
# but keeping the complete list makes the extractor robust across Yosys
# versions and front-ends.
FF_CELL_TYPES = {
    "$dff", "$dffe", "$adff", "$adffe",
    "$sdff", "$sdffe", "$aldff", "$aldffe",
    "$dffsr", "$dffsre", "$ff", "$ffsr", "$ffsre",
    "$dlatch", "$adlatch", "$dlatchsr",
}


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def normalize_files(v_files):
    """Accept a string, a comma separated string, or a sequence of paths."""
    if isinstance(v_files, str):
        parts = [p.strip() for p in v_files.split(",")]
    else:
        parts = [str(p).strip() for p in v_files]

    project_root = _project_root()
    resolved = []
    for part in parts:
        if not part:
            continue
        if not os.path.isabs(part):
            part = os.path.join(project_root, part)
        resolved.append(os.path.abspath(part))
    return resolved


def _yosys_path(path, project_root):
    """Prefer project-relative, forward-slash paths inside a Yosys script."""
    rel = os.path.relpath(path, project_root)
    if rel.startswith(".."):
        rel = path
    return rel.replace("\\", "/")


def extract_ports(v_files, top_module):
    project_root = _project_root()
    files = normalize_files(v_files)
    if not files:
        raise ValueError("没有指定 Verilog 源文件")

    json_dir = os.path.join(project_root, "workspace", "json")
    os.makedirs(json_dir, exist_ok=True)
    json_file = os.path.join(json_dir, "{}.json".format(top_module))
    json_rel = _yosys_path(json_file, project_root)

    read_cmds = ['read_verilog {}'.format(_yosys_path(f, project_root))
                 for f in files]
    # ``flatten`` is important for hierarchical designs (for example the TMR
    # counter): the miter builder mutates register cells in the flattened top
    # module, so the JSON netlist and the mutation script have to use exactly
    # the same elaboration sequence.
    script = "; ".join(read_cmds + [
        "prep -top {}".format(top_module),
        "flatten",
        'write_json {}'.format(json_rel),
    ])

    yosys = require_tool("yosys")
    print("🔧 Yosys: {}".format(yosys))
    result = subprocess.run(
        [yosys, "-q", "-p", script],
        cwd=project_root,
        env=get_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Yosys 网表解析失败:\n{}\n{}".format(result.stdout, result.stderr)
        )

    with open(json_file, "r", encoding="utf-8") as f:
        netlist = json.load(f)

    if top_module not in netlist.get("modules", {}):
        raise RuntimeError("在网表中找不到顶层模块 {}".format(top_module))

    top = netlist["modules"][top_module]
    ports = top.get("ports", {})
    cells = top.get("cells", {})

    inputs = []
    outputs = []
    internal_regs = []

    for name, info in ports.items():
        width = len(info["bits"])
        port_info = {"name": name, "width": width}
        if info["direction"] == "input":
            inputs.append(port_info)
        elif info["direction"] == "output":
            outputs.append(port_info)

    for cell_name, cell_info in cells.items():
        if cell_info["type"] not in FF_CELL_TYPES:
            continue
        q_bits = cell_info.get("connections", {}).get("Q", [])
        if not q_bits:
            continue
        internal_regs.append({
            "name": cell_name,
            "width": len(q_bits),
            "cell_type": cell_info["type"],
        })

    # Stable ordering keeps reports reproducible between runs.
    inputs.sort(key=lambda p: p["name"])
    outputs.sort(key=lambda p: p["name"])
    internal_regs.sort(key=lambda r: r["name"])

    print("✅ 解析成功！")
    print("   - 输入端口: {}".format(len(inputs)))
    print("   - 输出端口: {}".format(len(outputs)))
    print("   - 内部寄存器单元: {}".format(len(internal_regs)))
    for reg in internal_regs:
        print("     -> 发现寄存器: {} ({} , 宽度: {})".format(
            reg["name"], reg["cell_type"], reg["width"]))
    print("   - 可注入故障位点: {}".format(
        sum(r["width"] for r in internal_regs)))

    return inputs, outputs, internal_regs
