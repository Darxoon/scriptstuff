from array import array
from dataclasses import dataclass, field, replace
import dataclasses
from itertools import chain
import json

from other_types import Label, ScriptImport, print_function_import, print_label, read_function_imports, read_label
from tables import Table, print_table, read_table
from util import SymbolIds, read_string
from variables import Var, VarCategory, print_var, read_variable

# script expressions
@dataclass
class ExprSymbol:
    label: str

EXPR_SYMBOLS = {
    0x3f: ExprSymbol('next_function'),
    0x41: ExprSymbol('('),
    0x42: ExprSymbol(')'),
    0x43: ExprSymbol('||'),
    0x44: ExprSymbol('&&'),
    
    0x45: ExprSymbol('|'),
    0x46: ExprSymbol('&'),
    0x47: ExprSymbol('^'),
    0x48: ExprSymbol('<<'),
    0x49: ExprSymbol('>>'),
    
    0x4a: ExprSymbol('=='),
    0x4b: ExprSymbol('!='),
    0x4c: ExprSymbol('>'),
    0x4d: ExprSymbol('<'),
    0x4e: ExprSymbol('>='),
    0x4f: ExprSymbol('<='),
    
    0x52: ExprSymbol('%'),
    0x53: ExprSymbol('+'),
    0x54: ExprSymbol('-'),
    0x55: ExprSymbol('*'),
    0x56: ExprSymbol('/'),
}

@dataclass
class Expr:
    elements: list['Var | CallCmd | int'] = field(default_factory=lambda: [])

def read_expr(initial_element: int | None, arr: enumerate[int], symbol_ids: SymbolIds, raise_on_ending_sequence = False) -> Expr:
    elements = []
    
    values = chain([(0, initial_element)], arr) if initial_element is not None else arr
    
    for _, value in values:
        if value == 0x40:
            break
        
        if value == 0xc:
            elements.append(read_call_cmd(arr, symbol_ids, ReadCmdOptions(0xc, False)))
            continue
        
        if value in EXPR_SYMBOLS:
            var = EXPR_SYMBOLS[value]
        else:
            var = symbol_ids.get(value)
        elements.append(var)
    
    return Expr(elements)

def print_expr_or_var(value, braces_around_expression = False) -> str:
    match value:
        case Expr(elements):
            content = ' '.join(print_expr_or_var(x) for x in elements)
            if braces_around_expression:
                return f'( {content} )'
            else:
                return content
        case ExprSymbol(label):
            return label
        case Var(name, alias, category, id, data_type, flags, user_data):
            if name is not None:
                return f"{category.name}:{name}"
            elif alias is not None:
                return f"{category.name}:{alias}"
            elif category == VarCategory.Const and user_data is not None:
                return f"{user_data}`" if isinstance(user_data, (int, float)) else repr(user_data)
            else:
                return f"{category.name}:0x{id:x}"
        case ScriptImport(name) | FunctionDef(name):
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
        case _:
            raise Exception(f"Unknown thing {repr(value)}")

# script instructions
@dataclass
class ReadCmdOptions:
    opcode: int
    is_const: bool
    cmd_offset: int | None = None

@dataclass
class ReturnValCmd:
    is_const: bool
    value: Expr | Var | int

def read_returnval_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReturnValCmd:
    value_int = next(arr)[1]
    if options.is_const:
        value = symbol_ids.get(value_int)
        assert isinstance(value, Var) or isinstance(value, int)
        if value == 0x40:
            value = Expr()
    else:
        value = read_expr(value_int, arr, symbol_ids)
    
    return ReturnValCmd(options.is_const, value)

@dataclass 
class CallCmd:
    is_const: bool
    func: 'ScriptImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CallCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, ScriptImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if options.is_const:
            var = symbol_ids.get(value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallCmd(options.is_const, func, args)

@dataclass
class CallAsThreadCmd:
    is_const: bool
    func: 'ScriptImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_as_thread_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CallAsThreadCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, ScriptImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if options.is_const:
            var = symbol_ids.get(value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallAsThreadCmd(options.is_const, func, args)

# Same as CallAsThread but sets the original thread as the new thread's parent
# This might mean that the parent thread waits for the child to be done before it continues
# TODO: But idk if that's true
@dataclass
class CallAsChildThreadCmd:
    is_const: bool
    func: 'ScriptImport | FunctionDef | int'
    args: list[Expr | Var | int]

def read_call_as_child_thread_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CallAsChildThreadCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, ScriptImport) or isinstance(func, FunctionDef) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if options.is_const:
            var = symbol_ids.get(value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallAsChildThreadCmd(options.is_const, func, args)

@dataclass 
class CallVarCmd:
    is_const: bool
    func: Var | int
    args: list[Expr | Var | int]

def read_call_var_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CallVarCmd:
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, Var) or isinstance(func, int)
    
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if options.is_const:
            var = symbol_ids.get(value)
            args.append(var)
        else:
            args.append(read_expr(value, arr, symbol_ids))
    
    return CallVarCmd(options.is_const, func, args)

@dataclass
class SetCmd:
    is_const: bool
    destination: Var | int
    value: Expr | Var | int

def read_set_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> SetCmd:
    destination_int = next(arr)[1]
    destination = symbol_ids.get(destination_int)
    assert isinstance(destination, Var) or isinstance(destination, int)
    
    if options.is_const:
        value_int = next(arr)[1]
        value = symbol_ids.get(value_int)
        assert isinstance(value, Var) or isinstance(value, int)
        if value == 0x40:
            value = Expr()
    else:
        value = read_expr(None, arr, symbol_ids)
    
    return SetCmd(options.is_const, destination, value)

@dataclass
class ReadTableLengthCmd:
    is_const: bool
    arrayt: Table

def read_read_table_length_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReadTableLengthCmd:
    assert not options.is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int)
    
    return ReadTableLengthCmd(options.is_const, arrayt)

# returns the value to FuncVar0 by default (but other variables can be set to whatever it returns directly)
@dataclass
class ReadTableEntryCmd:
    is_const: bool
    arrayt: Table
    index: Expr | Var | int

def read_read_table_entry_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReadTableEntryCmd:
    assert not options.is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int)
    
    return ReadTableEntryCmd(options.is_const, arrayt, index)

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

def read_read_table_entry_to_var_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReadTableEntryToVarCmd:
    assert not options.is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int)    
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int)
    assert isinstance(var, Var)
    
    return ReadTableEntryToVarCmd(options.is_const, arrayt, index, var)

# read 2 entries starting from the specified index and save those values to 2 specified variables. 
# Used to read 2d vector values without having to call ReadTableEntry 2 times.
@dataclass
class ReadTableEntriesVec2Cmd:
    is_const: bool
    arrayt: Table
    index: Expr | Var | int
    x: Var
    y: Var

def read_read_table_entries_vec2_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReadTableEntriesVec2Cmd:
    assert not options.is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int)    
    
    x_int = next(arr)[1]
    x = symbol_ids.get(x_int)
    y_int = next(arr)[1]
    y = symbol_ids.get(y_int)
    
    assert isinstance(x, Var)
    assert isinstance(y, Var)
    
    return ReadTableEntriesVec2Cmd(options.is_const, arrayt, index, x, y)

# read 3 entries starting from the specified index and save those values to 3 specified variables. 
# Used to read 3d vector values without having to call ReadTableEntry 3 times.
@dataclass
class ReadTableEntriesVec3Cmd:
    is_const: bool
    arrayt: Table
    index: Expr | Var | int
    x: Var
    y: Var
    z: Var

def read_read_table_entries_vec3_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReadTableEntriesVec3Cmd:
    assert not options.is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int)
    index_int = next(arr)[1]
    index = symbol_ids.get(index_int)    
    
    x_int = next(arr)[1]
    x = symbol_ids.get(x_int)
    y_int = next(arr)[1]
    y = symbol_ids.get(y_int)
    z_int = next(arr)[1]
    z = symbol_ids.get(z_int)
    
    assert isinstance(x, Var)
    assert isinstance(y, Var)
    assert isinstance(z, Var)
    
    return ReadTableEntriesVec3Cmd(options.is_const, arrayt, index, x, y, z)
@dataclass
class TableGetIndexCmd:
    is_const: bool
    arrayt: Table
    occurance: Expr | Var | int
    var: Var

def read_table_get_index_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> TableGetIndexCmd:
    assert not options.is_const
    
    arrayt_int = next(arr)[1]
    arrayt = symbol_ids.get(arrayt_int)
    occurance_int = next(arr)[1]
    occurance = symbol_ids.get(occurance_int)    
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int)
    assert isinstance(var, Var)
    
    return TableGetIndexCmd(options.is_const, arrayt, occurance, var)

@dataclass
class ReturnCmd:
    pass

def read_return_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ReturnCmd:
    assert not options.is_const
    
    # A new layer gets pushed to in child threads (Thread and Thread2) for captured vars
    # Return ends a thread so it gets popped again
    symbol_ids.pop()
    
    return ReturnCmd()

@dataclass
class GetArgsCmd:
    func: 'FunctionDef'
    args: list[Var | int]

def read_get_args_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> GetArgsCmd:
    assert not options.is_const
    
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, FunctionDef)
    
    args = []
    for _, value in arr:
        if value == 0x8:
            break
        
        var = symbol_ids.get(value)
        assert isinstance(var, Var) or isinstance(var, int)
        args.append(var)
        
    return GetArgsCmd(func, args)

@dataclass
class IfCmd:
    condition: Expr
    unused1: int
    jump_to: int
    unused2: int

def read_if_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> IfCmd:
    assert not options.is_const
    
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
    jump_to: int # TODO: ensure that jump_to always points to an Else, ElseIf or EndIf

def read_ifequal_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> IfEqualCmd:
    assert not options.is_const
    
    var1_int = next(arr)[1]
    var1 = symbol_ids.get(var1_int)
    var2_int = next(arr)[1]
    var2 = symbol_ids.get(var2_int)
    jump_to = next(arr)[1]
    
    return IfEqualCmd(var1, var2, jump_to)

@dataclass
class IfNotEqualCmd:
    var1: Expr | Var | int
    var2: Expr | Var | int
    jump_to: int

def read_ifnotequal_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> IfNotEqualCmd:
    assert not options.is_const
    
    var1_int = next(arr)[1]
    var1 = symbol_ids.get(var1_int)
    var2_int = next(arr)[1]
    var2 = symbol_ids.get(var2_int)
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

def read_else_if_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ElseIfCmd:
    assert not options.is_const
    
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

def read_else_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ElseCmd:
    assert not options.is_const
    
    jump_to = next(arr)[1]
    
    return ElseCmd(jump_to)

@dataclass
class GotoLabelCmd:
    label: Label | int

def read_goto_label_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> GotoLabelCmd:
    assert not options.is_const
    
    label_int = next(arr)[1]
    label = symbol_ids.get(label_int)
    assert isinstance(label, Label) or isinstance(label, int)
    
    return GotoLabelCmd(label)

@dataclass
class NoopCmd:
    opcode: int

def read_noop_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> NoopCmd:
    assert not options.is_const
    
    return NoopCmd(options.opcode)

@dataclass
class LabelCmd:
    pass

def read_label_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> LabelCmd:
    assert not options.is_const
    
    return LabelCmd()

@dataclass
class EndIfCmd:
    pass

def read_endif_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> EndIfCmd:
    assert not options.is_const
    
    return EndIfCmd()

@dataclass
class ThreadCmd:
    func: 'FunctionDef | ScriptImport | int'
    take_args: list[int]
    give_args: list[Var | int]

def read_thread_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ThreadCmd:
    assert not options.is_const
    
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, FunctionDef)
    
    take_args: list[int] = []
    for _, value in arr:
        if value == 0x8:
            break
        
        take_args.append(value)
    
    give_args: list[Var | int] = []
    for _, value in arr:
        if value == 0x11:
            break
        
        var = symbol_ids.get(value)
        assert isinstance(var, Var) or isinstance(var, int)
        give_args.append(var)
    
    # Thread and Thread2 are always ended by a Return
    # this will make sure the thread body has access to the captured vars
    # and that they won't leak out of this thread
    symbol_ids.push()
    
    assert len(give_args) == len(take_args)
    for give, take in zip(give_args, take_args):
        if not isinstance(give, Var):
            continue
        
        copy = replace(give)
        copy.id = take
        if copy.category == VarCategory.TempVar:
            copy.category = VarCategory.OuterTempVar
        symbol_ids.add(copy)
        
    return ThreadCmd(func, take_args, give_args)

@dataclass
class Thread2Cmd:
    func: 'FunctionDef | ScriptImport | int'
    take_args: list[int]
    give_args: list[Var | int]

def read_thread2_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> Thread2Cmd:
    assert not options.is_const
    
    func_int = next(arr)[1]
    func = symbol_ids.get(func_int)
    assert isinstance(func, FunctionDef)
    
    take_args: list[int] = []
    for _, value in arr:
        if value == 0x8:
            break
        
        take_args.append(value)
        
    give_args: list[Var | int] = []
    for _, value in arr:
        if value == 0x11:
            break
        
        var = symbol_ids.get(value)
        assert isinstance(var, Var) or isinstance(var, int)
        give_args.append(var)
    
    # Thread and Thread2 are always ended by a Return
    # this will make sure the thread body has access to the captured vars
    # and that they won't leak out of this thread
    symbol_ids.push()
    
    assert len(give_args) == len(take_args)
    for give, take in zip(give_args, take_args):
        if not isinstance(give, Var):
            continue
        
        copy = replace(give)
        copy.id = take
        symbol_ids.add(copy)
    
    return Thread2Cmd(func, take_args, give_args)

@dataclass
class DeleteRuntimeCmd:
    is_const: bool
    var: Expr | Var | int

def read_delete_runtime_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> DeleteRuntimeCmd:
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int)
    if options.is_const:
        assert isinstance(var, Var) or isinstance(var, int)
    
    return DeleteRuntimeCmd(options.is_const, var)

@dataclass
class WaitCmd:
    is_const: bool
    duration: Expr | Var | int

def read_wait_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> WaitCmd:
    if options.is_const:
        duration_int = next(arr)[1]
        duration = symbol_ids.get(duration_int)
        assert isinstance(duration, Var) or isinstance(duration, int)
    else:
        duration = read_expr(None, arr, symbol_ids)
    
    return WaitCmd(options.is_const, duration)

@dataclass
class WaitMsCmd:
    is_const: bool
    duration: Expr | Var | int

def read_wait_ms_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> WaitMsCmd:
    if options.is_const:
        duration_int = next(arr)[1]
        duration = symbol_ids.get(duration_int)
        assert isinstance(duration, Var) or isinstance(duration, int)
    else:
        duration = read_expr(None, arr, symbol_ids)
    
    return WaitMsCmd(options.is_const, duration)

@dataclass
class SwitchCmd:
    var: Var | int
    unused: int
    jump_offset: int

def read_switch_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> SwitchCmd:
    assert not options.is_const

    var_int = next(arr)[1]
    var = symbol_ids.get(var_int)
    assert isinstance(var, Var) or isinstance(var, int)
    
    unused = next(arr)[1]
    jump_offset = next(arr)[1]
    
    return SwitchCmd(var, unused, jump_offset)

@dataclass
class CaseEqCmd:
    is_const: bool
    value: Expr | Var | int
    jump_offset: int

def read_case_eq_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CaseEqCmd:
    value_int = next(arr)[1]
    if options.is_const:
        value = symbol_ids.get(value_int)
        assert isinstance(value, Var) or isinstance(value, int)
    else:
        value = symbol_ids.get(value_int)
    
    jump_offset = next(arr)[1]
    
    return CaseEqCmd(options.is_const, value, jump_offset)

# A variant of the switch instruction that seems to also take two floating point values...
# It being a check as to whether the match value is within this range is just a guess.
@dataclass
class CaseRangeCmd:
    is_const: bool
    lower: Expr | Var | int
    upper: Expr | Var | int
    jump_offset: int

def read_case_range_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CaseRangeCmd:
    
    lower_int = next(arr)[1]
    if options.is_const:
        lower = symbol_ids.get(lower_int)
        assert isinstance(lower, Var) or isinstance(lower, int)
    else:
        lower = symbol_ids.get(lower_int)
        
    upper_int = next(arr)[1]
    if options.is_const:
        upper = symbol_ids.get(upper_int)
        assert isinstance(upper, Var) or isinstance(upper, int)
    else:
        upper = symbol_ids.get(upper_int)
    
    jump_offset = next(arr)[1]
    
    return CaseRangeCmd(options.is_const, lower, upper, jump_offset)

@dataclass
class BreakSwitchCmd:
    pass

def read_breakswitch_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> BreakSwitchCmd:
    assert not options.is_const
    
    return BreakSwitchCmd()

@dataclass
class EndSwitchCmd:
    pass

def read_endswitch_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> EndSwitchCmd:
    assert not options.is_const
    
    return EndSwitchCmd()

@dataclass
class WhileCmd:
    is_const: bool
    value: Expr | Var | int
    jump_offset: int

def read_while_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> WhileCmd:
    if options.is_const:
        value_int = next(arr)[1]
        value = symbol_ids.get(value_int)
        assert isinstance(value, Var) or isinstance(value, int)
    else:
        value = read_expr(None, arr, symbol_ids)
    
    jump_offset = next(arr)[1]
    
    return WhileCmd(options.is_const, value, jump_offset)

@dataclass
class BreakCmd:
    pass

def read_break_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> BreakCmd:
    assert not options.is_const
    
    return BreakCmd()

@dataclass
class EndWhileCmd:
    pass

def read_end_while_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> EndWhileCmd:
    assert not options.is_const
    
    return EndWhileCmd()

@dataclass
class WaitCompletedCmd:
    is_const: bool
    runtime: Expr | Var | int

def read_wait_completed_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> WaitCompletedCmd:
    if options.is_const:
        runtime_int = next(arr)[1]
        runtime = symbol_ids.get(runtime_int)
        assert isinstance(runtime, Var) or isinstance(runtime, int)
    else:
        runtime = read_expr(None, arr, symbol_ids)
    
    return WaitCompletedCmd(options.is_const, runtime)

@dataclass
class WaitWhileCmd:
    condition: Expr
    unused1: int
    unused2: int

def read_wait_while_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> WaitWhileCmd:
    assert not options.is_const
    
    condition = read_expr(None, arr, symbol_ids)
    unused1 = next(arr)[1]
    unused2 = next(arr)[1]
    
    return WaitWhileCmd(condition, unused1, unused2)

@dataclass
class ToIntCmd:
    variable: Var | int

def read_to_int_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> ToIntCmd:
    assert not options.is_const
    
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int)
    
    return ToIntCmd(var)

@dataclass
class LoadKSMCmd:
    variable: Var | int

def read_load_ksm_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> LoadKSMCmd:
    assert not options.is_const
    
    var_int = next(arr)[1]
    var = symbol_ids.get(var_int)
    
    return LoadKSMCmd(var)

@dataclass
class GetArgCountCmd:
    pass

def read_get_arg_count_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> GetArgCountCmd:
    assert not options.is_const
    
    return GetArgCountCmd()

@dataclass
class CaseLteCmd:
    is_const: bool
    value: Expr | Var | int
    jump_offset: int

def read_case_lte_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> CaseLteCmd:
    
    value_int = next(arr)[1]
    if options.is_const:
        value = symbol_ids.get(value_int)
        assert isinstance(value, Var) or isinstance(value, int)
    else:
        value = symbol_ids.get(value_int)
    
    jump_offset = next(arr)[1]
    
    return CaseLteCmd(options.is_const, value, jump_offset)

@dataclass
class UnknownCmd:
    opcode: int
    is_const: bool
    args: list[Expr | Var | int]

def read_unknown_cmd(arr: enumerate[int], symbol_ids: SymbolIds, options: ReadCmdOptions) -> UnknownCmd:
    args = []
    for _, value in arr:
        if value == 0x11:
            break
        
        if value in EXPR_SYMBOLS:
            var = EXPR_SYMBOLS[value]
        else:
            var = symbol_ids.get(value)
        args.append(var)
    
    return UnknownCmd(options.opcode, options.is_const, args)

INSTRUCTIONS = {
    # TODO: some of the noops return 1, some 3, might be worth looking into
    0x2: read_noop_cmd,
    0x3: read_returnval_cmd,
    0x4: read_label_cmd,
    0x5: read_get_args_cmd,
    0x6: read_thread_cmd,
    0x7: read_thread2_cmd,
    0x9: read_return_cmd,
    0xa: read_goto_label_cmd,
    0xc: read_call_cmd,
    0xd: read_call_as_thread_cmd,
    0xe: read_call_as_child_thread_cmd,
    0x12: read_delete_runtime_cmd,
    0x16: read_wait_cmd,
    0x17: read_wait_ms_cmd,
    0x18: read_if_cmd,
    
    # Unusual If Instructions (experimental)
    #0x19: read_ifequal_cmd,
    #0x1d: read_ifnotequal_cmd,
    
    # Switch, Case Instructions
    0x26: read_else_cmd,
    0x27: read_else_if_cmd,
    0x28: read_endif_cmd,
    0x29: read_switch_cmd,
    0x2a: read_case_eq_cmd,
    0x2f: read_case_lte_cmd,
    0x30: read_case_range_cmd,
    0x37: read_breakswitch_cmd,
    0x38: read_endswitch_cmd,
    
    # While Instructions
    0x39: read_while_cmd,
    0x3a: read_break_cmd,
    0x3c: read_end_while_cmd,
    
    0x3d: read_set_cmd,
    
    # Array Instructions 
    0x67: read_read_table_length_cmd,
    0x68: read_read_table_entry_cmd,
    0x69: read_read_table_entry_to_var_cmd,
    0x6a: read_read_table_entries_vec2_cmd,
    0x6b: read_read_table_entries_vec3_cmd,
    0x6d: read_table_get_index_cmd,
    
    0x75: read_load_ksm_cmd,
    0x77: read_get_arg_count_cmd,
    
    # TODO: are these noops?
    0x7c: read_noop_cmd,
    0x7d: read_noop_cmd,
    
    0x80: read_call_var_cmd,
    # 0x81: read_call_var_as_thread,
    # 0x82: read_call_var_as_child_thread,
    0x85: read_to_int_cmd,
    0x89: read_wait_completed_cmd,
    0x9f: read_wait_while_cmd,
}


# function definitions
@dataclass
class FunctionDef:
    name: str | None
    id: int
    is_public: int
    field_0xc: int
    return_var: int
    field_0x34: int
    
    code: array
    code_offset: int
    instructions: list | None
    
    vars: list[Var]
    tables: list[Table]
    unk: list[Label]
    
    # analysis
    thread_references: list['FunctionDef'] = field(default_factory=list)
    thread2_references: list['FunctionDef'] = field(default_factory=list)

def read_function_definitions(section: bytes, code_section: bytes) -> list[FunctionDef]:
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
        return_var = next(arr)[1]
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
            var = read_variable(arr, section, VarCategory.LocalVar)
            
            if var.name == None:
                assert (var.id & 0xFF) == 0
                var.alias = str((var.id >> 8) & 0xFF) # TODO: make this more exact
            
            variables.append(var)
        
        # TODO: table values don't work yet here
        tables = []
        for _ in range(next(arr)[1]):
            tables.append(read_table(arr, section))
        
        labels = []
        for _ in range(next(arr)[1]):
            labels.append(read_label(arr, section))
        
        definitions.append(FunctionDef(name, id, is_public, field_0xc, return_var, field_0x34, code, code_offset, None, variables, tables, labels))
    
    assert len(definitions) == count
    return definitions

def analyze_function_def(fn: FunctionDef, symbol_ids: SymbolIds):
    arr = enumerate(fn.code)
    instructions = []
    
    for i, value in arr:
        try:
            options = ReadCmdOptions(value & 0xfffffeff, value & 0x100 != 0, fn.code_offset + i * 4)
            
            if value & 0xfffffeff in INSTRUCTIONS:
                instruction = INSTRUCTIONS[value & 0xfffffeff](arr, symbol_ids, options)
                
                match instruction:
                    case ThreadCmd(func):
                        if isinstance(func, FunctionDef) and func is not fn:
                            func.thread_references.append(fn)
                    case Thread2Cmd(func):
                        if isinstance(func, FunctionDef) and func is not fn:
                            func.thread2_references.append(fn)
                
                instructions.append(instruction)
            else:
                instructions.append(read_unknown_cmd(arr, symbol_ids, options))
        except StopIteration:
            pass
    
    fn.instructions = instructions

def print_function_def(fn: FunctionDef) -> str:
    return_var_var = next((var for var in fn.vars if var.id == fn.return_var), None)
    return_var = print_expr_or_var(return_var_var) if return_var_var is not None else hex(fn.return_var)
    
    result = f"""  - name: {fn.name if fn.name != None else 'null'}
    id: 0x{fn.id:x}
    is_public: {fn.is_public}
    field_0xc: 0x{fn.field_0xc:x}
    return_var: {return_var}
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
    
    if len(fn.thread_references) == 1 and len(fn.thread2_references) == 0:
        result += f"    \n    generated_from_thread: true # used by fn:{fn.thread_references[0].name}\n"
    elif len(fn.thread_references) == 0 and len(fn.thread2_references) == 1:
        result += f"    \n    generated_from_thread2: true # used by fn:{fn.thread2_references[0].name}\n"
    elif fn.instructions and len(fn.instructions) > 0:
        result += "    \n    "
        
        if len(fn.thread_references) >= 1:
            thread_references = ', '.join(print_expr_or_var(x) for x in fn.thread_references)
            result += f"# used by Threads: {thread_references}\n    "
        if len(fn.thread2_references) >= 1:
            thread2_references = ', '.join(print_expr_or_var(x) for x in fn.thread2_references)
            result += f"# used by Thread2s: {thread2_references}\n    "
        
        result += "body:\n"
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
                    value = f"Set{'*' if is_const else ' '}  {print_expr_or_var(destination)} {print_expr_or_var(source, True)}"
                case CallCmd(is_const, func, args):
                    value = f"Call{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallAsThreadCmd(is_const, func, args):
                    value = f"CallAsThread{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallAsChildThreadCmd(is_const, func, args):
                    value = f"CallAsChildThread{'*' if is_const else ' '} {func if isinstance(func, int) else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case CallVarCmd(is_const, func, args):
                    value = f"CallVar{'*' if is_const else '' } {func if isinstance(func, int) else func.name} {args}"
                case ReturnCmd():
                    if indentation > 0:
                        indentation -= 1
                    
                    value = f"Return"
                case GetArgsCmd(func, args):
                    value = f"GetArgs fn:{'self' if func.name == fn.name else func.name} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case IfCmd(condition, unused1, jump_to, unused2):
                    start_indented_block = True
                    value = f"If {print_expr_or_var(condition)}" # , {hex(unused1)}, {hex(jump_to)}, {hex(unused2)}
                case IfEqualCmd(var1, var2, jump_to):
                    start_indented_block = True
                    value = f"IfEqual ( {print_expr_or_var(var1)}, {print_expr_or_var(var2)} )" # , {hex(jump_to)}
                case IfNotEqualCmd(var1, var2, jump_to):
                    start_indented_block = True
                    value = f"IfNotEqual ( {print_expr_or_var(var1)}, {print_expr_or_var(var2)} )" # , {hex(jump_to)}
                case ElseCmd(jump_to):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    value = f"Else" #  ( {hex(jump_to)} )
                case ElseIfCmd(start_from, unused1, condition, unused2, jump_to, unused3):
                    if indentation > 0:
                        indentation -= 1
                    start_indented_block = True
                    # value = f"ElseIf ( {hex(start_from)}, {hex(unused1)}, {print_expr_or_var(condition)}, {hex(unused2)}, {hex(jump_to)}, {hex(unused3)} )"
                    value = f"ElseIf {print_expr_or_var(condition)}"
                case EndIfCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndIf"
                case GotoLabelCmd(label):
                    value = f"GotoLabel {print_expr_or_var(label)}"
                case NoopCmd(opcode):
                    value = f"Noop_{hex(opcode)}"
                case LabelCmd():
                    value = f"LabelPoint"
                case ThreadCmd(func, take_args, give_args) | Thread2Cmd(func, take_args, give_args):
                    start_indented_block = True
                    
                    opcode = "Thread1" if isinstance(inst, ThreadCmd) else "Thread2"
                    if isinstance(func, FunctionDef):
                        label_or_func = json.dumps(func.name[1:func.name.rindex('_')] if func.name is not None else func.name)
                    else:
                        label_or_func = print_expr_or_var(func)
                    captures = ', '.join(print_expr_or_var(var) for var in give_args)
                    
                    value = f"{opcode} {label_or_func} Capture ( {captures} )"
                case DeleteRuntimeCmd(is_const, duration):
                    value = f"DeleteRuntime{'*' if is_const else '' } {print_expr_or_var(duration)}"                
                case WaitCmd(is_const, duration):
                    value = f"Wait{'*' if is_const else '' } {print_expr_or_var(duration)}"
                case WaitMsCmd(is_const, duration):
                    value = f"WaitMs{'*' if is_const else '' } {print_expr_or_var(duration)}"
                case SwitchCmd(var, unused, jump_offset):
                    start_indented_block = True
                    value = f"Switch {print_expr_or_var(var)}" # , {hex(unused)}, {hex(jump_offset)}                
                case CaseEqCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"Case{'*' if is_const else '' } == {print_expr_or_var(var)}" # , {hex(jump_offset)}       
                case CaseLteCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"Case{'*' if is_const else '' } <= {print_expr_or_var(var)}" # , {hex(jump_offset)}
                case CaseRangeCmd(is_const, lower, upper, jump_offset):
                    start_indented_block = True
                    value = f"CaseRange{'*' if is_const else '' } ( {print_expr_or_var(lower)} to {print_expr_or_var(upper)}" # , {hex(jump_offset)}
                case BreakSwitchCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"BreakSwitch"
                case EndSwitchCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndSwitch"
                case WhileCmd(is_const, var, jump_offset):
                    start_indented_block = True
                    value = f"While{'*' if is_const else '' } {print_expr_or_var(var)}" # , {hex(jump_offset)} )
                case BreakCmd():
                    value = f"Break"
                case EndWhileCmd():
                    if indentation > 0:
                        indentation -= 1
                    value = f"EndWhile"
                case ReadTableLengthCmd(is_const, arrayt):
                    value = f"ReadTableLength ( {print_expr_or_var(arrayt)} )"
                case ReadTableEntryCmd(is_const, arrayt, index):
                    value = f"ReadTableEntry ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)} )"
                case ReadTableEntryToVarCmd(is_const, arrayt, index, var):
                    value = f"ReadTableEntryToVar ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(var)} )"
                case ReadTableEntriesVec2Cmd(is_const, arrayt, index, x, y):
                    value = f"ReadTableEntriesVec2 ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(x)}, {print_expr_or_var(y)} )"
                case ReadTableEntriesVec3Cmd(is_const, arrayt, index, x, y, z):
                    value = f"ReadTableEntriesVec3 ( {print_expr_or_var(arrayt)}, {print_expr_or_var(index)}, {print_expr_or_var(x)}, {print_expr_or_var(y)}, {print_expr_or_var(z)} )"
                case TableGetIndexCmd(is_const, arrayt, occurance, var):
                    value = f"TableGetIndex ( {print_expr_or_var(arrayt)}, {print_expr_or_var(occurance)}, {print_expr_or_var(var)} )"
                case WaitCompletedCmd(is_const, runtime):
                    value = f"WaitCompleted{'*' if is_const else '' } {print_expr_or_var(runtime)}"
                case WaitWhileCmd(condition):
                    value = f"WaitWhile {print_expr_or_var(condition)}"
                case ToIntCmd(var):
                    value = f"ToInt {print_expr_or_var(var)}"
                case LoadKSMCmd(var):
                    value = f"LoadKSM {print_expr_or_var(var)}"
                case GetArgCountCmd():
                    value = f"GetArgCount"
                case UnknownCmd(opcode, is_const, args):
                    value = f"Unk_0x{opcode:x}{'*' if is_const else ' '} ( {', '.join(print_expr_or_var(x) for x in args)} )"
                case _:
                    raise Exception()
            
            if ': ' in value:
                result += f"      - {'    ' * indentation}'{value}'\n"
            else:
                result += f"      - {'    ' * indentation}{value}\n"
    
    return result

def print_function_imports(sections: list[bytes], symbol_ids: SymbolIds) -> str:
    # section 5 (function imports)
    imports = read_function_imports(sections[5])
    
    if len(imports) == 0:
        return ""
    
    out_str = '\nimports:\n'
    
    for fn in imports:
        symbol_ids.add(fn)
        out_str += print_function_import(fn)
    
    return out_str

def print_function_definitions(sections: list[bytes], symbol_ids: SymbolIds) -> str:
    # section 1 (function definitions)
    definitions = read_function_definitions(sections[1], sections[7])
    
    if len(definitions) == 0:
        return ""
    
    for fn in definitions:
        symbol_ids.add(fn)
    
    for fn in definitions:
        if fn.code is not None and len(fn.code) > 0:
            local_symbol_ids = symbol_ids.copy()
            
            for var in fn.vars:
                local_symbol_ids.add(var)
            for table in fn.tables:
                local_symbol_ids.add(table)
            for unk in fn.unk:
                local_symbol_ids.add(unk)
            
            analyze_function_def(fn, local_symbol_ids)
    
    out_str = '\ndefinitions:\n'
    is_first = True
    
    for fn in definitions:
        if not is_first:
            if out_str.endswith('  \n'):
                out_str = out_str[:-5] + '\n'
            else:
                out_str += '    \n'
        
        out_str += print_function_def(fn)
        is_first = False
    
    return out_str
