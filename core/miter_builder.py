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
    
    # 🚨 修复点 1：共同初态约束
    if is_seq:
        wrapper_code += "    // 强制同步：用计数器跳过初始状态差异\n"
        wrapper_code += "    reg [1:0] init_counter = 2'b00;\n"
        clk_name = 'clk' if 'clk' in input_names else 'clock'
        wrapper_code += f"    always @(posedge {clk_name}) begin\n"
        wrapper_code += "        if (init_counter < 2'b11) init_counter <= init_counter + 1'b1;\n"
        wrapper_code += "    end\n\n"

    if is_seq and use_constraints:
        wrapper_code += "    always @(*) begin\n"
        if 'rst' in input_names: wrapper_code += "        assume(rst == 1'b0);\n"
        elif 'reset' in input_names: wrapper_code += "        assume(reset == 1'b0);\n"
        if 'en' in input_names: wrapper_code += "        assume(en == 1'b1);\n"
        elif 'enable' in input_names: wrapper_code += "        assume(enable == 1'b1);\n"
        if 'mode' in input_names: wrapper_code += "        assume(mode == 1'b1);\n"
        elif 'mask' in input_names: wrapper_code += "        assume(mask == 1'b1);\n"
        if custom_assume: wrapper_code += f"        assume({custom_assume});\n"
        wrapper_code += "    end\n\n"
        
    # 🚨 修复点 2：延迟 2 拍后检查
    wrapper_code += "    always @(*) begin\n"
    if is_seq:
        wrapper_code += "        if (init_counter == 2'b11) begin\n"
        indent = "            "
    else:
        indent = "        "

    has_mask = ('mode' in input_names) or ('mask' in input_names)
    if use_constraints and has_mask:
        mask_name = 'mode' if 'mode' in input_names else 'mask'
        wrapper_code += f"{indent}if ({mask_name} == 1'b0) begin\n"
        for p in outputs:
            wrapper_code += f"{indent}    assert({p['name']}_golden == {p['name']}_faulty);\n"
        wrapper_code += f"{indent}end\n"
    else:
        for p in outputs:
            wrapper_code += f"{indent}assert({p['name']}_golden == {p['name']}_faulty);\n"
        
    if is_seq: wrapper_code += "        end\n"
    wrapper_code += "    end\nendmodule\n"
    
    with open(os.path.join(tasks_dir, "miter_wrapper.v"), "w", encoding='utf-8') as f:
        f.write(wrapper_code)

    # ==========================================
    # 2. 生成验证任务
    # ==========================================
    tasks = []
    if not internal_regs:
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
flatten

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
        
    print(f"Success: Generated {len(tasks)} tasks in workspace/tasks/")
    return tasks