from array import array
from ctypes import c_int
from dataclasses import dataclass
from enum import Enum
import struct
from sys import argv

from util import SymbolIds

class VarCategory(Enum):
    # script binary scope
    Static = 0
    Const = 1
    Global = 2
    # function local
    TempVar = 3
    LocalVar = 4

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')

@dataclass
class Var:
    name: str | None
    alias: str | None
    category: VarCategory
    
    id: int
    data_type: int
    flags: int
    user_data: int | str

def read_variable(arr: enumerate[int], section: bytes, category: VarCategory) -> Var:
    offset, value = next(arr)
    id = next(arr)[1]
    raw_status = next(arr)[1]
    
    status = raw_status & 0xffffff
    flags = raw_status >> 24
    
    if status == 0:
        user_data = struct.unpack('!f', struct.pack('!I', next(arr)[1]))[0]
    elif status == 1:
        user_data = c_int(next(arr)[1]).value
    else:
        user_data = next(arr)[1]
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 5)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    if status == 3:
        assert user_data == 0
        j, word_len = next(arr)
        
        user_data = read_string(section, j + 1)
        
        for _ in range(word_len):
            next(arr)
    
    return Var(name, None, category, id, status, flags, user_data)

def read_variable_defs(section: bytes, category: VarCategory) -> list[Var]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    variables = []
    
    for _ in range(count):
        variables.append(read_variable(arr, section, category))
    
    assert next(arr, None) == None
    return variables

VAR_TYPE_NAMES = {
    0: 'Float',
    1: 'Int',
    3: 'String',
    4: 'Alloc',
    5: 'UserVar',
    8: 'Func',
    0xd: 'QueuedFree',
    0xe: 'Uninitialized',
}

def print_var(var: Var, indentation_level: int = 1) -> str:
    indent = '  ' * indentation_level
    
    if isinstance(var.user_data, str):
        user_data = repr(var.user_data)
    elif var.data_type in [0, 1] or var.user_data == 0:
        user_data = str(var.user_data)
    else:
        user_data = hex(var.user_data)
    
    if var.data_type in VAR_TYPE_NAMES:
        type = VAR_TYPE_NAMES[var.data_type] + f" # {var.data_type}"
    else:    
        type = var.data_type
    
    # no need to print category as the variables are
    # already grouped by category in output
    result = result = f"{indent}- "
    
    if var.name:
        result += f"name: {var.name}\n{indent}  "
    
    if var.alias is not None:
        result += f"alias: {var.category.name}:{var.alias}\n{indent}  "
    
    result += f"id: 0x{var.id:x}\n"
    
    result += f"{indent}  type: {type}\n"
    
    if var.flags != 0:
        result += f"{indent}  flags: 0x{var.flags:x}\n"
    
    if var.user_data != 0 or var.category == VarCategory.Const:
        result += f"{indent}  content: {user_data}\n"
    
    return result


def write_variables(sections: list[bytes], symbol_ids: SymbolIds):
    # section 2
    variables = read_variable_defs(sections[2], VarCategory.Static)
    
    var_str = 'static_variables:\n'
    prev_status = None
    for var in variables:
        if prev_status != None and var.data_type != prev_status:
            var_str += '  \n'
        
        prev_status = var.data_type
        symbol_ids.add(var)
        var_str += print_var(var)
    
    # section 4
    constants = read_variable_defs(sections[4], VarCategory.Const)
    
    var_str += '\nconstants:\n'
    prev_status = None
    for var in constants:
        if prev_status != None and var.data_type != prev_status:
            var_str += '  \n'
        
        prev_status = var.data_type
        symbol_ids.add(var)
        var_str += print_var(var)
    
    # section 6
    global_variables = read_variable_defs(sections[6], VarCategory.Global)
    
    var_str += '\nglobal_variables:\n'
    prev_status = None
    for var in global_variables:
        if prev_status != None and var.data_type != prev_status:
            var_str += '  \n'
        
        prev_status = var.data_type
        symbol_ids.add(var)
        var_str += print_var(var)
    
    # local variables (defined implicitly)
    for i in range(0x16): # TODO: how many are there?
        var = Var(None, f"{i:X}", VarCategory.TempVar, 0x10000100 | i, 0, 0, 0)
        symbol_ids.add(var)
    
    with open(argv[1] + '.variables.yaml', 'w', encoding='utf-8') as f:
        f.write(var_str)
