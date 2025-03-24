from array import array
from dataclasses import dataclass, field
import json
from string import ascii_lowercase

import cmds
from other_types import Label, print_expr_or_var, print_function_import, print_label, read_function_imports, read_label
from tables import Table, print_table, read_table
from util import SymbolIds, read_string, write_string
from variables import Var, VarCategory, print_var, read_variable, var_from_yaml, write_variable

# function definitions
@dataclass
class FunctionDef:
    name: str | None
    id: int
    is_public: int
    field_0xc: int
    return_var: int
    field_0x34: int
    
    code: array
    code_offset: int
    instructions: list | None
    instruction_strs: list[str] | None
    
    vars: list[Var]
    tables: list[Table]
    labels: list[Label]
    
    # analysis
    thread_references: list['FunctionDef'] = field(default_factory=list)
    thread2_references: list['FunctionDef'] = field(default_factory=list)

def read_function_definitions(section: bytes, code_section: bytes) -> list[FunctionDef]:
    arr = enumerate(array('I', section))
    code_section_arr = array('I', code_section)
    
    count = next(arr)[1]
    definitions = []
    
    for i, value in arr:
        id = next(arr)[1]
        is_public = next(arr)[1]
        field_0xc = next(arr)[1]
        code_offset = next(arr)[1]
        code_end = next(arr)[1]
        return_var = next(arr)[1]
        field_0x34 = next(arr)[1]
        
        code = code_section_arr[code_offset + 1:code_end + 1]
        
        if value == 0xFFFFFFFF:
            name = read_string(section, i + 9)
            
            for _ in range(next(arr)[1]):
                next(arr)
        else:
            assert value == 0
            name = None
        
        variables: list[Var] = []
        for i in range(next(arr)[1]):
            var = read_variable(arr, section, VarCategory.LocalVar)
            
            if var.name == None:
                assert (var.id & 0xFF) == 0
                var.alias = str((var.id >> 8) & 0xFF) # TODO: make this more exact
            
            variables.append(var)
        
        # TODO: table values don't work yet here
        tables: list[Table] = []
        for _ in range(next(arr)[1]):
            tables.append(read_table(arr, section))
        
        labels: list[Label] = []
        for _ in range(next(arr)[1]):
            label = read_label(arr, section)
            
            labels.append(label)
        
        # assign aliases to labels
        alphabet = iter(ascii_lowercase)
        for label in sorted(labels, key=lambda label: label.code_offset):
            if label.name is None:
                label.alias = next(alphabet, None)
        
        definitions.append(FunctionDef(name, id, is_public, field_0xc, return_var, field_0x34, code, code_offset, None, None, variables, tables, labels))
    
    assert len(definitions) == count
    return definitions

def analyze_function_def(fn: FunctionDef, symbol_ids: SymbolIds):
    # cache labels by their offset
    labels: dict[int, Label] = {}
    
    for label in fn.labels:
        labels[label.code_offset] = label
    
    # parse instructions
    arr = enumerate(fn.code)
    instructions = []
    
    for i, value in arr:
        try:
            options = cmds.ReadCmdOptions(value & 0xfffffeff, value & 0x100 != 0, fn.code_offset + i)
            
            if value & 0xfffffeff in cmds.INSTRUCTIONS.readers:
                instruction = cmds.INSTRUCTIONS.readers[value & 0xfffffeff](arr, symbol_ids, options)
                
                match instruction:
                    case cmds.ThreadCmd(func):
                        if isinstance(func, FunctionDef) and func is not fn:
                            func.thread_references.append(fn)
                    case cmds.Thread2Cmd(func):
                        if isinstance(func, FunctionDef) and func is not fn:
                            func.thread2_references.append(fn)
                    case cmds.LabelCmd(offset):
                        if offset in labels:
                            instruction.label = labels[offset]
                
                instructions.append(instruction)
            else:
                instructions.append(cmds.read_unknown_cmd(arr, symbol_ids, options))
        except StopIteration:
            pass
    
    fn.instructions = instructions

def print_function_def(fn: FunctionDef) -> str:
    return_var_var = next((var for var in fn.vars if var.id == fn.return_var), None)
    return_var = print_expr_or_var(return_var_var) if return_var_var is not None else hex(fn.return_var)
    
    result = f"""  - name: {fn.name if fn.name != None else 'null'}
    id: 0x{fn.id:x}
    is_public: {fn.is_public}
    field_0xc: 0x{fn.field_0xc:x}
    return_var: {return_var}
    field_0x34: 0x{fn.field_0x34:x}\n"""
    
    if fn.vars and len(fn.vars) > 0:
        result += "    \n    variables:\n"
        for var in fn.vars:
            result += print_var(var, 3)
    if fn.tables and len(fn.tables) > 0:
        result += "    \n    tables:\n"
        for table in fn.tables:
            result += print_table(table, 3)
    if fn.labels and len(fn.labels) > 0:
        result += "    \n    labels:\n"
        for var in fn.labels:
            result += print_label(var)
    
    if len(fn.thread_references) == 1 and len(fn.thread2_references) == 0:
        result += f"    \n    generated_from_thread: true # used by fn:{fn.thread_references[0].name}\n"
    elif len(fn.thread_references) == 0 and len(fn.thread2_references) == 1:
        result += f"    \n    generated_from_thread2: true # used by fn:{fn.thread2_references[0].name}\n"
    elif fn.instructions and len(fn.instructions) > 0:
        result += "    \n    "
        
        if len(fn.thread_references) >= 1:
            thread_references = ', '.join(print_expr_or_var(x) for x in fn.thread_references)
            result += f"# used by Threads: {thread_references}\n    "
        if len(fn.thread2_references) >= 1:
            thread2_references = ', '.join(print_expr_or_var(x) for x in fn.thread2_references)
            result += f"# used by Thread2s: {thread2_references}\n    "
        
        result += "body:\n"
        start_indented_block = False
        indentation = 0
        
        for inst in fn.instructions:
            if start_indented_block:
                start_indented_block = False
                indentation += 1
            
            match inst:
                case cmds.ReturnValCmd(is_const, var):
                    value = f"ReturnVal{'*' if is_const else ' '} {print_expr_or_var(var)}"
                case cmds.SetCmd(is_const, destination, source):
                    value = f"Set{'*' if is_const else ' '}  {print_expr_or_var(destination)} {print_expr_or_var(source, True)}"
                case cmds.CallCmd(is_const, func, args):
                    value = f"Call{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case cmds.CallAsThreadCmd(is_const, func, args):
                    value = f"CallAsThread{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case cmds.CallAsChildThreadCmd(is_const, func, args):
                    value = f"CallAsChildThread{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case cmds.CallVarCmd(is_const, func, args):
                    value = f"CallVar{'*' if is_const else '' } {func if isinstance(func, int) else func.name} {args}"
                case cmds.ReturnCmd():
                    if indentation > 0:
                        indentation -= 1
                    
                    value = f"Return"
                case cmds.GetArgsCmd(func, args):
                    value = f"GetArgs fn:{'self' if func.name == fn.name else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case cmds.IfCmd(condition, unused1, jump_to, unused2):
                    start_indented_block = True
                    value = f"If {print_expr_or_var(condition)}" # , {hex(unused1)}, {hex(jump_to)}, {hex(unused2)}
                case cmds.IfEqualCmd(var1, var2, jump_to):
                    start_indented_block = True
                    value = f"IfEqual ( {print_expr_or_var(var1)}, {print_expr_or_var(var2)} )" # , {hex(jump_to)}
                case cmds.IfNotEqualCmd(var1, var2, jump_to):
                    start_indented_block = True
                    value = f"IfNotEqual ( {print_expr_or_var(var1)}, {print_expr_or_var(var2)} )" # , {hex(jump_to)}
                case cmds.ElseCmd(jump_to):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"Else" #  ( {hex(jump_to)} )
                case cmds.ElseIfCmd(start_from, unused1, condition, unused2, jump_to, unused3):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    # value = f"ElseIf ( {hex(start_from)}, {hex(unused1)}, {print_expr_or_var(condition)}, {hex(unused2)}, {hex(jump_to)}, {hex(unused3)} )"
                    value = f"ElseIf {print_expr_or_var(condition)}"
                case cmds.EndIfCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndIf"
                case cmds.GotoLabelCmd(label):
                    value = f"GotoLabel {print_expr_or_var(label)}"
                case cmds.NoopCmd(opcode):
                    value = f"Noop_{hex(opcode)}"
                case cmds.LabelCmd(offset, label):
                    if label is None:
                        label_name = f"? (at {hex(offset)})"
                    elif not isinstance(label, Label):
                        label_name = print_expr_or_var(label)
                    elif label.name is not None:
                        label_name = label.name
                    elif label.alias is not None:
                        label_name = label.alias
                    else:
                        label_name = print_expr_or_var(label)
                    
                    value = f"Label {label_name}"
                case cmds.ThreadCmd(func, take_args, give_args) | cmds.Thread2Cmd(func, take_args, give_args):
                    start_indented_block = True
                    
                    opcode = "Thread1" if isinstance(inst, cmds.ThreadCmd) else "Thread2"
                    if isinstance(func, FunctionDef):
                        name_start = 1 if func.name is not None and func.name.startswith('_') else 0
                        label_or_func = json.dumps(func.name[name_start:func.name.rindex('_')] if func.name is not None else func.name)
                    else:
                        label_or_func = print_expr_or_var(func)
                    captures = ', '.join(print_expr_or_var(var) for var in give_args)
                    
                    value = f"{opcode} {label_or_func} Capture ( {captures} )"
                case cmds.DeleteRuntimeCmd(is_const, duration):
                    value = f"DeleteRuntime{'*' if is_const else '' } {print_expr_or_var(duration)}"                
                case cmds.WaitCmd(is_const, duration):
                    value = f"Wait{'*' if is_const else '' } {print_expr_or_var(duration)}"
                case cmds.WaitMsCmd(is_const, duration):
                    value = f"WaitMs{'*' if is_const else '' } {print_expr_or_var(duration)}"
                case cmds.SwitchCmd(var, unused, jump_offset):
                    start_indented_block = True
                    value = f"Switch {print_expr_or_var(var)}" # , {hex(unused)}, {hex(jump_offset)}                
                case cmds.CaseEqCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"Case{'*' if is_const else '' } == {print_expr_or_var(var)}" # , {hex(jump_offset)}       
                case cmds.CaseLteCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"Case{'*' if is_const else '' } <= {print_expr_or_var(var)}" # , {hex(jump_offset)}
                case cmds.CaseRangeCmd(is_const, lower, upper, jump_offset):
                    start_indented_block = True
                    value = f"CaseRange{'*' if is_const else '' } ( {print_expr_or_var(lower)} to {print_expr_or_var(upper)}" # , {hex(jump_offset)}
                case cmds.BreakSwitchCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"BreakSwitch"
                case cmds.EndSwitchCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndSwitch"
                case cmds.WhileCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"While{'*' if is_const else '' } {print_expr_or_var(var)}" # , {hex(jump_offset)} )
                case cmds.BreakCmd():
                    value = f"Break"
                case cmds.EndWhileCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndWhile"
                case cmds.ReadTableLengthCmd(is_const, arrayt):
                    value = f"ReadTableLength ( {print_expr_or_var(arrayt)} )"
                case cmds.ReadTableEntryCmd(is_const, arrayt, index):
                    value = f"ReadTableEntry ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)} )"
                case cmds.ReadTableEntryToVarCmd(is_const, arrayt, index, var):
                    value = f"ReadTableEntryToVar ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(var)} )"
                case cmds.ReadTableEntriesVec2Cmd(is_const, arrayt, index, x, y):
                    value = f"ReadTableEntriesVec2 ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(x)}, {print_expr_or_var(y)} )"
                case cmds.ReadTableEntriesVec3Cmd(is_const, arrayt, index, x, y, z):
                    value = f"ReadTableEntriesVec3 ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(x)}, {print_expr_or_var(y)}, {print_expr_or_var(z)} )"
                case cmds.TableGetIndexCmd(is_const, arrayt, occurance, var):
                    value = f"TableGetIndex ( {print_expr_or_var(arrayt)}, {print_expr_or_var(occurance)}, {print_expr_or_var(var)} )"
                case cmds.WaitCompletedCmd(is_const, runtime):
                    value = f"WaitCompleted{'*' if is_const else '' } {print_expr_or_var(runtime)}"
                case cmds.WaitWhileCmd(condition):
                    value = f"WaitWhile {print_expr_or_var(condition)}"
                case cmds.ToIntCmd(var):
                    value = f"ToInt {print_expr_or_var(var)}"
                case cmds.ToFloatCmd(var):
                    value = f"ToFloat {print_expr_or_var(var)}"
                case cmds.LoadKSMCmd(var):
                    value = f"LoadKSM {print_expr_or_var(var)}"
                case cmds.GetArgCountCmd():
                    value = f"GetArgCount"
                case cmds.SetKSMUnkCmd(is_const, destination, source):
                    value = f"SetKSMUnk{'*' if is_const else ''} {print_expr_or_var(destination)} {print_expr_or_var(source, True)}"
                case cmds.UnknownCmd(opcode, is_const, args):
                    value = f"Unk_0x{opcode:x}{'*' if is_const else ' '} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case _:
                    raise Exception()
            
            if ': ' in value:
                result += f"      - {'    ' * indentation}'{value}'\n"
            else:
                result += f"      - {'    ' * indentation}{value}\n"
    
    return result

def print_function_imports(sections: list[bytes], symbol_ids: SymbolIds) -> str:
    # section 5 (function imports)
    imports = read_function_imports(sections[5])
    
    if len(imports) == 0:
        return ""
    
    out_str = '\nimports:\n'
    
    for fn in imports:
        symbol_ids.add(fn)
        out_str += print_function_import(fn)
    
    return out_str

def print_function_definitions(sections: list[bytes], symbol_ids: SymbolIds) -> str:
    # section 1 (function definitions)
    definitions = read_function_definitions(sections[1], sections[7])
    
    if len(definitions) == 0:
        return ""
    
    for fn in definitions:
        symbol_ids.add(fn)
    
    for fn in definitions:
        if fn.code is not None and len(fn.code) > 0:
            local_symbol_ids = symbol_ids.copy()
            
            for var in fn.vars:
                local_symbol_ids.add(var)
            for table in fn.tables:
                local_symbol_ids.add(table)
            for unk in fn.labels:
                local_symbol_ids.add(unk)
            
            analyze_function_def(fn, local_symbol_ids)
    
    out_str = '\ndefinitions:\n'
    is_first = True
    
    for fn in definitions:
        if not is_first:
            if out_str.endswith('  \n'):
                out_str = out_str[:-5] + '\n'
            else:
                out_str += '    \n'
        
        out_str += print_function_def(fn)
        is_first = False
    
    return out_str

def function_definitions_from_yaml(function_definitions: list) -> list[FunctionDef]:
    out: list[FunctionDef] = []
    
    for obj in function_definitions:
        assert isinstance(obj, dict), "Function definition has to be an object"
        
        if 'name' not in obj or obj['name'] is None:
            name = None
        else:
            assert isinstance(obj['name'], str), "Function name has to be a string"
            name = obj['name']
        
        # TODO: de-boilerplate this into a helper class
        assert 'id' in obj and isinstance(obj['id'], int), "Function id (required) has to be an integer"
        id = obj['id']
        
        assert 'is_public' in obj and isinstance(obj['is_public'], int), "Function's 'is_public' (required) has to be an integer"
        is_public = obj['is_public']
        
        assert 'field_0xc' in obj and isinstance(obj['field_0xc'], int), "Function's 'field_0xc' (required) has to be an integer"
        field_0xc = obj['field_0xc']
        
        assert 'return_var' in obj and isinstance(obj['return_var'], (str, int)), "Function's 'return_var' (required) has to be a string or integer"
        return_var_str = obj['return_var']
        
        assert 'field_0x34' in obj and isinstance(obj['field_0x34'], int), "Function's 'field_0x34' (required) has to be an integer"
        field_0x34 = obj['field_0x34']
        
        if 'variables' in obj and obj['variables'] is not None:
            variables_obj = obj['variables']
            assert isinstance(variables_obj, list), "Function variables have to be a list of variables"
            
            vars = []
            
            for var_obj in variables_obj:
                assert isinstance(var_obj, dict), "Variable has to be an object"
                vars.append(var_from_yaml(var_obj, VarCategory.LocalVar))
        else:
            vars = []
        
        assert 'tables' not in obj, "TODO"
        assert 'labels' not in obj, "TODO"
        
        code_offset = 0 # TODO
        code = array('I', [])
        
        tables = []
        labels = []
        
        if 'body' in obj and obj['body'] is not None:
            assert isinstance(obj['body'], list), "Function body has to be a list of instructions"
            body_obj = obj['body']
            
            for line in body_obj:
                assert isinstance(line, str), "Function body has to be a list of instructions"
        else:
            raise NotImplementedError()
        
        out.append(FunctionDef(name, id, is_public, field_0xc, 0, field_0x34, code, code_offset, None, body_obj, vars, tables, labels))
    
    return out

def write_function_def(fn: FunctionDef) -> bytearray:
    out = array('I')
    
    out.append(0xFFFFFFFF if fn.name is not None else 0)
    out.append(fn.id)
    out.append(fn.is_public)
    out.append(fn.field_0xc)
    out.append(0) # code offset and code end will be patched in later
    out.append(0)
    out.append(fn.return_var)
    out.append(fn.field_0x34)
    
    if fn.name is not None:
        out.extend(write_string(fn.name))
    
    if len(fn.vars) > 0:
        out.append(len(fn.vars))
        
        for var in fn.vars:
            out.extend(write_variable(var))
    
    out.append(0)
    out.append(0)
    
    return bytearray(out)

def parse_function_definitions(input_file: dict, symbol_ids: SymbolIds) -> tuple[list[FunctionDef], bytearray]:
    if 'definitions' not in input_file:
        return [], bytearray([0, 0, 0, 0])
    
    assert isinstance(input_file['definitions'], list)
    definitions = function_definitions_from_yaml(input_file['definitions'])
    
    out = bytearray(array('I', [len(definitions)]))
    
    for definition in definitions:
        symbol_ids.add(definition)
        out.extend(write_function_def(definition))
    
    return definitions, out

def parse_function_implementations(funcs: list[FunctionDef], symbol_ids: SymbolIds) -> bytearray:
    out = array('I')
    
    out.append(0) # amount of 32-bit words in section, will be patched in later
    
    for func in funcs[::-1]:
        assert func.instructions is not None
        
        for cmd in func.instructions:
            assert type(cmd) in cmds.INSTRUCTIONS.writers, f"Instruction {type(cmd).__name__} not supported yet"
            cmds.INSTRUCTIONS.writers[type(cmd)](cmd, out)
    
    return bytearray(out)
