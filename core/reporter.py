import csv
import os
import json

def save_reports(results, circuit_name, timeout_sec=None):
    if not results:
        print("没有结果可保存。")
        return
        
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    reports_dir = os.path.join(project_root, 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    # 1. 保存详细的 CSV 数据
    csv_file = os.path.join(reports_dir, f"{circuit_name}_report.csv")
    fieldnames = ['task', 'cell', 'bit', 'fault', 'fault_timing',
                  'status', 'decision', 'time', 'depth', 'inject_cycle']
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, '') for key in fieldnames})
            
    # 2. 统计各项指标并保存为 JSON（留给未来的 GUI 用）
    total = len(results)
    pruned = sum(1 for r in results if r['status'] == 'PASS')
    kept = sum(1 for r in results if r['status'] == 'FAIL')
    unknown = sum(1 for r in results if r['status'] == 'UNKNOWN')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    
    total_time = sum(r['time'] for r in results)
    
    summary = {
        "circuit": circuit_name,
        "fault_model": results[0].get('fault', '') if results else '',
        "fault_timing": results[0].get('fault_timing', '') if results else '',
        "total_faults": total,
        "pruned_faults": pruned,
        "kept_faults": kept,
        "unknown_faults": unknown,
        "error_faults": errors,
        "reduction_rate": f"{(pruned/total*100):.2f}%" if total > 0 else "0%",
        "bmc_depth": results[0].get('depth', '') if results else '',
        "inject_cycle": results[0].get('inject_cycle', '') if results else '',
        "timeout_sec": timeout_sec,
        "formal_time_sec": round(total_time, 2)
    }
    
    json_file = os.path.join(reports_dir, f"{circuit_name}_summary.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
        
    print(f"\n📊 报表已保存！")
    print(f"CSV: {csv_file}")
    print(f"JSON: {json_file}")
    print(f"缩减率: {summary['reduction_rate']} (筛减掉 {pruned} 个故障)")

if __name__ == "__main__":
    # 测试代码：模拟 runner.py 传来的数据
    mock_results = [
        {'task': 'task_procdff8', 'status': 'FAIL', 'decision': 'KEEP',
         'time': 0.19, 'cell': '$procdff$8', 'bit': 0, 'fault': 'inv',
         'depth': 8, 'inject_cycle': 3}
    ]
    save_reports(mock_results, "_self_test")