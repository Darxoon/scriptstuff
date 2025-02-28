#!/bin/env python3
from array import array
from struct import unpack
from sys import argv
from typing import TypeVar

import yaml

from cmds import cmd_from_string
from functions import parse_function_definitions, print_function_definitions, print_function_imports
from other_types import parse_imports
from tables import print_tables
from util import SymbolIds
from variables import VarCategory, parse_variables, write_variables_yaml

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

def print_section_0(sections: list[bytes]) -> str:
    section = sections[0]
    arr = array('I', section)
    
    assert len(arr) == 3
    assert arr[0] == 0
    assert arr[1] == 0
    
    out_str = 'section_0:\n'
    out_str += f"  - {hex(arr[2])} # mysterious number\n"
    
    return out_str

def ksm_to_yaml(filename: str):
    with open(filename, 'rb') as f:
        input_file = f.read()
    
    sections = read_ksm_container(input_file)
    
    symbol_ids = SymbolIds()
    write_variables_yaml(sections, symbol_ids)
    
    # output main yaml
    main_out_str = print_section_0(sections)

    main_out_str += print_function_imports(sections, symbol_ids)
    main_out_str += print_tables(sections, symbol_ids)
    main_out_str += print_function_definitions(sections, symbol_ids)
    
    with open(argv[1] + '.yaml', 'w') as f:
        f.write(main_out_str)

def write_ksm_container(sections: list[bytearray]) -> bytes:
    section_indices = [2 + len(sections)]
    for section in sections[:-1]:
        assert len(section) % 4 == 0
        section_indices.append(section_indices[-1] + len(section) // 4)
    
    out_arr = array('I', b'KSMR\0\x03\x01\0')
    out_arr.extend(section_indices)
    
    out = bytearray(out_arr)
    for section in sections:
        out.extend(section)
    
    return bytes(out)

def parse_section_0(input_file: dict) -> bytearray:
    section_0 = input_file['section_0']
    assert isinstance(section_0, list), "Section 0 has invalid"
    assert len(section_0) == 1, "Section 0 has invalid"
    assert isinstance(section_0[0], int), "Section 0 has invalid"
    
    out_arr = array('I', [0, 0, section_0[0]])
    return bytearray(out_arr)

def yaml_to_ksm(filename: str):
    # main input file
    with open(filename, 'r') as f:
        input_file = yaml.safe_load(f)
    
    assert isinstance(input_file, dict) and 'section_0' in input_file, "Input yaml file has to be a dictionary \
        containing the properties 'section_0' and optionally 'tables' and 'definitions'."
    
    # var input file
    var_filename = filename[:-len('.yaml')] + '.variables.yaml'
    
    with open(var_filename, 'r') as f:
        var_input_file = yaml.safe_load(f)
    
    assert isinstance(var_input_file, dict), "Input variables yaml file has to be a dict."
    
    sections: dict[int, bytearray] = {}
    symbol_ids = SymbolIds()
    
    # section 0
    sections[0] = parse_section_0(input_file)
    funcs, sections[1] = parse_function_definitions(input_file, symbol_ids)
    sections[2] = parse_variables(var_input_file, 'static_variables', VarCategory.Static, symbol_ids)
    # TODO: tables
    sections[4] = parse_variables(var_input_file, 'constants', VarCategory.Const, symbol_ids)
    sections[5] = parse_imports(input_file, symbol_ids)
    sections[6] = parse_variables(var_input_file, 'global_variables', VarCategory.Global, symbol_ids)
    
    for fn in funcs:
        assert fn.instruction_strs is not None
        fn.instructions = [cmd_from_string(line, fn, symbol_ids) for line in fn.instruction_strs]
    
    # sections[7] = ...
    
    section_list = [sections.get(i, bytearray([0, 0, 0, 0])) for i in range(9)]
    
    if filename.endswith('.bin.yaml'):
        out_filename = filename[:-len('.bin.yaml')] + '_modified.bin'
    else:
        out_filename = filename + '.bin'
    
    with open(out_filename, 'wb') as f:
        f.write(write_ksm_container(section_list))

def main():
    if len(argv) == 1 or argv[1] == '--help' or argv[1] == '-h':
        print("Sticker Star KSM Script Dumper")
        print("Usage: main.py <input file.bin | input file.yaml>")
        return
    
    filename = argv[1]
    
    if filename.endswith('.bin'):
        ksm_to_yaml(filename)
    elif filename.endswith('.yaml'):
        yaml_to_ksm(filename)

if __name__ ==  '__main__':
    main()
