import sys
import os

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from extractor import extract_ports
from miter_builder import build_miter
from runner import run_all_tasks
from reporter import save_reports

def run_pipeline(circuit_path, top_module, fault_effect='flip'):
    print(f"\n{'='*40}")
    print(f"🚀 启动 FormaCut 自动化故障缩减流程")
    print(f"电路: {circuit_path} | 顶层: {top_module} | 故障类型: {fault_effect}")
    print(f"{'='*40}\n")
    
    # 步骤 1：提取内部寄存器与端口
    inputs, outputs, internal_regs = extract_ports(circuit_path, top_module)
    if not inputs:
        return
        
    # 步骤 2：生成任务
    build_miter(circuit_path, top_module, inputs, outputs, internal_regs, fault_effect)
    
    # 步骤 3：并发/自动化验证
    results = run_all_tasks()
    
    # 步骤 4：生成报表
    if results:
        save_reports(results, top_module)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python core/main.py <电路文件路径> <顶层模块名> [故障类型]")
        print("例如: python core/main.py circuits/seq_counter/counter.v counter flip")
        print("故障类型可选: flip (SEU), set (SA1), reset (SA0)")
        sys.exit(1)
        
    circuit_file = sys.argv[1]
    top_mod = sys.argv[2]
    
    # 第三个参数可选，默认为 flip
    effect = sys.argv[3] if len(sys.argv) > 3 else 'flip'
    
    run_pipeline(circuit_file, top_mod, effect)