import os
import shutil

def build_miter(v_file, top_module, inputs, outputs, internal_regs, fault_effect='flip', use_constraints=True, custom_assume=None):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    tasks_dir = os.path.join(project_root, 'workspace', 'tasks')
    
    if os.path.exists(tasks_dir):
        shutil.rmtree(tasks_dir)
    os.makedirs(tasks_dir)
    
    v_file_abs = os.path.abspath(os.path.join(project_root, v_file))
    input_names = [p['name'] for p in inputs]
    is_seq = any(name in ['clk', 'clock'] for name in input_names)
    
    # ==========================================
    # 1. 自动生成带断言的 miter_wrapper.v
    # ==========================================
    wrapper_code = "module miter_wrapper(\n"
    for p in inputs:
        w = p['width']
        wrapper_code += f"    input wire [{w-1}:0] {p['name']},\n" if w > 1 else f"    input wire {p['name']},\n"
    for p in outputs:
        w = p['width']
        wrapper_code += f"    output wire [{w-1}:0] {p['name']}_golden,\n" if w > 1 else f"    output wire {p['name']}_golden,\n"
        wrapper_code += f"    output wire [{w-1}:0] {p['name']}_faulty,\n" if w > 1 else f"    output wire {p['name']}_faulty,\n"
    wrapper_code += ");\n\n"
    
    wrapper_code += f"    {top_module} inst_golden (\n"
    for p in inputs: wrapper_code += f"        .{p['name']}({p['name']}),\n"
    for p in outputs: wrapper_code += f"        .{p['name']}({p['name']}_golden),\n"
    wrapper_code = wrapper_code.rstrip(',\n') + "\n    );\n\n"
    
    wrapper_code += f"    {top_module} inst_faulty (\n"
    for p in inputs: wrapper_code += f"        .{p['name']}({p['name']}),\n"
    for p in outputs: wrapper_code += f"        .{p['name']}({p['name']}_faulty),\n"
    wrapper_code = wrapper_code.rstrip(',\n') + "\n    );\n\n"
    
    # 智能约束 + 自定义约束注入
    if is_seq and use_constraints:
        wrapper_code += "    always @(*) begin\n"
        if 'rst' in input_names: wrapper_code += "        assume(rst == 1'b0);\n"
        elif 'reset' in input_names: wrapper_code += "        assume(reset == 1'b0);\n"
        if 'en' in input_names: wrapper_code += "        assume(en == 1'b1);\n"
        elif 'enable' in input_names: wrapper_code += "        assume(enable == 1'b1);\n"
        if 'mode' in input_names: wrapper_code += "        assume(mode == 1'b1);\n"
        elif 'mask' in input_names: wrapper_code += "        assume(mask == 1'b1);\n"
        
        # 🚨 新增：插入用户在命令行指定的自定义约束
        if custom_assume:
            wrapper_code += f"        assume({custom_assume});\n"
            
        wrapper_code += "    end\n\n"
        
    # 智能断言生成
    wrapper_code += "    always @(*) begin\n"
    has_mask = ('mode' in input_names) or ('mask' in input_names)
    if use_constraints and has_mask:
        mask_name = 'mode' if 'mode' in input_names else 'mask'
        wrapper_code += f"        if ({mask_name} == 1'b0) begin\n"
        for p in outputs:
            wrapper_code += f"            assert({p['name']}_golden == {p['name']}_faulty);\n"
        wrapper_code += "        end\n"
    else:
        for p in outputs:
            wrapper_code += f"        assert({p['name']}_golden == {p['name']}_faulty);\n"
    wrapper_code += "    end\nendmodule\n"
    
    with open(os.path.join(tasks_dir, "miter_wrapper.v"), "w", encoding='utf-8') as f:
        f.write(wrapper_code)

    # 3. 为每个内部寄存器生成对应的 Yosys 注入脚本 (.ys)
    tasks = []
    if not internal_regs:
        print("Warning: No internal registers found.")
        return tasks

    for reg in internal_regs:
        reg_name = reg['name']
        safe_reg_name = reg_name.replace('$', '').replace('\\', '_').replace('.', '_').replace(':', '_')
        task_name = f"task_{safe_reg_name}"
        
        docker_v_file = f"/workspace/FormalCut/{v_file.replace(chr(92), '/')}"
        docker_wrapper = f"/workspace/FormalCut/workspace/tasks/miter_wrapper.v"
        docker_smt2 = f"/workspace/FormalCut/workspace/tasks/{task_name}.smt2"
        
        ys_code = f"""
read_verilog {docker_v_file}
prep -top {top_module}
select {top_module}/t:{reg_name}
setattr -set fault_signals 1
cd;
read_verilog -sv {docker_wrapper}
prep -top miter_wrapper
flatten
plugin -i fault_rtlil
fault_rtlil -cnt 1 -timing 1 -effect {fault_effect}
async2sync
dffunmap
write_smt2 -wires {docker_smt2}
"""
        with open(os.path.join(tasks_dir, f"{task_name}.ys"), "w", encoding='utf-8') as f:
            f.write(ys_code)
            
        tasks.append(task_name)
        
    print(f"Success: Generated {len(tasks)} injection tasks in workspace/tasks/")
    return tasks