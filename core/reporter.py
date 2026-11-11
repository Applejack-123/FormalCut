import csv
import os
import json

def save_reports(results, circuit_name):
    if not results:
        print("没有结果可保存。")
        return
        
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    reports_dir = os.path.join(project_root, 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    # 1. 保存详细的 CSV 数据
    csv_file = os.path.join(reports_dir, f"{circuit_name}_report.csv")
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['task', 'status', 'decision', 'time'])
        writer.writeheader()
        for row in results:
            writer.writerow(row)
            
    # 2. 统计各项指标并保存为 JSON（留给未来的 GUI 用）
    total = len(results)
    pruned = sum(1 for r in results if r['status'] == 'PASS')
    kept = sum(1 for r in results if r['status'] == 'FAIL')
    unknown = sum(1 for r in results if r['status'] == 'UNKNOWN')
    
    total_time = sum(r['time'] for r in results)
    
    summary = {
        "circuit": circuit_name,
        "total_faults": total,
        "pruned_faults": pruned,
        "kept_faults": kept,
        "unknown_faults": unknown,
        "reduction_rate": f"{(pruned/total*100):.2f}%" if total > 0 else "0%",
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
        {'task': 'task_procdff8', 'status': 'FAIL', 'decision': 'KEEP', 'time': 0.19}
    ]
    save_reports(mock_results, "counter")