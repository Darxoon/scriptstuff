#!/bin/env python3
from array import array
from struct import unpack
from sys import argv
from typing import TypeVar

from functions import print_function_definitions, print_function_imports
from tables import print_tables
from util import SymbolIds
from variables import write_variables

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


def main():
    if len(argv) == 1 or argv[1] == '--help' or argv[1] == '-h':
        print("Sticker Star KSM Script Dumper")
        print("Usage: main.py <input file.bin>")
        return
    
    with open(argv[1], 'rb') as f:
        input_file = f.read()
    
    sections = read_ksm_container(input_file)
    
    symbol_ids = SymbolIds()
    write_variables(sections, symbol_ids)
    
    # output main yaml
    main_out_str = print_section_0(sections)

    main_out_str += print_function_imports(sections, symbol_ids)
    main_out_str += print_tables(sections, symbol_ids)
    main_out_str += print_function_definitions(sections, symbol_ids)
    
    
    with open(argv[1] + '.yaml', 'w') as f:
        f.write(main_out_str)

if __name__ ==  '__main__':
    main()
