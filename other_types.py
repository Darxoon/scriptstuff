from array import array
from dataclasses import dataclass, field
from enum import Enum
from itertools import chain

import cmds
import functions
from tables import Table
from util import SymbolIds, read_string, write_string
from variables import Var, VarCategory

# function imports
# (I feel like I'm really misunderstanding this type)
class ImportType(Enum):
    LocalVar = 0
    ScriptVar = 1
    Unk1 = 2
    Table = 3
    Label = 4
    Unk2 = 5
    Func = 7

@dataclass
class ScriptImport:
    name: str | None
    field_0x4: int # short
    type: ImportType
    id: int

def read_function_imports(section: bytes) -> list[ScriptImport]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    imports = []
    
    for i, value in arr:
        field_0x4 = next(arr)[1] & 0xFFFF
        type = next(arr)[1]
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
        
        imports.append(ScriptImport(name, field_0x4, ImportType(type), id))
    
    assert len(imports) == count
    return imports

def write_import(fn: ScriptImport) -> array[int]:
    out = array('I')
    
    out.append(0xFFFFFFFF if fn.name is not None else 0)
    out.append(fn.field_0x4)
    out.append(fn.type.value)
    out.append(0) # ?
    out.append(fn.id) # ?
    out.append(0) # ?
    out.append(0) # ?
    
    if fn.name is not None:
        out.extend(write_string(fn.name))
    
    return out

def print_function_import(fn: ScriptImport) -> str:
    assert fn.name is not None, "Imported function name is None"
    
    return f"  - {{ id: 0x{fn.id:x}, name: '{fn.name}', field_0x4: {fn.field_0x4}, type: {fn.type.name} }}\n"

def function_import_from_yaml(obj: dict) -> ScriptImport:
    assert 'id' in obj and isinstance(obj['id'], int), "Import id (required) has to be an integer"
    id = obj['id']
    
    if 'name' in obj:
        assert isinstance(obj['name'], str), "Import name has to be an string"
        name = obj['name']
    else:
        name = None
    
    assert 'field_0x4' in obj and isinstance(obj['field_0x4'], int), "Import field_0x4 (required) has to be an integer"
    field_0x4 = obj['field_0x4']
    
    assert 'type' in obj and isinstance(obj['type'], str), f"\
        Import type (required) has to be a string with value {', '.join(value.name for value in ImportType)}"
    type = ImportType[obj['type']]
    
    return ScriptImport(name, field_0x4, type, id)

def parse_imports(input_file: dict, symbol_ids: SymbolIds) -> bytearray:
    if 'imports' not in input_file:
        return bytearray([0, 0, 0, 0])
    
    assert isinstance(input_file['imports'], list), "Script imports have to be a list"
    
    imports = []
    for obj in input_file['imports']:
        assert isinstance(obj, dict), "Script import has to be an object"
        imports.append(function_import_from_yaml(obj))
    
    out = array('I', [len(imports)])
    
    for fn in imports:
        symbol_ids.add(fn)
        out.extend(write_import(fn))
    
    return bytearray(out)

# labels
@dataclass
class Label:
    name: str | None
    alias: str | None
    id: int
    code_offset: int

def read_label(arr: enumerate[int], section: bytes) -> Label:
    offset, value = next(arr)
    id = next(arr)[1]
    code_offset = next(arr)[1]
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 6)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    return Label(name, None, id, code_offset)

def print_label(label: Label) -> str:
    out_str = "      - "
    
    if label.name is not None:
        out_str += f"name: {label.name}\n        "
    if label.alias is not None:
        out_str += f"alias: {label.alias}\n        "
    
    out_str += f"""id: 0x{label.id:x}
        code_offset: 0x{label.code_offset:x}\n"""
    
    return out_str

# script expressions
@dataclass
class ExprSymbol:
    label: str

EXPR_SYMBOLS = {
    0x3f: ExprSymbol('next_function'),
    0x41: ExprSymbol('('),
    0x42: ExprSymbol(')'),
    0x43: ExprSymbol('||'),
    0x44: ExprSymbol('&&'),
    
    0x45: ExprSymbol('|'),
    0x46: ExprSymbol('&'),
    0x47: ExprSymbol('^'),
    0x48: ExprSymbol('<<'),
    0x49: ExprSymbol('>>'),
    
    0x4a: ExprSymbol('=='),
    0x4b: ExprSymbol('!='),
    0x4c: ExprSymbol('>'),
    0x4d: ExprSymbol('<'),
    0x4e: ExprSymbol('>='),
    0x4f: ExprSymbol('<='),
    
    0x52: ExprSymbol('%'),
    0x53: ExprSymbol('+'),
    0x54: ExprSymbol('-'),
    0x55: ExprSymbol('*'),
    0x56: ExprSymbol('/'),
}

@dataclass
class Expr:
    elements: list['Var | cmds.CallCmd | int'] = field(default_factory=lambda: [])

def read_expr(initial_element: int | None, arr: enumerate[int], symbol_ids: SymbolIds, raise_on_ending_sequence = False) -> Expr:
    elements = []
    
    values = chain([(0, initial_element)], arr) if initial_element is not None else arr
    
    for _, value in values:
        if value == 0x40:
            break
        
        if value == 0xc:
            elements.append(cmds.read_call_cmd(arr, symbol_ids, cmds.ReadCmdOptions(0xc, False)))
            continue
        
        if value in EXPR_SYMBOLS:
            var = EXPR_SYMBOLS[value]
        else:
            var = symbol_ids.get(value)
        elements.append(var)
    
    return Expr(elements)

def print_expr_or_var(value, braces_around_expression = False) -> str:
    match value:
        case Expr(elements):
            content = ' '.join(print_expr_or_var(x) for x in elements)
            if braces_around_expression:
                return f'( {content} )'
            else:
                return content
        case ExprSymbol(label):
            return label
        case Var(name, alias, category, id, data_type, flags, user_data):
            if name is not None:
                return f"{category.name}:{name}"
            elif alias is not None:
                return f"{category.name}:{alias}"
            elif category == VarCategory.Const and user_data is not None:
                return f"{user_data}`" if isinstance(user_data, (int, float)) else repr(user_data)
            else:
                return f"{category.name}:0x{id:x}"
        case ScriptImport(name) | functions.FunctionDef(name):
            return f"fn:{name}"
        case Label(name, alias, id):
            if name is not None:
                return f"label:{name}"
            elif alias is not None:
                return f"label:{alias}"
            else:
                return f"label:{hex(id)}"
        case Table(name, id):
            if name is not None:
                return f"table:{name}"
            else:
                return f"table:{hex(id)}"
        case cmds.CallCmd(is_const, func, args):
            content = f"Call{'*' if is_const else ''} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
            if braces_around_expression:
                return f'( {content} )'
            else:
                return content
        case int(n):
            return f"?0x{n:x}"
        case _:
            raise Exception(f"Unknown thing {repr(value)}")
