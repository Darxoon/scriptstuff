#!/bin/env python3
from array import array
from dataclasses import dataclass
from functools import partial
from math import ceil
from struct import unpack
from sys import argv
from typing import Callable, TypeVar

from functions import FunctionImport, write_functions
from variables import Var, write_variables

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

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')

@dataclass
class FunctionDef:
    name: str
    id: str
    header: list[int]
    other_fields: list[int]

def read_function_def(section: bytes, arr: array[int], offset: int):
    id = arr[offset + 1]
    header = arr[offset + 2:offset + 9]
    
    # this is stupid
    name_buffer = section[offset * 4 + 0x24:]
    name_bytelen = name_buffer.index(0)
    
    name = read_string(section, offset + 9)
    
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
class Instruction:
    value: int
    label: str
    empty_line_after: bool

INSTRUCTIONS = {
    # 0xc: Instruction(0xc, "block_a"),
    # 0x3d: Instruction(0x3d, "block_b"),
    # 0x18: Instruction(0x18, "block_c"),
    # 0x40: Instruction(0x40, "end_block"),
    0x11: Instruction(0x11, "return", True),
    0x9: Instruction(0x9, "end", False),
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
        elif isinstance(x, Var):
            out += f"      - push {x.id}\n"
        elif isinstance(x, Instruction):
            out += f"      - {x.label} # 0x{x.value:x}\n"
            if x.empty_line_after:
                out += "      \n"
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
    
    symbol_ids = {}
    sections = read_ksm_container(input_file)
    
    write_variables(sections, symbol_ids)
    write_functions(sections, symbol_ids)
    
    # section 0 (mysterious)
    out_str = 'section_0:\n'
    out_str += print_raw_integers(sections[0])
    
    # section 1 (function definitions)
    function_defs = read_values_from_section(read_function_def, sections[1], 0xFFFFFFFF)
    
    for fn in function_defs:
        symbol_ids[fn.id] = fn
    
    out_str += 'function_defs:\n'
    for fn in function_defs:
        out_str += print_function_def(fn)
    
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
