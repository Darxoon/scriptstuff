from array import array
from dataclasses import dataclass
from sys import argv

from tables import Table, print_table, read_table
from variables import Var, VarCategory, print_var, read_variable

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')


# function imports
@dataclass
class FunctionImport:
    name: str | None
    field_0x4: int # short
    field_0x8: int
    id: int

def read_function_imports(section: bytes) -> list[FunctionImport]:
    arr = enumerate(array('I', section))
    
    count = next(arr)[1]
    imports = []
    
    for i, value in arr:
        field_0x4 = next(arr)[1] & 0xFFFF
        field_0x8 = next(arr)[1]
        next(arr) # unused
        
        id = next(arr)[1]
        next(arr) # unused
        next(arr) # unused
        
        if value == 0xFFFFFFFF:
            name = read_string(section, i + 8)
            
            for _ in range(next(arr)[1]):
                next(arr)
        else:
            assert value == 0
            name = None
        
        imports.append(FunctionImport(name, field_0x4, field_0x8, id))
    
    assert len(imports) == count
    return imports

def print_function_import(fn: FunctionImport) -> str:
    assert fn.name is not None, "Imported function name is None"
    
    return f"  - {{ id: 0x{fn.id:x}, name: '{fn.name}', field_0x4: {fn.field_0x4}, field_0x8: {fn.field_0x8} }}\n"


# labels
@dataclass
class Label:
    name: str | None
    id: int
    code_offset: int

def read_label(arr: enumerate[int], section: bytes):
    offset, value = next(arr)
    id = next(arr)[1]
    code_offset = next(arr)[1]
    
    if value == 0xFFFFFFFF:
        name = read_string(section, offset + 6)
        
        for _ in range(next(arr)[1]):
            next(arr)
    else:
        assert value == 0
        name = None
    
    return Label(name, id, code_offset)

def print_label(label: Label) -> str:
    return f"""      - name: {label.name if label.name != None else 'null'}
        id: 0x{label.id:x}
        code_offset: 0x{label.code_offset:x}\n"""


# script expressions
@dataclass
class Expr:
    elements: list['Var | CallCmd | int']

def read_expr(initial_element: int | None, arr: enumerate[int], symbol_ids: dict, raise_on_ending_sequence = False) -> Expr:
    elements = []
    
    if initial_element is not None:
        elements.append(symbol_ids.get(initial_element, initial_element))
    
    for _, value in arr:
        if value == 0x40:
            break
        
        if value == 0xc:
            elements.append(read_call_cmd(arr, symbol_ids, 0xc, False))
            continue
        
        var = symbol_ids.get(value, value)
        elements.append(var)
    
    return Expr(elements)

def print_expr_or_var(value, braces_around_expression = False) -> str:
    match value:
        case Expr(elements):
            content = ' '.join(print_expr_or_var(x, True) for x in elements)
            if braces_around_expression:
                return f'( {content} )'
            else:
                return content
        case Var(name, alias, category, id, status, flags, user_data):
            if name is not None:
                return f"{category.name}:{name}"
            elif alias is not None:
                return f"{category.name}:{alias}"
            elif category == VarCategory.Const and user_data is not None:
                return f"{user_data}`" if isinstance(user_data, int) else repr(user_data)
            else:
                return f"{category.name}:0x{id:x}"
        case FunctionImport(name) | FunctionDef(name):
            return f"fn:{name}"
        case Label(name, id):
            if name is not None:
                return f"label:{name}"
            else:
                return f"label:{hex(id)}"
        case Table(name, id):
            if name is not None:
                return f"table:{name}"
            else:
                return f"table:{hex(id)}"
        case CallCmd(is_const, func, args):
            content = f"Call{'*' if is_const else ''} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
            if braces_around_expression:
                return f'( {content} )'
            else:
                return content
        case int(n):
            return f"?0x{n:x}"
        case str(n):
            return n
        case _:
            raise Exception(f"Unknown thing {repr(value)}")

# script instructions
@dataclass
class ReturnValCmd:
    is_const: bool
    value: Expr | Var | int

def read_returnval_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> ReturnValCmd:
    value_int = next(arr)[1]
    if is_const:
        value = symbol_ids.get(value_int, value_int)
        assert isinstance(value, Var) or isinstance(value, int)
        if value == 0x40:
            value = Expr([])
    else:
        value = read_expr(value_int, arr, symbol_ids)
    
    return ReturnValCmd(is_const, value)

@dataclass 
class CallCmd:
    is_const: bool
    func: 'FunctionImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CallCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if is_const:
            var = symbol_ids.get(value, value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallCmd(is_const, func, args)

@dataclass
class CallThreadedCmd:
    is_const: bool
    func: 'FunctionImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_threaded_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CallCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if is_const:
            var = symbol_ids.get(value, value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallThreadedCmd(is_const, func, args)

#???
@dataclass
class CallThreaded2Cmd:
    is_const: bool
    func: 'FunctionImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_threaded2_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CallCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if is_const:
            var = symbol_ids.get(value, value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallThreaded2Cmd(is_const, func, args)

@dataclass 
class CallVarCmd:
    is_const: bool
    func: Var | int
    args: list[Expr | Var | int]

def read_call_var_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CallVarCmd:
    func_int = next(arr)[1]
    func = symbol_ids[func_int, func_int]
    assert isinstance(func, Var) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if is_const:
            var = symbol_ids.get(value, value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallVarCmd(is_const, func, args)

@dataclass
class SetCmd:
    is_const: bool
    destination: Var | int
    value: Expr | Var | int

def read_set_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> SetCmd:
    destination_int = next(arr)[1]
    destination = symbol_ids.get(destination_int, destination_int)
    assert isinstance(destination, Var) or isinstance(destination, int)
    
    if is_const:
        value_int = next(arr)[1]
        value = symbol_ids.get(value_int, value_int)
        assert isinstance(value, Var) or isinstance(value, int)
        if value == 0x40:
            value = Expr([])
    else:
        value = read_expr(None, arr, symbol_ids)
    
    return SetCmd(is_const, destination, value)

@dataclass
class ReadTableLengthCmd:
    is_const: bool
    arrayt: Table

def read_read_table_length_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> ReadTableLengthCmd:
    assert not is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int, arrayt_int)
    
    return ReadTableLengthCmd(is_const, arrayt)

# returns the value to FuncVar0 by default (but other variables can be set to whatever it returns directly)
@dataclass
class ReadTableEntryCmd:
    is_const: bool
    arrayt: Table
    index: Expr | Var | int

def read_read_table_entry_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> ReadTableEntryCmd:
    assert not is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int, arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int, index_int)
    
    return ReadTableEntryCmd(is_const, arrayt, index)

# this is just like ReadTableEntryCmd, 
# but the variable that the value returned to is specified in the parameters of this instruction
# instead of being determined by a SetCmd directly before it
# so ReadTableEntryToVarCmd and ReadTableEntryCmd are used interchangably
@dataclass
class ReadTableEntryToVarCmd:
    is_const: bool
    arrayt: Table
    index: Expr | Var | int
    var: Var

def read_read_table_entry_to_var_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> SetCmd:
    assert not is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int, arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int, index_int)    
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int, var_int)
    assert isinstance(var, Var)
    
    return ReadTableEntryToVarCmd(is_const, arrayt, index, var)

# read 3 entries starting from the specified index and save those values to 3 specified variables. 
# Used to read 3d vector values without having to call ReadTableEntryCmds 3 times.
@dataclass
class ReadTableEntriesVec3Cmd:
    is_const: bool
    arrayt: Table
    index: Expr | Var | int
    x: Var
    y: Var
    z: Var

def read_read_table_entries_vec3_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> SetCmd:
    assert not is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int, arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int, index_int)    
    
    x_int = next(arr)[1]
    x = symbol_ids.get(x_int, x_int)
    y_int = next(arr)[1]
    y = symbol_ids.get(y_int, y_int)
    z_int = next(arr)[1]
    z = symbol_ids.get(z_int,z_int)
    
    assert isinstance(x, Var)
    assert isinstance(y, Var)
    assert isinstance(z, Var)
    
    return ReadTableEntriesVec3Cmd(is_const, arrayt, index, x, y, z)

@dataclass
class TableGetIndexCmd:
    is_const: bool
    arrayt: Table
    occurance: Expr | Var | int
    var: Var

def read_table_get_index_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> TableGetIndexCmd:
    assert not is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int, arrayt_int)
    occurance_int = next(arr)[1]
    occurance = symbol_ids.get(occurance_int, occurance_int)    
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int, var_int)
    assert isinstance(var, Var)
    
    return TableGetIndexCmd(is_const, arrayt, occurance, var)

@dataclass
class ReturnCmd:
    pass

def read_pop_func_stack_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> ReturnCmd:
    assert not is_const
    
    return ReturnCmd()

@dataclass
class GetArgsCmd:
    func: 'FunctionDef'
    args: list[Var | int]

def read_get_args_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> GetArgsCmd:
    assert not is_const
    
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionDef)
    
    args = []
    for _, value in arr:
        if value == 0x8:
            break
        
        var = symbol_ids.get(value, value)
        assert isinstance(var, Var) or isinstance(var, int)
        args.append(var)
        
    return GetArgsCmd(func, args)

# ??
@dataclass
class IfCmd:
    condition: Expr
    unused1: int
    jump_to: int
    unused2: int

def read_if_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> IfCmd:
    assert not is_const
    
    condition = read_expr(None, arr, symbol_ids)
    unused1 = next(arr)[1]
    jump_to = next(arr)[1]
    unused2 = next(arr)[1]
    
    return IfCmd(condition, unused1, jump_to, unused2)

# these appear in Script/Map/MAC/mac_1_30.bin
# TODO: Find other use cases to confirm whether these are what they appear to be.
@dataclass
class IfEqualCmd:
    var1: Expr | Var | int
    var2: Expr | Var | int
    jump_to: int

def read_ifequal_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> IfEqualCmd:
    assert not is_const
    
    var1_int = next(arr)[1]
    var1 = symbol_ids.get(var1_int, var1_int)
    var2_int = next(arr)[1]
    var2 = symbol_ids.get(var2_int, var2_int)
    jump_to = next(arr)[1]
    
    return IfEqualCmd(var1, var2, jump_to)

@dataclass
class IfNotEqualCmd:
    var1: Expr | Var | int
    var2: Expr | Var | int
    jump_to: int

def read_ifnotequal_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> IfNotEqualCmd:
    assert not is_const
    
    var1_int = next(arr)[1]
    var1 = symbol_ids.get(var1_int, var1_int)
    var2_int = next(arr)[1]
    var2 = symbol_ids.get(var2_int, var2_int)
    jump_to = next(arr)[1]
    
    return IfNotEqualCmd(var1, var2, jump_to)

@dataclass
class ElseIfCmd:
    start_from: int
    unused1: int
    condition: Expr
    unused2: int
    jump_to: int
    unused3: int

def read_else_if_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> IfCmd:
    assert not is_const
    
    start_from = next(arr)[1]
    unused1 = next(arr)[1]
    condition = read_expr(None, arr, symbol_ids)
    unused2 = next(arr)[1]
    jump_to = next(arr)[1]
    unused3 = next(arr)[1]
    
    return ElseIfCmd(start_from, unused1, condition, unused2, jump_to, unused3)

@dataclass
class ElseCmd:
    jump_to: int

def read_else_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> IfCmd:
    assert not is_const
    
    jump_to = next(arr)[1]
    
    return ElseCmd(jump_to)

@dataclass
class GotoLabelCmd:
    label: Label | int

def read_goto_label_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> GotoLabelCmd:
    assert not is_const
    
    label_int = next(arr)[1]
    label = symbol_ids.get(label_int, label_int)
    assert isinstance(label, Label) or isinstance(label, int)
    
    return GotoLabelCmd(label)

@dataclass
class NoopCmd:
    opcode: int

def read_noop_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> NoopCmd:
    assert not is_const
    
    return NoopCmd(opcode)

@dataclass
class LabelCmd:
    opcode: int

def read_label_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> LabelCmd:
    assert not is_const
    
    return LabelCmd(opcode)

# TODO: Find out if the endif and endswitch commands are strictly necessary for the code to run.
@dataclass
class EndIfCmd:
    opcode: int

def read_endif_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> EndIfCmd:
    assert not is_const
    
    return EndIfCmd(opcode)

@dataclass
class ThreadCmd:
    func: 'FunctionDef | FunctionImport | int'
    take_args: list[Var | int]
    give_args: list[Var | int]

def read_thread_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> ThreadCmd:
    assert not is_const
    
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionDef)
    
    take_args = []
    for _, value in arr:
        if value == 0x8:
            break
        
        var = symbol_ids.get(value, value)
        assert isinstance(var, Var) or isinstance(var, int)
        take_args.append(var)
        
    give_args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        var = symbol_ids.get(value, value)
        give_args.append(var)
        
    return ThreadCmd(func, take_args, give_args)

@dataclass
class Thread2Cmd:
    func: 'FunctionDef | FunctionImport | int'
    take_args: list[Var | int]
    give_args: list[Var | int]

def read_thread2_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> Thread2Cmd:
    assert not is_const
    
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int, func_int)
    assert isinstance(func, FunctionDef)
    
    take_args = []
    for _, value in arr:
        if value == 0x8:
            break
        
        var = symbol_ids.get(value, value)
        assert isinstance(var, Var) or isinstance(var, int)
        take_args.append(var)
        
    give_args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        var = symbol_ids.get(value, value)
        give_args.append(var)
        
    return Thread2Cmd(func, take_args, give_args)

# Really stumped on this one. It just takes one value. I've just added this definition because it can otherwise really mess up the formatting
# It doesn't return a value either, so it might change the value in place
@dataclass
class CheckValCmd:
    is_const: bool
    var: Expr | Var | int

def read_checkval_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CheckValCmd:
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int, var_int)
    if is_const:
        assert isinstance(var, Var) or isinstance(var, int)
    
    return CheckValCmd(is_const, var)

@dataclass
class WaitCmd:
    is_const: bool
    duration: Expr | Var | int

def read_wait_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> WaitCmd:
    if is_const:
        duration_int = next(arr)[1]
        duration = symbol_ids.get(duration_int, duration_int)
        assert isinstance(duration, Var) or isinstance(duration, int)
    else:
        duration = read_expr(None, arr, symbol_ids)
    
    return WaitCmd(is_const, duration)


# I'm not sure how this differs from the normal wait command. This needs further looking into (maybe it waits using a different unit of time?)
@dataclass
class Wait2Cmd:
    is_const: bool
    duration: Expr | Var | int

def read_wait2_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> Wait2Cmd:
    if is_const:
        duration_int = next(arr)[1]
        duration = symbol_ids.get(duration_int, duration_int)
        assert isinstance(duration, Var) or isinstance(duration, int)
    else:
        duration = read_expr(None, arr, symbol_ids)
    
    return Wait2Cmd(is_const, duration)

@dataclass
class SwitchCmd:
    var: Var | int
    unused: int
    jump_offset: int

def read_switch_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> SwitchCmd:
    assert not is_const

    var_int = next(arr)[1]
    var = symbol_ids.get(var_int, var_int)
    assert isinstance(var, Var) or isinstance(var, int)
    
    unused = next(arr)[1]
    jump_offset = next(arr)[1]
    
    return SwitchCmd(var, unused, jump_offset)

@dataclass
class CaseCmd:
    is_const: bool
    value: Expr | Var | int
    jump_offset: int

def read_case_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CaseCmd:
    
    value_int = next(arr)[1]
    if is_const:
        value = symbol_ids.get(value_int, value_int)
        assert isinstance(value, Var) or isinstance(value, int)
    else:
        value = symbol_ids.get(value_int, value_int)
    
    jump_offset = next(arr)[1]
    
    return CaseCmd(is_const, value, jump_offset)

# A variant of the switch instruction that seems to also take two floating point values...
# It being a check as to whether the match value is within this range is just a guess.
@dataclass
class CaseRangeCmd:
    is_const: bool
    lower: Expr | Var | int
    upper: Expr | Var | int
    jump_offset: int

def read_case_range_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> CaseRangeCmd:
    
    lower_int = next(arr)[1]
    if is_const:
        lower = symbol_ids.get(lower_int, lower_int)
        assert isinstance(lower, Var) or isinstance(lower, int)
    else:
        lower = symbol_ids.get(lower_int, lower_int)
        
    upper_int = next(arr)[1]
    if is_const:
        upper = symbol_ids.get(upper_int, upper_int)
        assert isinstance(upper, Var) or isinstance(upper, int)
    else:
        upper = symbol_ids.get(upper_int, upper_int)
    
    jump_offset = next(arr)[1]
    
    return CaseRangeCmd(is_const, lower, upper, jump_offset)

@dataclass
class BreakSwitchCmd:
    opcode: int

def read_breakswitch_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> BreakSwitchCmd:
    assert not is_const
    
    return BreakSwitchCmd(opcode)

@dataclass
class EndSwitchCmd:
    opcode: int

def read_endswitch_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> EndSwitchCmd:
    assert not is_const
    
    return EndSwitchCmd(opcode)

@dataclass
class DoWhileCmd:
    is_const: bool
    value: Expr | Var | int
    jump_offset: int

def read_dowhile_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> DoWhileCmd:
    
    if is_const:
        value_int = next(arr)[1]
        value = symbol_ids.get(value_int, value_int)
        assert isinstance(value, Var) or isinstance(value, int)
    else:
        value = read_expr(None, arr, symbol_ids)
    
    jump_offset = next(arr)[1]
    
    return DoWhileCmd(is_const, value, jump_offset)

@dataclass
class BreakCmd:
    opcode: int

def read_break_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> BreakCmd:
    assert not is_const
    
    return BreakCmd(opcode)

@dataclass
class EndDoWhileCmd:
    opcode: int

def read_enddowhile_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> EndDoWhileCmd:
    assert not is_const
    
    return EndDoWhileCmd(opcode)


# more known commands: Switch, DoWhile, Read[n], Write

@dataclass
class UnknownCmd:
    opcode: int
    is_const: bool
    args: list[Expr | Var | int]

def read_unknown_cmd(arr: enumerate[int], symbol_ids: dict, opcode: int, is_const: bool) -> UnknownCmd:
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        var = symbol_ids.get(value, value)
        args.append(var)
    
    return UnknownCmd(opcode, is_const, args)

INSTRUCTIONS = {
    # TODO: some of the noops return 1, some 3, might be worth looking into
    0x2: read_noop_cmd,
    0x3: read_returnval_cmd,
    0x4: read_label_cmd,
    0x5: read_get_args_cmd,
    0x6: read_thread_cmd,
    0x7: read_thread2_cmd,
    0x9: read_pop_func_stack_cmd,
    0xa: read_goto_label_cmd,
    0xc: read_call_cmd,
    0xd: read_call_threaded_cmd,
    #TODO: Figure out what this could be, it's definitely similar to CallThreaded but how it's different isn't clear
    #0xe: read_call_threaded2_cmd,
    0x12: read_checkval_cmd,
    0x16: read_wait_cmd,
    0x17: read_wait2_cmd,
    0x18: read_if_cmd,
    
    # Unusual If Instructions (experimental)
    #0x19: read_ifequal_cmd,
    #0x1d: read_ifnotequal_cmd,
    
    # Switch, Case Instructions
    0x26: read_else_cmd,
    0x27: read_else_if_cmd,
    0x28: read_endif_cmd,
    0x29: read_switch_cmd,
    0x2a: read_case_cmd,
    0x30: read_case_range_cmd,
    0x37: read_breakswitch_cmd,
    0x38: read_endswitch_cmd,
    
    # DoWhile Instructions
    0x39: read_dowhile_cmd,
    0x3a: read_break_cmd,
    0x3c: read_enddowhile_cmd,
    
    0x3d: read_set_cmd,
    
    # Array Instructions 
    0x67: read_read_table_length_cmd,
    0x68: read_read_table_entry_cmd,
    0x69: read_read_table_entry_to_var_cmd,
    0x6b: read_read_table_entries_vec3_cmd,
    0x6d: read_table_get_index_cmd,
    
    # TODO: are these noops?
    0x7c: read_noop_cmd,
    0x7d: read_noop_cmd,
    
    0x80: read_call_var_cmd,
    # 0x29: read_switch,
}


# function definitions
@dataclass
class FunctionDef:
    name: str | None
    id: int
    is_public: int
    field_0xc: int
    field_0x30: int # some variable's handle?
    field_0x34: int
    
    code: array
    instructions: list | None
    
    vars: list
    tables: list
    unk: list
    
    # analysis
    thread_references: list['FunctionDef'] # TODO: do this for Thread2 too

def read_function_definitions(section: bytes, code_section: bytes, symbol_ids: dict) -> list[FunctionDef]:
    arr = enumerate(array('I', section))
    code_section_arr = array('I', code_section)
    
    count = next(arr)[1]
    definitions = []
    
    for i, value in arr:
        id = next(arr)[1]
        is_public = next(arr)[1]
        field_0xc = next(arr)[1]
        code_offset = next(arr)[1]
        code_end = next(arr)[1]
        field_0x30 = next(arr)[1]
        field_0x34 = next(arr)[1]
        
        code = code_section_arr[code_offset + 1:code_end + 1]
        
        if value == 0xFFFFFFFF:
            name = read_string(section, i + 9)
            
            for _ in range(next(arr)[1]):
                next(arr)
        else:
            assert value == 0
            name = None
        
        variables = []
        for i in range(next(arr)[1]):
            var = read_variable(arr, section, VarCategory.FuncVar)
            
            if var.name == None:
                assert (var.id & 0xFF) == 0
                var.alias = str((var.id >> 8) & 0xFF) # TODO: make this more exact
            
            variables.append(var)
            
        tables = []
        for _ in range(next(arr)[1]):
            tables.append(read_table(arr, section))
        
        labels = []
        for _ in range(next(arr)[1]):
            labels.append(read_label(arr, section))
        
        definitions.append(FunctionDef(name, id, is_public, field_0xc, field_0x30, field_0x34, code, None, variables, tables, labels, []))
    
    assert len(definitions) == count
    return definitions

def analyze_function_def(fn: FunctionDef, symbol_ids: dict):
    arr = enumerate(fn.code)
    instructions = []
    
    for _, value in arr:
        try:
            if value & 0xfffffeff in INSTRUCTIONS:
                instruction = INSTRUCTIONS[value & 0xfffffeff](arr, symbol_ids, value & 0xfffffeff, value & 0x100 != 0)
                
                match instruction:
                    case ThreadCmd(func):
                        if isinstance(func, FunctionDef) and func is not fn:
                            func.thread_references.append(fn)
                
                instructions.append(instruction)
            else:
                instructions.append(read_unknown_cmd(arr, symbol_ids, value & 0xfffffeff, value & 0x100 != 0))
        except StopIteration:
            pass
    
    fn.instructions = instructions

def print_function_def(fn: FunctionDef) -> str:
    result = f"""  - name: {fn.name if fn.name != None else 'null'}
    id: 0x{fn.id:x}
    is_public: {fn.is_public}
    field_0xc: 0x{fn.field_0xc:x}
    field_0x30: 0x{fn.field_0x30:x}
    field_0x34: 0x{fn.field_0x34:x}\n"""
    
    if fn.vars and len(fn.vars) > 0:
        result += "    \n    variables:\n"
        for var in fn.vars:
            result += print_var(var, 3)
    if fn.tables and len(fn.tables) > 0:
        result += "    \n    tables:\n"
        for table in fn.tables:
            result += print_table(table, 3)
    if fn.unk and len(fn.unk) > 0:
        result += "    \n    labels:\n"
        for var in fn.unk:
            result += print_label(var)
    
    if len(fn.thread_references) == 1:
        result += f"    \n    generated_from_thread: true # used by fn:{fn.thread_references[0].name}\n"
    elif fn.instructions and len(fn.instructions) > 0:
        result += "    \n    body:\n"
        start_indented_block = False
        indentation = 0
        
        for inst in fn.instructions:
            if start_indented_block:
                start_indented_block = False
                indentation += 1
            
            match inst:
                case ReturnValCmd(is_const, var):
                    value = f"ReturnVal{'*' if is_const else ' '} ( {print_expr_or_var(var)} )"
                case SetCmd(is_const, destination, source):
                    value = f"Set{'*' if is_const else ' '} {print_expr_or_var(destination)} {print_expr_or_var(source, True)}"
                case CallCmd(is_const, func, args):
                    value = f"Call{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallThreadedCmd(is_const, func, args):
                    value = f"CallAsThread{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallThreaded2Cmd(is_const, func, args):
                    value = f"CallAsThread2{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallVarCmd(is_const, func, args):
                    value = f"CallVar{'*' if is_const else '' } {func if isinstance(func, int) else func.name} {args}"
                case ReturnCmd():
                    if indentation > 0:
                        indentation -= 1
                    
                    value = f"Return"
                case GetArgsCmd(func, args):
                    value = f"GetArgs self:{func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case IfCmd(condition, unused1, jump_to, unused2):
                    start_indented_block = True
                    value = f"If ( {print_expr_or_var(condition)}, {hex(unused1)}, {hex(jump_to)}, {hex(unused2)} )"
                case IfEqualCmd(var1, var2, jump_to):
                    start_indented_block = True
                    value = f"IfEqual ( {print_expr_or_var(var1)}, {print_expr_or_var(var2)}, {hex(jump_to)} )"
                case IfNotEqualCmd(var1, var2, jump_to):
                    start_indented_block = True
                    value = f"IfNotEqual ( {print_expr_or_var(var1)}, {print_expr_or_var(var2)}, {hex(jump_to)} )"
                case ElseCmd(jump_to):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"Else ( {hex(jump_to)} )"
                case ElseIfCmd(start_from, unused1, condition, unused2, jump_to, unused3):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"ElseIf ( {hex(start_from)}, {hex(unused1)}, {print_expr_or_var(condition)}, {hex(unused2)}, {hex(jump_to)}, {hex(unused3)} )"
                case EndIfCmd(opcode):
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndIf"
                case GotoLabelCmd(label):
                    value = f"GotoLabel {print_expr_or_var(label)}"
                case NoopCmd(opcode):
                    value = f"Noop_{hex(opcode)}"
                case LabelCmd(opcode):
                    value = f"LabelPoint"
                case ThreadCmd(func, take_args, give_args):
                    start_indented_block = True
                    value = f"Thread1 {print_expr_or_var(func)} Get ( {', '.join(print_expr_or_var(x) for x in take_args)} ) Give ( {', '.join(print_expr_or_var(x) for x in give_args)} )"
                case Thread2Cmd(func, take_args, give_args):
                    start_indented_block = True
                    value = f"Thread2 {print_expr_or_var(func)} Get ( {', '.join(print_expr_or_var(x) for x in take_args)} ) Give ( {', '.join(print_expr_or_var(x) for x in give_args)} )"
                case CheckValCmd(is_const, duration):
                    value = f"CheckVal{'*' if is_const else '' } {print_expr_or_var(duration)}"                
                case WaitCmd(is_const, duration):
                    value = f"Wait{'*' if is_const else '' } {print_expr_or_var(duration)}"
                case Wait2Cmd(is_const, duration):
                    value = f"Wait2{'*' if is_const else '' } {print_expr_or_var(duration)}"
                case SwitchCmd(var, unused, jump_offset):
                    start_indented_block = True
                    value = f"Switch ( {print_expr_or_var(var)}, {hex(unused)}, {hex(jump_offset)} )"                
                case CaseCmd(is_const, var, jump_offset):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"Case{'*' if is_const else '' } ( {print_expr_or_var(var)}, {hex(jump_offset)} )"
                case CaseRangeCmd(is_const, lower, upper, jump_offset):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"CaseRange{'*' if is_const else '' } ( {print_expr_or_var(lower)} to {print_expr_or_var(upper)}, {hex(jump_offset)} )"
                case BreakSwitchCmd(opcode):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"BreakSwitch"
                case EndSwitchCmd(opcode):
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndSwitch"
                case DoWhileCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"DoWhile{'*' if is_const else '' } ( {print_expr_or_var(var)}, {hex(jump_offset)} )"
                case BreakCmd(opcode):
                    value = f"Break"
                case EndDoWhileCmd(opcode):
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndDoWhile"
                case ReadTableLengthCmd(is_const, arrayt):
                    value = f"ReadTableLength ( {print_expr_or_var(arrayt)} )"
                case ReadTableEntryCmd(is_const, arrayt, index):
                    value = f"ReadTableEntry ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)} )"
                case ReadTableEntryToVarCmd(is_const, arrayt, index, var):
                    value = f"ReadTableEntryToVar ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(var)} )"
                case ReadTableEntriesVec3Cmd(is_const, arrayt, index, x, y, z):
                    value = f"ReadTableEntriesVec3 ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(x)}, {print_expr_or_var(y)}, {print_expr_or_var(z)} )"
                case TableGetIndexCmd(is_const, arrayt, occurance, var):
                    value = f"TableGetIndex ( {print_expr_or_var(arrayt)}, {print_expr_or_var(occurance)}, {print_expr_or_var(var)} )"
                case UnknownCmd(opcode, is_const, args):
                    value = f"Unk_0x{opcode:x}{'*' if is_const else ' '} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case _:
                    raise Exception()
            
            if ': ' in value:
                result += f"      - {'    ' * indentation}'{value}'\n"
            else:
                result += f"      - {'    ' * indentation}{value}\n"
    
    return result

def write_functions(sections: list[bytes], symbol_ids: dict):
    # section 5 (function imports)
    imports = read_function_imports(sections[5])
    
    for fn in imports:
        symbol_ids[fn.id] = fn
    
    out_str = 'imports:\n'
    for fn in imports:
        out_str += print_function_import(fn)
    
    # section 1 (function definitions)
    definitions = read_function_definitions(sections[1], sections[7], symbol_ids)
    
    for fn in definitions:
        symbol_ids[fn.id] = fn
    
    for fn in definitions:
        if fn.code is not None and len(fn.code) > 0:
            local_symbol_ids = symbol_ids.copy()
            for var in fn.vars:
                local_symbol_ids[var.id] = var
            for table in fn.tables:
                local_symbol_ids[table.id] = table
            for unk in fn.unk:
                local_symbol_ids[unk.id] = unk
            
            analyze_function_def(fn, local_symbol_ids)
    
    out_str += 'definitions:\n'
    is_first = True
    for fn in definitions:
        if not is_first:
            if out_str.endswith('  \n'):
                out_str = out_str[:-5] + '\n'
            else:
                out_str += '    \n'
        
        out_str += print_function_def(fn)
        is_first = False
    
    with open(argv[1] + '.functions.yaml', 'w', encoding='utf-8') as f:
        f.write(out_str)
