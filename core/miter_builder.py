import os
import shutil

def build_miter(v_file, top_module, inputs, outputs, internal_regs):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    tasks_dir = os.path.join(project_root, 'workspace', 'tasks')
    
    if os.path.exists(tasks_dir):
        shutil.rmtree(tasks_dir)
    os.makedirs(tasks_dir)
    
    v_file_abs = os.path.abspath(os.path.join(project_root, v_file))
    is_seq = any(port['name'] in ['clk', 'clock'] for port in inputs)
    input_names = [p['name'] for p in inputs]
    
    tasks = []
    
    # 针对每个输入端口位生成注入
    for in_port in inputs:
        p_name = in_port['name']
        p_width = in_port['width']
        
        # 强行跳过时钟端口，防止 Z3 崩溃
        if p_name in ['clk', 'clock']:
            continue
            
        for i in range(p_width):
            fault_id = f"{p_name}_{i}" if p_width > 1 else p_name
            task_dir = os.path.join(tasks_dir, fault_id)
            os.makedirs(task_dir)
            
            sv_code = f"module miter_{fault_id}(\n"
            for port in inputs:
                w = port['width']
                sv_code += f"    input wire [{w-1}:0] {port['name']},\n" if w > 1 else f"    input wire {port['name']},\n"
            for port in outputs:
                w = port['width']
                sv_code += f"    output wire [{w-1}:0] {port['name']}_golden,\n" if w > 1 else f"    output wire {port['name']}_golden,\n"
            for port in outputs:
                w = port['width']
                sv_code += f"    wire [{w-1}:0] {port['name']}_faulty;\n" if w > 1 else f"    wire {port['name']}_faulty;\n"
            
            sv_code += "    (* anyseq *) input wire fire\n);\n\n"
            
            # 故障注入 MUX
            for port in inputs:
                w = port['width']
                if port['name'] == p_name:
                    if w > 1:
                        sv_code += f"    wire [{w-1}:0] faulty_{port['name']};\n"
                        for j in range(w):
                            if j == i:
                                sv_code += f"    assign faulty_{port['name']}[{j}] = fire ? 1'b0 : {port['name']}[{j}];\n"
                            else:
                                sv_code += f"    assign faulty_{port['name']}[{j}] = {port['name']}[{j}];\n"
                    else:
                        sv_code += f"    wire faulty_{port['name']} = fire ? 1'b0 : {port['name']};\n"
                else:
                    sv_code += f"    wire [{w-1}:0] faulty_{port['name']} = {port['name']};\n" if w > 1 else f"    wire faulty_{port['name']} = {port['name']};\n"
            
            # 实例化正常电路
            sv_code += f"\n    {top_module} inst_golden (\n"
            for port in inputs:
                sv_code += f"        .{port['name']}({port['name']}),\n"
            for port in outputs:
                sv_code += f"        .{port['name']}({port['name']}_golden),\n"
            sv_code = sv_code.rstrip(',\n') + "\n    );\n"
            
            # 实例化故障电路
            sv_code += f"\n    {top_module} inst_faulty (\n"
            for port in inputs:
                if port['name'] == p_name:
                    sv_code += f"        .{port['name']}(faulty_{port['name']}),\n"
                else:
                    sv_code += f"        .{port['name']}({port['name']}),\n"
            for port in outputs:
                sv_code += f"        .{port['name']}({port['name']}_faulty),\n"
            sv_code = sv_code.rstrip(',\n') + "\n    );\n"
            
            # 智能环境约束
            sv_code += "\n    // 强制环境约束（屏蔽故障）\n"
            sv_code += "    always @(*) begin\n"
            if is_seq:
                if 'rst' in input_names:
                    sv_code += "        assume(rst == 1'b0);\n"
                if 'en' in input_names:
                    sv_code += "        assume(en == 1'b1);\n"
            sv_code += "    end\n\n"
            
            # 断言：时序电路用 posedge clk，组合电路用 always @(*)
            if is_seq:
                clock_name = 'clk' if 'clk' in input_names else 'clock'
                sv_code += f"    always @(posedge {clock_name}) begin\n"
                sv_code += "        if (fire) begin\n"
            else:
                sv_code += "    always @(*) begin\n"
                sv_code += "        if (fire) begin\n"
                
            for port in outputs:
                sv_code += f"            assert({port['name']}_golden == {port['name']}_faulty);\n"
            sv_code += "        end\n    end\nendmodule\n"

            with open(os.path.join(task_dir, f"miter_{fault_id}.sv"), 'w', encoding='utf-8') as f:
                f.write(sv_code)
                
            # SBY 配置
            sby_code = f"""
[options]
mode bmc
depth 1
[engines]
smtbmc z3
[script]
read -formal -sv {v_file_abs}
read -formal -sv miter_{fault_id}.sv
prep -top miter_{fault_id}
[files]
{v_file_abs}
miter_{fault_id}.sv
"""
            with open(os.path.join(task_dir, f"task.sby"), 'w', encoding='utf-8') as f:
                f.write(sby_code)
                
            tasks.append(fault_id)
            
    print(f"Success: Generated {len(tasks)} tasks in workspace/tasks/")
    return tasks

if __name__ == "__main__":
    from extractor import extract_ports
    v_file = 'circuits/seq_counter/counter.v'
    top = 'counter'
    ins, outs, regs = extract_ports(v_file, top)
    if ins:
        build_miter(v_file, top, ins, outs, regs)