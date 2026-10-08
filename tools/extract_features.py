#!/usr/bin/env python3
from __future__ import annotations
import re
from pathlib import Path
OPCODES=['add','sub','mul','udiv','sdiv','urem','srem','fadd','fsub','fmul','fdiv','load','store','getelementptr','br','switch','phi','call','invoke','ret','icmp','fcmp','select','alloca','shl','lshr','ashr','and','or','xor','trunc','zext','sext','sitofp','uitofp','fptosi','fptoui','bitcast','addrspacecast','extractelement','insertelement','shufflevector','extractvalue','insertvalue']
def count(pattern,text): return len(re.findall(pattern,text,flags=re.MULTILINE))
def extract_features(ir_text):
    f={'ir_lines':len(ir_text.splitlines()),'functions':count(r'^define\\s',ir_text),'declarations':count(r'^declare\\s',ir_text),'basic_blocks':count(r'^[A-Za-z$._][^:]*:\\s*$',ir_text),'phi_nodes':count(r'\\bphi\\s',ir_text),'branches':count(r'\\bbr\\s',ir_text),'conditional_branches':count(r'\\bbr\\s+i1\\s',ir_text),'switches':count(r'\\bswitch\\s',ir_text),'calls':count(r'\\b(call|invoke)\\s',ir_text),'loads':count(r'\\bload\\s',ir_text),'stores':count(r'\\bstore\\s',ir_text),'getelementptr':count(r'\\bgetelementptr\\s',ir_text),'vector_types':count(r'<\\d+\\s+x\\s+',ir_text),'allocas':count(r'\\balloca\\s',ir_text),'returns':count(r'\\bret\\s',ir_text),'global_vars':count(r'^@[^=]+=',ir_text),'metadata_nodes':count(r'^!\\d+\\s*=',ir_text)}
    for op in OPCODES: f['op_'+op]=count(rf'\\b{re.escape(op)}\\s',ir_text)
    f['estimated_ir_instruction_count']=sum(f['op_'+x] for x in OPCODES); f['memory_ops']=f['loads']+f['stores']; f['branch_density_proxy']=f['branches']+f['switches']; return f
def read_and_extract(path:Path): return extract_features(path.read_text(encoding='utf-8',errors='replace'))
