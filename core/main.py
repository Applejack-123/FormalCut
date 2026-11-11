import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from extractor import extract_ports
from miter_builder import build_miter
from runner import run_all_tasks
from reporter import save_reports

def run_pipeline(circuit_path, top_module, fault_effect='flip', use_constraints=True, custom_assume=None):
    print(f"\n{'='*40}")
    print(f"🚀 启动 FormaCut 自动化故障缩减流程")
    print(f"电路: {circuit_path} | 顶层: {top_module} | 故障类型: {fault_effect}")
    print(f"开启智能约束: {use_constraints} | 自定义约束: {custom_assume if custom_assume else '无'}")
    print(f"{'='*40}\n")
    
    inputs, outputs, internal_regs = extract_ports(circuit_path, top_module)
    if not inputs:
        return
        
    build_miter(circuit_path, top_module, inputs, outputs, internal_regs, fault_effect, use_constraints, custom_assume)
    results = run_all_tasks()
    if results:
        save_reports(results, top_module)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python core/main.py <电路文件路径> <顶层模块名> [故障类型] [是否加约束 true/false] [自定义约束]")
        print("示例: python core/main.py circuits/seq_counter/counter.v counter flip true \"en == 1'b0\"")
        sys.exit(1)
        
    circuit_file = sys.argv[1]
    top_mod = sys.argv[2]
    effect = sys.argv[3] if len(sys.argv) > 3 else 'flip'
    use_c = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else True
    
    # 🚨 接收第 5 个参数
    custom_assume = sys.argv[5] if len(sys.argv) > 5 else None
    
    run_pipeline(circuit_file, top_mod, effect, use_c, custom_assume)