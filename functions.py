from array import array
from dataclasses import dataclass
from sys import argv

from tables import Table, print_table, read_table
from variables import Var, VarCategory, print_var, read_variable

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')


# function imports
@dataclass
class FunctionImport:
    name: str | None
    field_0x4: int # short
    field_0x8: int
    id: int

def read_function_imports(section: bytes) -> list[FunctionImport]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    imports = []
    
    for i, value in arr:
        field_0x4 = next(arr)[1] & 0xFFFF
        field_0x8 = next(arr)[1]
        next(arr) # unused
        
        id = next(arr)[1]
        next(arr) # unused
        next(arr) # unused
        
        if value == 0xFFFFFFFF:
            name = read_string(section, i + 8)
            
            for _ in range(next(arr)[1]):
                next(arr)
        else:
            assert value == 0
            name = None
        
        imports.append(FunctionImport(name, field_0x4, field_0x8, id))
    
    assert len(imports) == count
    return imports

def print_function_import(fn: FunctionImport) -> str:
    assert fn.name is not None, "Imported function name is None"
    
    return f"  - {{ id: 0x{fn.id:x}, name: '{fn.name}', field_0x4: {fn.field_0x4}, field_0x8: {fn.field_0x8} }}\n"


# ScriptUnk (?)
@dataclass
class ScriptUnk:
    name: str | None
    id: int
    field_0x8: int

def read_unk(arr: enumerate[int], section: bytes):
    offset, value = next(arr)
    id = next(arr)[1]
    field_0x8 = next(arr)[1]
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 6)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    return ScriptUnk(name, id, field_0x8)

def print_unk(unk: ScriptUnk) -> str:
    return f"""      - name: {unk.name if unk.name != None else 'null'}
        id: 0x{unk.id:x}
        field_0x8: 0x{unk.field_0x8:x}\n"""


# script expressions
@dataclass
class Expr:
    elements: list[int]

def read_expr(initial_element: int | None, arr: enumerate[int]) -> Expr:
    elements = []
    
    if initial_element is not None:
        elements.append(initial_element)
    
    for _, value in arr:
        if value == 0x40:
            break
        
        elements.append(value)
    
    return Expr(elements)

def print_expr_or_var(value, braces_around_expression = False) -> str:
    match value:
        case Expr(elements):
            content = ' '.join(f"?0x{x:x}" for x in elements)
            if braces_around_expression:
                return f'( {content} )'
            else:
                return content
        case Var(name, category, id, status, flags, user_data):
            if name is not None:
                return f"{category.name}:{name}"
            elif category == VarCategory.Const and user_data is not None:
                return f"{user_data}`" if isinstance(user_data, int) else repr(user_data)
            else:
                return f"{category.name}:0x{id:x}"
        case FunctionImport(name):
            return f"fn:{name}"
        case int(n):
            return f"?0x{n:x}"
        case _:
            raise Exception("Unknown thing")

# script instructions
@dataclass 
class CallCmd:
    is_const: bool
    func: 'FunctionImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CallCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if is_const:
            var = symbol_ids.get(value, value)
            args.append(var)
        else:
            args.append(read_expr(value, arr))
    
    return CallCmd(is_const, func, args)

@dataclass 
class CallVarCmd:
    is_const: bool
    func: Var | int
    args: list[Expr | Var | int]

def read_call_var_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CallVarCmd:
    func_int = next(arr)[1]
    func = symbol_ids[func_int, func_int]
    assert isinstance(func, Var) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if is_const:
            var = symbol_ids.get(value, value)
            args.append(var)
        else:
            args.append(read_expr(value, arr))
    
    return CallVarCmd(is_const, func, args)

@dataclass
class SetCmd:
    is_const: bool
    destination: Var | int
    value: Expr | Var | int

def read_set_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> SetCmd:
    destination_int = next(arr)[1]
    destination = symbol_ids.get(destination_int, destination_int)
    assert isinstance(destination, Var) or isinstance(destination, int)
    
    if is_const:
        value_int = next(arr)[1]
        value = symbol_ids.get(value_int, value_int)
        assert isinstance(value, Var) or isinstance(value, int)
    else:
        value = read_expr(None, arr)
    
    return SetCmd(is_const, destination, value)

@dataclass
class PopFuncStackCmd:
    pass

def read_pop_func_stack_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> PopFuncStackCmd:
    return PopFuncStackCmd()

@dataclass
class GetArgsCmd:
    func: 'FunctionDef'
    args: list[Var | int]

def read_get_args_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> GetArgsCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionDef)
    
    args = []
    for _, value in arr:
        if value == 0x8:
            break
        
        var = symbol_ids.get(value, value)
        assert isinstance(var, Var) or isinstance(var, int)
        args.append(var)
        
    return GetArgsCmd(func, args)

# more known commands: Pop, Switch, Read[n], Write

@dataclass
class UnknownCmd:
    opcode: int
    is_const: bool
    args: list[int]

def read_unknown_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> UnknownCmd:
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        args.append(value)
    
    return UnknownCmd(opcode, is_const, args)

INSTRUCTIONS = {
    0x5: read_get_args_cmd,
    0x9: read_pop_func_stack_cmd,
    0xc: read_call_cmd,
    0x80: read_call_var_cmd,
    0x3d: read_set_cmd,
    # 0x29: read_switch,
}


# function definitions
@dataclass
class FunctionDef:
    name: str | None
    id: int
    is_public: int
    field_0xc: int
    field_0x30: int # some variable's handle?
    field_0x34: int
    
    code: array[int]
    instructions: list | None
    
    vars: list[Var]
    tables: list[Table]
    unk: list[ScriptUnk]

def read_function_definitions(section: bytes, code_section: bytes, symbol_ids: dict) -> list[FunctionDef]:
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
        field_0x30 = next(arr)[1]
        field_0x34 = next(arr)[1]
        
        code = code_section_arr[code_offset:code_end]
        
        if value == 0xFFFFFFFF:
            name = read_string(section, i + 9)
            
            for _ in range(next(arr)[1]):
                next(arr)
        else:
            assert value == 0
            name = None
        
        variables = []
        for _ in range(next(arr)[1]):
            variables.append(read_variable(arr, section, VarCategory.Func))
            
        tables = []
        for _ in range(next(arr)[1]):
            tables.append(read_table(arr, section))
        
        unk = []
        for _ in range(next(arr)[1]):
            unk.append(read_unk(arr, section))
        
        definitions.append(FunctionDef(name, id, is_public, field_0xc, field_0x30, field_0x34, code, None, variables, tables, unk))
    
    assert len(definitions) == count
    return definitions

def analyze_function_def(fn: FunctionDef, symbol_ids: dict):
    arr = enumerate(fn.code)
    instructions = []
    
    for _, value in arr:
        try:
            if value & 0xfffffeff in INSTRUCTIONS:
                instructions.append(INSTRUCTIONS[value & 0xfffffeff](arr, symbol_ids, value & 0xfffffeff, value & 0x100 != 0))
            else:
                instructions.append(read_unknown_cmd(arr, symbol_ids, value & 0xfffffeff, value & 0x100 != 0))
        except StopIteration:
            pass
    
    fn.instructions = instructions

def print_function_def(fn: FunctionDef, symbol_ids: dict) -> str:
    result = f"""  - name: {fn.name if fn.name != None else 'null'}
    id: 0x{fn.id:x}
    is_public: {fn.is_public}
    field_0xc: 0x{fn.field_0xc:x}
    field_0x30: 0x{fn.field_0x30:x}
    field_0x34: 0x{fn.field_0x34:x}\n"""
    
    if fn.vars and len(fn.vars) > 0:
        result += "    \n    variables:\n"
        for var in fn.vars:
            result += print_var(var, 3)
    if fn.tables and len(fn.tables) > 0:
        result += "    \n    tables:\n"
        for table in fn.tables:
            result += print_table(table, 3)
    if fn.unk and len(fn.unk) > 0:
        result += "    \n    unknown:\n"
        for var in fn.unk:
            result += print_unk(var)
    
    if fn.instructions and len(fn.instructions) > 0:
        result += "    \n    body:\n"
        
        for inst in fn.instructions:
            match inst:
                case SetCmd(is_const, destination, source):
                    value = f"Set{'*' if is_const else ' '} {print_expr_or_var(destination)} {print_expr_or_var(source, True)}"
                case CallCmd(is_const, func, args):
                    value = f"Call{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallVarCmd(is_const, func, args):
                    value = f"Call{'*' if is_const else '' } {func if isinstance(func, int) else func.name} {args}"
                case PopFuncStackCmd():
                    value = f"PopFuncStack"
                case GetArgsCmd(func, args):
                    value = f"GetArgs self:{func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case UnknownCmd(opcode, is_const, args):
                    value = f"Unk_0x{opcode:x}{'*' if is_const else ' '} ( {', '.join(f"?0x{x:x}" for x in args)} )"
            
            if ': ' in value:
                result += f"      - '{value}'\n"
            else:
                result += f"      - {value}\n"
    
    return result

def write_functions(sections: list[bytes], symbol_ids: dict):
    # section 5 (function imports)
    imports = read_function_imports(sections[5])
    
    for fn in imports:
        symbol_ids[fn.id] = fn
    
    out_str = 'imports:\n'
    for fn in imports:
        out_str += print_function_import(fn)
    
    # section 1 (function definitions)
    definitions = read_function_definitions(sections[1], sections[7], symbol_ids)
    
    for fn in definitions:
        symbol_ids[fn.id] = fn
    
    for fn in definitions:
        if fn.code is not None and len(fn.code) > 0:
            analyze_function_def(fn, symbol_ids)
    
    out_str += 'definitions:\n'
    is_first = True
    for fn in definitions:
        if not is_first:
            if out_str.endswith('  \n'):
                out_str = out_str[:-5] + '\n'
            else:
                out_str += '    \n'
        
        out_str += print_function_def(fn, symbol_ids)
        is_first = False
    
    with open(argv[1] + '.functions.yaml', 'w') as f:
        f.write(out_str)
