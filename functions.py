from array import array
from dataclasses import dataclass
from sys import argv

from tables import Table, print_table, read_table
from variables import Var, print_var, read_variable

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')


@dataclass
class FunctionImport:
    name: str
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
    return f"""  - name: {fn.name if fn.name != None else 'null'}
    field_0x4: {fn.field_0x4}
    field_0x8: {fn.field_0x8}
    id: 0x{fn.id:x}\n"""


@dataclass
class ScriptUnk:
    name: str
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


@dataclass
class Instruction:
    value: int
    label: str
    empty_line_after: bool

INSTRUCTIONS = {
    # 0xc: Instruction(0xc, "block_a"),
    # 0x3d: Instruction(0x3d, "block_b"),
    # 0x18: Instruction(0x18, "block_c"),
    # 0x40: Instruction(0x40, "end_block"),
    # 0x9: Instruction(0x9, "header", False),
    0x8: Instruction(0x8, "header_end", True),
    0x11: Instruction(0x11, "yield", True),
}


@dataclass
class FunctionDef:
    name: str
    id: int
    is_public: int
    field_0xc: int
    field_0x30: int # some variable's handle?
    field_0x34: int
    
    code: list[int]
    
    vars: None
    tables: None
    unk: None

def read_function_definitions(section: bytes, code_section: bytes) -> list[FunctionDef]:
    arr = enumerate(array('I', section))
    code_arr = array('I', code_section)
    
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
        
        code = code_arr[code_offset:code_end]
        
        if value == 0xFFFFFFFF:
            name = read_string(section, i + 9)
            
            for _ in range(next(arr)[1]):
                next(arr)
        else:
            assert value == 0
            name = None
        
        variables = []
        for _ in range(next(arr)[1]):
            variables.append(read_variable(arr, section))
            
        tables = []
        for _ in range(next(arr)[1]):
            tables.append(read_table(arr, section))
        
        unk = []
        for _ in range(next(arr)[1]):
            unk.append(read_unk(arr, section))
        
        definitions.append(FunctionDef(name, id, is_public, field_0xc, field_0x30, field_0x34, code, variables, tables, unk))
    
    assert len(definitions) == count
    return definitions

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
    
    if fn.code and len(fn.code) > 0:
        assert 8 in fn.code, f"Function {fn.name} does not have a header"
        result += "    \n    code_header:\n"
        
        
        is_header = True
        for x in fn.code:
            if x == 8:
                result += "    \n    body:\n"
                is_header = False
                continue
            
            match symbol_ids.get(x, None):
                case FunctionImport(name):
                    value = f"call {name} # 0x{x:x} (imported)"
                case FunctionDef(name):
                    if is_header:
                        value = f"{name} # 0x{x:x} (local)"
                    else:
                        value = f"call {name} # 0x{x:x} (local)"
                case Var(name, _, status, flags, reference_value):
                    if name:
                        value = f"push var {name} # 0x{x:x} (status {status} flags {'0x' if flags != 0 else ''}{flags:x})"
                    elif isinstance(reference_value, str):
                        value = f"push ref {reference_value} # 0x{x:x} (status {status} flags {'0x' if flags != 0 else ''}{flags:x})"
                    else:
                        value = f"0x{x:x} # variable (status {status} flags {'0x' if flags != 0 else ''}{flags:x})"
                case Table(name):
                    value = f"push table {name} # 0x{x:x}"
                case None:
                    if not is_header and x in INSTRUCTIONS:
                        value = f"{INSTRUCTIONS[x].label} # 0x{x:x}{"\n      " if INSTRUCTIONS[x].empty_line_after else ""}"
                    else:
                        value = f"0x{x:x}"
                case _:
                    raise Exception(f"Unknown symbol {symbol_ids[x]}")
            
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
    definitions = read_function_definitions(sections[1], sections[7])
    
    for fn in definitions:
        symbol_ids[fn.id] = fn
    
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
