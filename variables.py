from array import array
from dataclasses import dataclass
from enum import Enum
from sys import argv

class VarCategory(Enum):
    # script binary scope
    Var1 = 0
    Const = 1
    Global = 2
    # function local
    Func = 3

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')

@dataclass
class Var:
    name: str | None
    category: VarCategory
    
    id: int
    status: int
    flags: int
    user_data: int | str

def read_variable(arr: enumerate[int], section: bytes, category: VarCategory) -> Var:
    offset, value = next(arr)
    id = next(arr)[1]
    raw_status = next(arr)[1]
    user_data = next(arr)[1]
    
    status = raw_status & 0xffffff
    flags = raw_status >> 24
    
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
    
    return Var(name, category, id, status, flags, user_data)

def read_variable_defs(section: bytes, category: VarCategory) -> list[Var]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    variables = []
    
    for _ in range(count):
        variables.append(read_variable(arr, section, category))
    
    assert next(arr, None) == None
    return variables

VAR_STATUS_NAMES = {
    4: 'Alloc',
    5: 'UserVar',
    0xd: 'QueuedFree',
    0xe: 'Uninitialized',
}

def print_var(var: Var, indentation_level: int = 1) -> str:
    indent = '  ' * indentation_level
    
    if isinstance(var.user_data, str):
        user_data = repr(var.user_data)
    elif var.user_data != 0:
        user_data = f"0x{var.user_data:x}"
    else:
        user_data = var.user_data
    
    if (var.status) in VAR_STATUS_NAMES:
        status = VAR_STATUS_NAMES[var.status] + f" # {var.status}"
    else:    
        status = var.status
    
    # no need to print category as the variables are
    # already grouped by category in output
    if var.name:
        result = f"""{indent}- name: {var.name}
{indent}  id: 0x{var.id:x}
{indent}  status: {status}\n"""
    else:
        result = f"""{indent}- id: 0x{var.id:x}
{indent}  status: {status}\n"""
    
    if var.flags != 0:
        result += f"{indent}  flags: 0x{var.flags:x}\n"
    if var.user_data != 0:
        result += f"{indent}  content: {user_data}\n"
    
    return result


def write_variables(sections: list[bytes], symbol_ids: dict):
    # section 2
    variables = read_variable_defs(sections[2], VarCategory.Var1)
    
    var_str = 'variables:\n'
    prev_status = None
    for var in variables:
        if prev_status != None and var.status != prev_status:
            var_str += '  \n'
        
        prev_status = var.status
        symbol_ids[var.id] = var
        var_str += print_var(var)
    
    # section 4
    constants = read_variable_defs(sections[4], VarCategory.Const)
    
    var_str += '\nconstants:\n'
    prev_status = None
    for var in constants:
        if prev_status != None and var.status != prev_status:
            var_str += '  \n'
        
        prev_status = var.status
        symbol_ids[var.id] = var
        var_str += print_var(var)
    
    # section 6
    global_variables = read_variable_defs(sections[6], VarCategory.Global)
    
    var_str += '\nglobal_variables:\n'
    prev_status = None
    for var in global_variables:
        if prev_status != None and var.status != prev_status:
            var_str += '  \n'
        
        prev_status = var.status
        symbol_ids[var.id] = var
        var_str += print_var(var)
    
    with open(argv[1] + '.variables.yaml', 'w') as f:
        f.write(var_str)
