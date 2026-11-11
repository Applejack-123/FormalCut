import os
import subprocess
import glob
import time

def run_all_tasks():
    tasks_dir = 'workspace/tasks'
    ys_files = glob.glob(f"{tasks_dir}/*.ys")
    
    if not ys_files:
        print("❌ 没有找到任何 .ys 任务，请先运行 miter_builder.py")
        return []

    print(f"=== 发现 {len(ys_files)} 个注入任务，开始验证 ===")
    
    results = []
    for ys_file in ys_files:
        base_name = os.path.basename(ys_file).replace('.ys', '')
        smt2_file = ys_file.replace('.ys', '.smt2')
        
        print(f"\n[{base_name}] 正在执行 Yosys 注入...")
        res_yosys = subprocess.run(["yosys", "-s", ys_file], capture_output=True, text=True)
        if res_yosys.returncode != 0:
            print(f"[{base_name}] ❌ Yosys 注入失败！")
            results.append({'task': base_name, 'status': 'ERROR', 'decision': 'ERROR', 'time': 0})
            continue
            
        print(f"[{base_name}] 正在运行 Yices 求解器...")
        start_time = time.time()
        res_yices = subprocess.run(
            ["yosys-smtbmc", "-s", "yices", "-t", "5", smt2_file], 
            capture_output=True, text=True
        )
        elapsed = time.time() - start_time
        
        if "Status: PASSED" in res_yices.stdout:
            status = "PASS"
            decision = "PRUNED"
        elif "Status: FAILED" in res_yices.stdout:
            status = "FAIL"
            decision = "KEEP"
        else:
            status = "UNKNOWN"
            decision = "TIMEOUT_KEEP"
            
        print(f"[{base_name}] ✅ 结果: {status} ({decision}) | 耗时: {elapsed:.2f}s")
        
        results.append({
            'task': base_name,
            'status': status,
            'decision': decision,
            'time': round(elapsed, 2)
        })
        
    return results

if __name__ == "__main__":
    run_all_tasks()