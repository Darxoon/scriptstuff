#!/bin/env python3
from array import array
from dataclasses import dataclass
from functools import partial
from math import ceil
from struct import unpack
from sys import argv
from typing import Callable, Dict, TypeVar

T = TypeVar('T')

def read_ksm_container(file: bytes) -> list[bytes]:
    header = list(unpack('4siiiiiiiiii', file[:0x2c]))
    assert header[0] == b'KSMR'
    assert header[1] == 0x10300
    assert header[10] == 0
    
    header[10] = len(file) // 4
    
    # god python can be so beautiful
    sections = [file[start * 4:end * 4] for start, end in zip(header[2:], header[3:])]
    return sections

def print_raw_integers(section: bytes) -> str:
    arr = array('I', section)
    out = ""
    for n in arr:
        if n == 0:
            out += f"  - 0\n"
        else:
            out += f"  - 0x{n:x}\n"
    return out

def read_values_from_section(map_fn: Callable[..., T], section: bytes, start_value: int) -> list[T]:
    arr = array('I', section)
    fn = partial(map_fn, section, arr)
    
    function_offsets = [i for i, value in enumerate(arr) if value == start_value]
    functions = list(map(fn, function_offsets))
    return functions

@dataclass
class FunctionDef:
    name: str
    id: str
    header: list[int]
    other_fields: list[int]

def read_function_def(section: bytes, arr: array[int], offset: int):
    id = arr[offset + 1]
    header = arr[offset + 2:offset + 9]
    
    name_buffer = section[offset * 4 + 0x24:]
    name_bytelen = name_buffer.index(0)
    name = str(name_buffer[:name_bytelen], 'utf-8')
    
    rest = arr[offset + 9 + ceil(name_bytelen / 4):]
    if 0xFFFFFFFF in rest:
        other_fields = rest[:rest.index(0xFFFFFFFF)]
    else:
        other_fields = rest
    
    return FunctionDef(name, id, header, other_fields)

def print_function_def(fn: FunctionDef) -> str:
    out = f"  - name: {fn.name}\n    id: 0x{fn.id:x}\n    header:\n"
    
    for n in fn.header:
        out += f"      - 0x{n:x}\n"
    
    out += "    other_fields:\n"
    for n in fn.other_fields:
        out += f"      - 0x{n:x}\n"
    
    return out

@dataclass
class FunctionImport:
    name: str
    field_0x0: int
    field_0x4: int
    field_0x8: int
    id: int
    field_0x10: int
    field_0x14: int
    field_0x18: int

def read_function_import(section: bytes, arr: array[int], offset: int) -> FunctionImport:
    name_buffer = section[offset * 4 + 0x20:]
    name_bytelen = name_buffer.index(0)
    name = str(name_buffer[:name_bytelen], 'utf-8')
    
    int_fields = iter(arr[offset + 1:])
    return FunctionImport(name, *[next(int_fields) for _ in range(7)])

def print_function_import(fn: FunctionImport) -> str:
    return f"""  - name: {fn.name}
    field_0x0: 0x{fn.field_0x0:x}
    field_0x4: 0x{fn.field_0x4:x}
    field_0x8: 0x{fn.field_0x8:x}
    id: 0x{fn.id:x}
    field_0x10: 0x{fn.field_0x10:x}
    field_0x14: 0x{fn.field_0x14:x}
    field_0x18: 0x{fn.field_0x18:x}\n"""

@dataclass
class Instruction:
    value: int
    label: str

INSTRUCTIONS = {
    0xc: Instruction(0xc, "block_a"),
    0x3d: Instruction(0x3d, "block_b"),
    0x18: Instruction(0x18, "block_c"),
    0x40: Instruction(0x40, "end_block"),
    0x11: Instruction(0x11, "return"),
    0x9: Instruction(0x9, "end"),
}

@dataclass
class FunctionImpl:
    name: str
    extra_args: list[int]
    bytecode: list[int | str | FunctionDef | FunctionImport]

def read_function_impl(symbol_ids, section: bytes, arr: array[int], offset: int) -> FunctionImpl:
    buffer = arr[offset:]
    
    function_id = buffer[1]
    function = symbol_ids[function_id]
    
    if not isinstance(function, FunctionDef):
        raise Exception('Implementation to not defined function')
    
    header_end = buffer.index(8)
    extra_args = buffer[2:header_end]
    
    code = []
    
    for n in buffer[header_end + 1:]:
        if n == 5:
            break
        if n in symbol_ids:
            code.append(symbol_ids[n])
        elif n in INSTRUCTIONS:
            code.append(INSTRUCTIONS[n])
        else:
            code.append(n)
    
    return FunctionImpl(function.name, extra_args, code)

def print_function_impl(fn: FunctionImpl) -> str:
    out = f"  {fn.name}:\n    extra_args: ["
    
    if len(fn.extra_args) > 1:
        for arg in fn.extra_args[:-1]:
            out += f"0x{arg:x}, "
    
    if len(fn.extra_args) > 0:
        out += f"0x{fn.extra_args[-1]:x}"
    
    out += "]\n    body:\n"
    
    for x in fn.bytecode:
        if isinstance(x, FunctionDef):
            out += f"      - call {x.name} # 0x{x.id:x} (local)\n"
        elif isinstance(x, FunctionImport):
            out += f"      - call {x.name} # 0x{x.id:x} (imported)\n"
        elif isinstance(x, Instruction):
            out += f"      - {x.label} # 0x{x.value:x}\n"
        else:
            out += f"      - 0x{x:x}\n"
    
    return out

def main():
    if len(argv) == 1 or argv[1] == '--help' or argv[1] == '-h':
        print("Sticker Star KSM Script Dumper")
        print("Usage: main.py <input file.bin>")
        return
    
    with open(argv[1], 'rb') as f:
        input_file = f.read()
    
    symbol_ids: Dict[int, FunctionDef | FunctionImport] = {}
    
    sections = read_ksm_container(input_file)
    
    out_str = 'section_0:\n'
    out_str += print_raw_integers(sections[0])
    
    function_defs = read_values_from_section(read_function_def, sections[1], 0xFFFFFFFF)
    
    for fn in function_defs:
        symbol_ids[fn.id] = fn
    
    out_str += 'function_defs:\n'
    for fn in function_defs:
        out_str += print_function_def(fn)
    
    function_imports = read_values_from_section(read_function_import, sections[5], 0xFFFFFFFF)
    
    for fn in function_imports:
        symbol_ids[fn.id] = fn
    
    out_str += 'function_imports:\n'
    for fn in function_imports:
        out_str += print_function_import(fn)
    
    # TODO: section 7 start
    
    read_impl = partial(read_function_impl, symbol_ids)
    function_impls = read_values_from_section(read_impl, sections[7], 5)
    
    out_str += 'implementations:\n'
    for fn in function_impls:
        out_str += print_function_impl(fn)
    
    with open(argv[1] + '.yaml', 'w') as f:
        f.write(out_str)

if __name__ ==  '__main__':
    main()
