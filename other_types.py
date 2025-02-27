from array import array
from dataclasses import dataclass
from enum import Enum

from util import read_string

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

def print_function_import(fn: ScriptImport) -> str:
    assert fn.name is not None, "Imported function name is None"
    
    return f"  - {{ id: 0x{fn.id:x}, name: '{fn.name}', field_0x4: {fn.field_0x4}, type: {fn.type.name} }}\n"

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
