import subprocess
import concurrent.futures
import time
import os
from pathlib import Path
import csv

def run_task(task_dir):
    task_name = os.path.basename(task_dir)
    sby_file = "task.sby"
    
    start_time = time.time()
    # 运行 sby 命令，注意在 task_dir 下执行
    result = subprocess.run(
        ['sby', '-f', sby_file], 
        cwd=task_dir, 
        capture_output=True, text=True
    )
    elapsed = time.time() - start_time
    
    status = 'UNKNOWN'
    if 'DONE (PASS' in result.stdout: status = 'PASS'
    elif 'DONE (FAIL' in result.stdout: status = 'FAIL'
        
    decision = 'PRUNED_PROVEN' if status == 'PASS' else ('KEEP_COUNTEREXAMPLE' if status == 'FAIL' else 'KEEP_UNKNOWN')
        
    return {
        'Fault': task_name,
        'Status': status,
        'Decision': decision,
        'Time(s)': round(elapsed, 2)
    }

def run_all_tasks(max_workers=4):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    tasks_dir = os.path.join(project_root, 'workspace', 'tasks')
    
    # 找出所有任务文件夹
    tasks = [str(p) for p in Path(tasks_dir).iterdir() if p.is_dir()]
    
    if not tasks:
        print("❌ 没有找到任何任务，请先运行 miter_builder.py")
        return None

    print(f"=== 发现 {len(tasks)} 个任务，启动 {max_workers} 并发执行 ===")
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {executor.submit(run_task, task): task for task in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            res = future.result()
            results.append(res)
            print(f"[{res['Status']}] 故障: {res['Fault']} | 耗时: {res['Time(s)']}s")
            
    return results

if __name__ == "__main__":
    res = run_all_tasks()
    if res:
        # 简单打印一下
        pass