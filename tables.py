from array import array
from dataclasses import dataclass
from enum import Enum
from sys import argv
from util import SymbolIds, read_string
from variables import Var, VarCategory

class TableDataType(Enum):
    Var = 0
    Int = 1
    Float = 2
    Byte = 3

@dataclass
class Table:
    name: str | None
    id: int
    data_type: TableDataType
    length: int
    start_offset: int
    datatype2: int
    values: list

def read_table_values(section: bytes, tables: list[Table], symbol_ids: SymbolIds) -> list[Table]:
    for table in tables:
        # ?? 
        table.datatype2 = array('I', section[table.start_offset * 4 : table.start_offset * 4 + 4])[0]
        
        start = (table.start_offset * 4) + 4
        match table.data_type:
            case TableDataType.Var:
                end = start + (table.length * 4)
                section_slice = section[start : end]
                arr = enumerate(array('I', section_slice))
                for _, val in arr:
                    val = symbol_ids.get(val)
                    table.values.append(val)
            case TableDataType.Int:
                end = start + (table.length * 4)
                section_slice = section[start : end]
                arr = enumerate(array('I', section_slice))
                for _, val in arr:
                    table.values.append(val)
            case TableDataType.Float:
                end = start + (table.length * 4)
                section_slice = section[start : end]
                arr = enumerate(array('f', section_slice))
                for _, val in arr:
                    table.values.append(val)
            case TableDataType.Byte:
                end = start + table.length
                section_slice = section[start : end]
                arr = enumerate(array('B', section_slice))
                for _, val in arr:
                    table.values.append(val)
            case _:
                raise Exception(f"Unknown table data type {table.data_type}")
    
    return tables

def read_table(arr: enumerate[int], section: bytes):
    offset, value = next(arr)
    id = next(arr)[1]
    type_int = next(arr)[1]
    length = next(arr)[1]
    start_offset = next(arr)[1]
    
    data_type = TableDataType(type_int)
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 6)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    return Table(name, id, data_type, length, start_offset, 0, [])

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
{indent}  data_type: {table.data_type.name}
{indent}  datatype2: {hex(table.datatype2)} # ?
{indent}  length: {hex(table.length)}
{indent}  start_offset: {hex(table.start_offset)}\n"""

    if table.values is not None and len(table.values) > 0:
        text += f"{indent}  values:\n"
        
        for val in table.values:
            text += f"{indent}    - {print_var(val) if isinstance(val, Var) else val}\n"
    
    return text


def print_tables(sections: list[bytes], symbol_ids: SymbolIds) -> str:
    # section 3
    tables = read_table_defs(sections[3], sections[7], symbol_ids)
        
    if len(tables) == 0:
        return ''
    
    out_str = '\ntables:'

    for table in tables:
        symbol_ids.add(table)
        out_str += '\n' + print_table(table)
    
    return out_str
