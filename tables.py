from array import array
from dataclasses import dataclass
from sys import argv

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')


@dataclass
class Table:
    name: str | None
    id: int
    field_0x8: int
    field_0xc: int
    field_0x10: int

def read_table(arr: enumerate[int], section: bytes):
    offset, value = next(arr)
    id = next(arr)[1]
    field_0x8 = next(arr)[1]
    field_0xc = next(arr)[1]
    field_0x10 = next(arr)[1]
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 6)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    return Table(name, id, field_0x8, field_0xc, field_0x10)

def read_table_defs(section: bytes) -> list[Table]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    tables = []
    
    for _ in range(count):
        tables.append(read_table(arr, section))
    
    assert next(arr, None) == None
    return tables

def print_table(table: Table, indentation_level: int = 1) -> str:
    indent = '  ' * indentation_level
    
    return f"""{indent}- name: {table.name}
{indent}  id: 0x{table.id:x}
{indent}  field_0x8: 0x{table.field_0x8:x}
{indent}  field_0xc: 0x{table.field_0xc:x}
{indent}  field_0x10: 0x{table.field_0x10:x}\n"""


def write_tables(sections: list[bytes], symbol_ids: dict):
    # section 3
    tables = read_table_defs(sections[3])
    
    for table in tables:
        symbol_ids[table.id] = table
    
    out_str = 'tables:\n'
    for table in tables:
        out_str += print_table(table)
    
    with open(argv[1] + '.tables.yaml', 'w') as f:
        f.write(out_str)
