from array import array
from dataclasses import dataclass
from sys import argv

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
    return f"""  - name: {fn.name}
    field_0x4: {fn.field_0x4}
    field_0x8: {fn.field_0x8}
    id: 0x{fn.id:x}\n"""



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
        
        assert next(arr)[1] == 0, "Variables"
        assert next(arr)[1] == 0, "Tables"
        assert next(arr)[1] == 0, "Unknown"
        
        definitions.append(FunctionDef(name, id, is_public, field_0xc, field_0x30, field_0x34, code))
    
    assert len(definitions) == count
    return definitions


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
    
    with open(argv[1] + '.functions.yaml', 'w') as f:
        f.write(out_str)
