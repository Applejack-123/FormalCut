import sys
import os

# 支持从 core 目录导入兄弟模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from extractor import extract_ports
from miter_builder import build_miter
from runner import run_all_tasks
from reporter import save_reports

def run_pipeline(circuit_path, top_module):
    print(f"\n{'='*40}")
    print(f"🚀 启动 FormaCut 自动化故障缩减流程")
    print(f"电路: {circuit_path} | 顶层: {top_module}")
    print(f"{'='*40}\n")
    
    # 步骤 1：提取端口
    inputs, outputs,internal_regs = extract_ports(circuit_path, top_module)
    if not inputs:
        return
        
    # 步骤 2：生成任务
    build_miter(circuit_path, top_module, inputs, outputs,internal_regs)
    
    # 步骤 3：并发验证
    results = run_all_tasks(max_workers=4)
    
    # 步骤 4：生成报表
    if results:
        save_reports(results, top_module)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python core/main.py <电路文件路径> <顶层模块名>")
        print("例如: python core/main.py circuits/comb_alu/alu.v alu")
        sys.exit(1)
        
    circuit_file = sys.argv[1]
    top_mod = sys.argv[2]
    run_pipeline(circuit_file, top_mod)