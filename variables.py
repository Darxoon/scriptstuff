from array import array
from ctypes import c_int
from dataclasses import dataclass
from enum import Enum
import struct
from sys import argv
from types import NoneType
from typing import Any

from util import SymbolIds, read_string, write_string

class VarCategory(Enum):
    # script binary scope
    Static = 0
    Const = 1
    Global = 2
    # function local
    TempVar = 3
    OuterTempVar = 4 # used for captured temp vars
    ClearTempVar = 5
    LocalVar = 6

# TODO: make this an enum as well
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
        # bitwise convert int to float
        user_data = struct.unpack('!f', struct.pack('!I', next(arr)[1]))[0]
    elif status == 1:
        # convert u32 to s32
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

def write_variable(var: Var) -> array[int]:
    out = array('I')
    
    out.append(0xFFFFFFFF if var.name is not None else 0)
    out.append(var.id)
    out.append(var.data_type | var.flags << 24)
    
    if var.data_type == 0:
        # float
        out.append(struct.unpack('!I', struct.pack('!f', var.user_data))[0])
    elif var.data_type == 3:
        # string
        out.append(0)
    else:
        out.append(int(var.user_data))
    
    if var.name is not None:
        out.extend(write_string(var.name))
    
    if var.data_type == 3:
        assert isinstance(var.user_data, (str, NoneType)), "A variable of type string's content has to be a string"
        out.extend(write_string(var.user_data if var.user_data is not None else ""))
    
    return out

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

def var_from_yaml(var: Any, category: VarCategory) -> Var:
    assert isinstance(var, dict), "Variable has to be an object"
    
    if 'name' in var and var['name'] is not None:
        assert isinstance(var['name'], str), "Variable name has to be a string"
        name = var['name']
    else:
        name = None
    
    if 'alias' in var and var['alias'] is not None:
        assert isinstance(var['alias'], str), "Variable alias has to be a string"
        alias = var['alias']
        
        assert alias.startswith(category.name + ':'), f"Variable has to be a {category.name}, not {alias}"
        alias = alias[len(category.name) + 1:]
    else:
        alias = None
    
    assert 'id' in var and isinstance(var['id'], int), "Variable's id (required) has to be an integer"
    id = var['id']
    
    assert 'type' in var and isinstance(var['type'], (str, int)), "Variable's type (required) has to be a string or integer"
    data_type = var['type']
    
    if 'flags' in var and var['flags'] is not None:
        assert isinstance(var['flags'], int), "Variable flags has to be an integer"
        flags = var['flags']
    else:
        flags = 0
    
    if 'content' in var and var['content'] is not None:
        # assert isinstance(var['content'], int), "Variable content has to be an integer"
        content = var['content']
    else:
        content = 0
    
    if isinstance(data_type, str):
        try:
            data_type = next(i for i, name in VAR_TYPE_NAMES.items() if name == data_type)
        except StopIteration:
            raise ValueError("Variable's type (required) has to be one of the following values: "
                             + ','.join(VAR_TYPE_NAMES.values()))
    
    return Var(name, alias, category, id, data_type, flags, content)

def write_variables_yaml(sections: list[bytes], symbol_ids: SymbolIds):
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
    
    # temporary variables (defined implicitly)
    for i in range(20):
        var = Var(None, f"{i:X}", VarCategory.TempVar, 0x10000100 | i, 0, 0, 0)
        symbol_ids.add(var)

    for i in range(20):
        # these temp vars are the same as regular but cleared to 0 whenever they are accessed
        # good for passing previously uninitialized variables as out vars to a function
        var = Var(None, f"{i:X}", VarCategory.ClearTempVar, 0x10000400 | i, 0, 0, 0)
        symbol_ids.add(var)
    
    with open(argv[1] + '.variables.yaml', 'w', encoding='utf-8') as f:
        f.write(var_str)

def parse_variables(var_input_file: dict, category_key: str, category: VarCategory, symbol_ids: SymbolIds) -> bytearray:
    if category_key in var_input_file and var_input_file[category_key] is not None:
        assert isinstance(var_input_file[category_key], list), f"{category.name} variables have to be a list"
        
        vars_obj = var_input_file[category_key]
        vars = [var_from_yaml(var_obj, category) for var_obj in vars_obj]
        
        out = array('I')
        out.append(len(vars))
        
        for var in vars:
            symbol_ids.add(var)
            out.extend(write_variable(var))
        
        return bytearray(out)
    else:
        return bytearray([0, 0, 0, 0])