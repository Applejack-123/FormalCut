import os
import shutil

def build_miter(v_file, top_module, inputs, outputs, internal_regs, fault_effect='flip', use_constraints=True, custom_assume=None):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    tasks_dir = os.path.join(project_root, 'workspace', 'tasks')
    
    if os.path.exists(tasks_dir):
        shutil.rmtree(tasks_dir)
    os.makedirs(tasks_dir)
    
    if fault_effect == 'flip':
        mutate_mode = 'inv'
    elif fault_effect == 'set':
        mutate_mode = 'const1'
    elif fault_effect == 'reset':
        mutate_mode = 'const0'
    else:
        mutate_mode = 'inv'

    tasks = []
    if not internal_regs:
        return tasks

    for reg in internal_regs:
        reg_name = reg['name']
        reg_width = reg.get('width', 1)
        
        for bit_idx in range(reg_width):
            safe_reg_name = reg_name.replace('$', '').replace('\\', '_').replace('.', '_').replace(':', '_')
            task_name = "task_{}_bit{}".format(safe_reg_name, bit_idx)
            
            docker_v_file = "/workspace/FormalCut/{}".format(v_file.replace(chr(92), '/'))
            mutated_v = os.path.join(tasks_dir, "{}_mutated.v".format(task_name))
            docker_mutated_v = "/workspace/FormalCut/workspace/tasks/{}_mutated.v".format(task_name)
            
            mutate_cmd = "read_verilog {}; prep -top {}; mutate -mode {} -module {} -cell {} -port Q -portbit {} -ctrl mutsel 1 1; write_verilog -noattr {}".format(
                docker_v_file, top_module, mutate_mode, top_module, reg_name, bit_idx, docker_mutated_v
            )
            
            miter_v = os.path.join(tasks_dir, "{}_miter.v".format(task_name))
            docker_miter_v = "/workspace/FormalCut/workspace/tasks/{}_miter.v".format(task_name)
            
            ports_decl = ""
            ref_ports = ""
            uut_ports = ""
            for p in inputs:
                w = p['width']
                ports_decl += "    input wire [{}:0] {},\n".format(w-1, p['name']) if w > 1 else "    input wire {},\n".format(p['name'])
                ref_ports += "        .{}({}),\n".format(p['name'], p['name'])
                uut_ports += "        .{}({}),\n".format(p['name'], p['name'])
            
            out_decl = ""
            assert_logic = ""
            for p in outputs:
                w = p['width']
                out_decl += "    wire [{}:0] {}_ref, {}_uut;\n".format(w-1, p['name'], p['name']) if w > 1 else "    wire {}_ref, {}_uut;\n".format(p['name'], p['name'])
                ref_ports += "        .{}({}_ref),\n".format(p['name'], p['name'])
                uut_ports += "        .{}({}_uut),\n".format(p['name'], p['name'])
                assert_logic += "            assert({}_ref == {}_uut);\n".format(p['name'], p['name'])
            
            is_seq = any(p['name'] in ['clk', 'clock'] for p in inputs)
            clk_name = 'clk' if 'clk' in [p['name'] for p in inputs] else 'clock'
            
            init_cond = ""
            if is_seq and use_constraints:
                init_cond = """
    reg [1:0] init_counter = 2'b00;
    always @(posedge {}) begin
        if (init_counter < 2'b11) init_counter <= init_counter + 1'b1;
    end
""".format(clk_name)
            
            env_constraints = ""
            if is_seq and use_constraints:
                if 'rst' in [p['name'] for p in inputs]:
                    env_constraints += "        assume(rst == 1'b0);\n"
                if 'en' in [p['name'] for p in inputs]:
                    env_constraints += "        assume(en == 1'b1);\n"
                if custom_assume:
                    env_constraints += "        assume({});\n".format(custom_assume)

            wrapper_code = """
module miter_test(
{ports_decl}
);
{out_decl}
    {top_module} ref (
{ref_ports}
    );

    {top_module} uut (
{uut_ports}
    );
{init_cond}
    always @(*) begin
{env_constraints}
        if (init_counter == 2'b11) begin
{assert_logic}
        end
    end
endmodule
""".format(
                ports_decl=ports_decl,
                out_decl=out_decl,
                top_module=top_module,
                ref_ports=ref_ports.rstrip(',\n'),
                uut_ports=uut_ports.rstrip(',\n'),
                init_cond=init_cond,
                env_constraints=env_constraints,
                assert_logic=assert_logic
            )
            with open(miter_v, "w", encoding='utf-8') as f:
                f.write(wrapper_code)

            sby_file = os.path.join(tasks_dir, "{}.sby".format(task_name))
            sby_code = """
[options]
mode bmc
depth 5
[engines]
smtbmc yices
[script]
read_verilog {docker_mutated_v}
read_verilog -sv {docker_miter_v}
prep -top miter_test
flatten
async2sync
dffunmap
[files]
{docker_mutated_v}
{docker_miter_v}
""".format(docker_mutated_v=docker_mutated_v, docker_miter_v=docker_miter_v)
            with open(sby_file, 'w', encoding='utf-8') as f:
                f.write(sby_code)
                
            tasks.append({'task': task_name, 'sby': sby_file, 'mutate_cmd': mutate_cmd})
        
    print("Success: Generated {} mutation tasks in workspace/tasks/".format(len(tasks)))
    return tasks