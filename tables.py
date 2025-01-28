from array import array
from dataclasses import dataclass
from sys import argv
from util import SymbolIds
from variables import Var, VarCategory

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')


@dataclass
class Table:
    name: str | None
    id: int
    datatype: int
    length: int
    start_offset: int
    datatype2: int
    values: list

def read_table_values(section: bytearray, tables: list[Table], symbol_ids: SymbolIds) -> list[Table]:
    for table in tables:
        # ?? 
        table.datatype2 = array('I', section[table.start_offset * 4 : table.start_offset * 4 + 4])[0]
        
        start = (table.start_offset * 4) + 4
        match table.datatype:
            case 0x0: # constant
                end = start + (table.length * 4)
                section_slice = section[start : end]
                arr = enumerate(array('I', section_slice))
                for _, val in arr:
                    val = symbol_ids.get(val)
                    table.values.append(val)
            case 0x1: # int
                end = start + (table.length * 4)
                section_slice = section[start : end]
                arr = enumerate(array('I', section_slice))
                for _, val in arr:
                    table.values.append(val)
            case 0x2: # float
                end = start + (table.length * 4)
                section_slice = section[start : end]
                arr = enumerate(array('f', section_slice))
                for _, val in arr:
                    table.values.append(val)
            case 0x3: # byte
                end = start + table.length
                section_slice = section[start : end]
                arr = enumerate(array('B', section_slice))
                for _, val in arr:
                    table.values.append(val)
            case _:
                print(f"Unknown array data type {table.datatype} ...skipping this table's values!")
                table.values = []
    
    return tables

def read_table(arr: enumerate[int], section: bytes):
    offset, value = next(arr)
    id = next(arr)[1]
    datatype = next(arr)[1]
    length = next(arr)[1]
    start_offset = next(arr)[1]
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 6)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    return Table(name, id, datatype, length, start_offset, 0, [])

def read_table_defs(section: bytes, code_section: bytes, symbol_ids: SymbolIds) -> list[Table]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    tables = []
    
    for _ in range(count):
        tables.append(read_table(arr, section))
    
    tables = read_table_values(code_section, tables, symbol_ids)
    
    assert next(arr, None) == None
    return tables

def print_var(var: Var):
    if var.name is not None:
        return f"{var.category.name}:{var.name}"
    elif var.alias is not None:
        return f"{var.category.name}:{var.alias}"
    elif var.category == VarCategory.Const and var.user_data is not None:
        return f"{var.user_data}`" if isinstance(var.user_data, int) else repr(var.user_data)
    else:
        return f"{var.category.name}:{hex(var.id)}"


def print_table(table: Table, indentation_level: int = 1) -> str:
    indent = '  ' * indentation_level
    text = f"""{indent}- name: {table.name}
{indent}  id: {hex(table.id)}
{indent}  datatype: {hex(table.datatype)}
{indent}  datatype2: {hex(table.datatype2)} # ?
{indent}  length: {hex(table.length)}
{indent}  start_offset: {hex(table.start_offset)}\n"""

    if table.values is not None and len(table.values) > 0:
        text += f"{indent}  values:\n"
        
        for val in table.values:
            text += f"{indent}    - {print_var(val) if isinstance(val, Var) else val}\n"
    
    return text


def write_tables(sections: list[bytes], symbol_ids: SymbolIds):
    # section 3
    tables = read_table_defs(sections[3], sections[7], symbol_ids)
        
    for table in tables:
        symbol_ids.add(table)
    
    out_str = 'tables:\n'
    for table in tables:
        out_str += print_table(table)
    
    with open(argv[1] + '.tables.yaml', 'w', encoding='utf-8') as f:
        f.write(out_str)
