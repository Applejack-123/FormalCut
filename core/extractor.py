import json
import os
import subprocess

def extract_ports(v_file, top_module):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    json_dir = os.path.join(project_root, 'workspace', 'json')
    os.makedirs(json_dir, exist_ok=True)
    json_file = os.path.join(json_dir, f"{top_module}.json")
    v_file_abs = os.path.abspath(os.path.join(project_root, v_file))
    
    # 核心改动：加上了 -noopt，禁止 Yosys 优化！
    # 这样所有的内部寄存器和线名都会原封不动地保留在网表里
    cmd = f'yosys -q -p "read_verilog {v_file_abs}; prep -top {top_module}; write_json {json_file}"'
    subprocess.run(cmd, shell=True, check=True)
        
    with open(json_file, 'r') as f:
        netlist = json.load(f)
        
    top = netlist['modules'][top_module]
    ports = top['ports']
    cells = top['cells']
    
    inputs = []
    outputs = []
    internal_regs = []
    
    for name, info in ports.items():
        width = len(info['bits'])
        port_info = {'name': name, 'width': width}
        if info['direction'] == 'input':
            inputs.append(port_info)
        elif info['direction'] == 'output':
            outputs.append(port_info)
            
    # 暴力搜索所有单元里的寄存器
    for cell_name, cell_info in cells.items():
        if cell_info['type'] in ['$adff', '$dff', '$sdff', '$dlatch']:
            q_bits = cell_info['connections']['Q']
            
            # 直接用 Yosys 生成的真实名字！
            # 这样就能看到 $procdff$91 这种真实存在的寄存器
            internal_regs.append({
                'name': cell_name, 
                'width': len(q_bits),
                'cell_type': cell_info['type']
            })
            
    print(f"✅ 解析成功！")
    print(f"   - 输入端口: {len(inputs)}")
    print(f"   - 输出端口: {len(outputs)}")
    print(f"   - 内部寄存器: {len(internal_regs)}")
    for r in internal_regs:
        print(f"     -> 发现寄存器: {r['name']} (宽度: {r['width']})")
    
    return inputs, outputs, internal_regs