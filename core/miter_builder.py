import os
import shutil

def build_miter(v_file, top_module, inputs, outputs, internal_regs, fault_effect='flip'):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    tasks_dir = os.path.join(project_root, 'workspace', 'tasks')
    
    # 清理旧任务
    if os.path.exists(tasks_dir):
        shutil.rmtree(tasks_dir)
    os.makedirs(tasks_dir)
    
    # 获取绝对路径
    v_file_abs = os.path.abspath(os.path.join(project_root, v_file))
    input_names = [p['name'] for p in inputs]
    is_seq = any(name in ['clk', 'clock'] for name in input_names)
    
    # ==========================================
    # 1. 自动生成带断言的 miter_wrapper.v
    # ==========================================
    wrapper_code = "module miter_wrapper(\n"
    # 端口声明
    for p in inputs:
        w = p['width']
        wrapper_code += f"    input wire [{w-1}:0] {p['name']},\n" if w > 1 else f"    input wire {p['name']},\n"
    for p in outputs:
        w = p['width']
        wrapper_code += f"    output wire [{w-1}:0] {p['name']}_golden,\n" if w > 1 else f"    output wire {p['name']}_golden,\n"
        wrapper_code += f"    output wire [{w-1}:0] {p['name']}_faulty,\n" if w > 1 else f"    output wire {p['name']}_faulty,\n"
    wrapper_code += ");\n\n"
    
    # 实例化正常电路
    wrapper_code += f"    {top_module} inst_golden (\n"
    for p in inputs:
        wrapper_code += f"        .{p['name']}({p['name']}),\n"
    for p in outputs:
        wrapper_code += f"        .{p['name']}({p['name']}_golden),\n"
    wrapper_code = wrapper_code.rstrip(',\n') + "\n    );\n\n"
    
    # 实例化故障电路
    wrapper_code += f"    {top_module} inst_faulty (\n"
    for p in inputs:
        wrapper_code += f"        .{p['name']}({p['name']}),\n"
    for p in outputs:
        wrapper_code += f"        .{p['name']}({p['name']}_faulty),\n"
    wrapper_code = wrapper_code.rstrip(',\n') + "\n    );\n\n"
    
    # 添加环境约束 (只针对标准的 clk/rst)
    if is_seq:
        wrapper_code += "    always @(*) begin\n"
        if 'rst' in input_names:
            wrapper_code += "        assume(rst == 1'b0); // 假设系统一直处于正常工作状态\n"
        elif 'reset' in input_names:
            wrapper_code += "        assume(reset == 1'b0);\n"
        wrapper_code += "    end\n\n"
        
    # 添加断言
    wrapper_code += "    always @(*) begin\n"
    for p in outputs:
        wrapper_code += f"        assert({p['name']}_golden == {p['name']}_faulty);\n"
    wrapper_code += "    end\nendmodule\n"
    
    wrapper_file = os.path.join(tasks_dir, "miter_wrapper.v")
    with open(wrapper_file, "w", encoding='utf-8') as f:
        f.write(wrapper_code)

    # ==========================================
    # 2. 为每个内部寄存器生成对应的 Yosys 注入脚本 (.ys)
    # ==========================================
    tasks = []
    
    # 如果没找到内部寄存器，就跳过后面的
    if not internal_regs:
        print("Warning: No internal registers found. Task generation skipped.")
        return tasks

    for reg in internal_regs:
        reg_name = reg['name']
        # 清理寄存器名字中的特殊字符，防止作为文件名报错
        safe_reg_name = reg_name.replace('$', '').replace('\\', '_').replace('.', '_').replace(':', '_')
        task_name = f"task_{safe_reg_name}"
        
        # 获取 Docker 容器内的路径映射 (假设 Docker 挂载在 /workspace/FormalCut)
        docker_v_file = f"/workspace/FormalCut/{v_file.replace(chr(92), '/')}"
        docker_wrapper = f"/workspace/FormalCut/workspace/tasks/miter_wrapper.v"
        docker_smt2 = f"/workspace/FormalCut/workspace/tasks/{task_name}.smt2"
        
        ys_code = f"""
# 1. 读入原始设计并展开
read_verilog {docker_v_file}
prep -top {top_module}

# 2. 在 flatten 之前，直接在 counter 模块内部打上标记
# 注意：这里用 hierarchical 语法直接定位，绝不加 %d
select {top_module}/t:{reg_name}
setattr -set fault_signals 1
cd;

# 3. 读入带断言的 Miter 外壳
read_verilog -sv {docker_wrapper}
prep -top miter_wrapper

# 4. 现在才压平（插件会自动把打过标记的线保留下来）
flatten

# 5. 插件干活
plugin -i fault_rtlil
fault_rtlil -cnt 1 -timing 1 -effect {fault_effect}

# 6. 导出
async2sync
dffunmap
write_smt2 -wires {docker_smt2}
"""
        ys_file = os.path.join(tasks_dir, f"{task_name}.ys")
        with open(ys_file, "w", encoding='utf-8') as f:
            f.write(ys_code)
            
        tasks.append(task_name)
        
    print(f"Success: Generated {len(tasks)} injection tasks in workspace/tasks/")
    return tasks

if __name__ == "__main__":
    from extractor import extract_ports
    # 测试用例
    v_file = 'circuits/seq_counter/counter.v'
    top = 'counter'
    ins, outs, regs = extract_ports(v_file, top)
    if ins:
        build_miter(v_file, top, ins, outs, regs, fault_effect='flip')