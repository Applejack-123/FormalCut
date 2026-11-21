import os
import subprocess
import time

def run_all_tasks(tasks):
    results = []
    
    for task in tasks:
        task_name = task['task']
        sby_file = task['sby']
        mutate_cmd = task['mutate_cmd']
        
        print(f"\n[{task_name}] 正在执行 mutate 注入...")
        # 1. 执行 mutate 生成变异网表
        res_yosys = subprocess.run(["yosys", "-p", mutate_cmd], capture_output=True, text=True)
        if res_yosys.returncode != 0:
            print(f"[{task_name}] ❌ Mutate 失败！")
            results.append({'task': task_name, 'status': 'ERROR', 'decision': 'ERROR', 'time': 0})
            continue
            
        print(f"[{task_name}] 正在运行 SBY...")
        # 2. 调用 SBY 跑形式化验证
        start_time = time.time()
        res_sby = subprocess.run(["sby", "-f", sby_file], capture_output=True, text=True)
        elapsed = time.time() - start_time
        
        # 3. 解析结果
        if "DONE (PASS" in res_sby.stdout:
            status = "PASS"
            decision = "PRUNED"
        elif "DONE (FAIL" in res_sby.stdout:
            status = "FAIL"
            decision = "KEEP"
        else:
            status = "UNKNOWN"
            decision = "TIMEOUT_KEEP"
            
        print(f"[{task_name}] ✅ 结果: {status} ({decision}) | 耗时: {elapsed:.2f}s")
        results.append({'task': task_name, 'status': status, 'decision': decision, 'time': round(elapsed, 2)})
        
    return results