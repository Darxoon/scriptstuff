import functions
from other_types import ScriptImport
from util import SymbolIds
from variables import Var

# tokenization
def is_identifier(string: str) -> bool:
    return all(c == '_' or c.isalnum() for c in string)

def tokenize(code: str) -> list[str]:
    tokens: list[str] = []
    
    while len(code) > 0:
        if code[0] == ' ':
            code = code[1:]
            continue
        
        if is_identifier(code[0]):
            token_end = next((i + 1 for i, c in enumerate(code[1:]) if not is_identifier(c)), len(code))
        else:
            token_end = 1
        
        token, code = code[:token_end], code[token_end:]
        tokens.append(token)
    
    return tokens

class TokenStream:
    def __init__(self, code: str):
        self.tokens = iter(tokenize(code))
        self.current = ""
        
        self.advance()
    
    def peek(self) -> str:
        return self.current
    
    def advance(self) -> str:
        current, self.current = self.current, next(self.tokens, "")
        return current
    
    def expect(self, expected: str) -> str:
        token = self.advance()
        assert token == expected, f"Expected token {expected!r}, got {token!r}"
        return expected

# parsing
def get_func_from_name(name: str, symbol_ids: SymbolIds) -> functions.FunctionDef | ScriptImport:
    func = None
    for value in symbol_ids.flat().values():
        if isinstance(value, (functions.FunctionDef, ScriptImport)) and value.name == name:
            func = value
    
    assert func is not None, f"Could not find function with name {name}"
    return func

def read_function_id(tokens: TokenStream, current_func: functions.FunctionDef, symbol_ids: SymbolIds) -> functions.FunctionDef | ScriptImport | None:
    if tokens.peek() != 'fn':
        return None
    
    tokens.advance()
    tokens.expect(':')
    name = tokens.advance()
    
    assert is_identifier(name), "Function name (fn:...) has to be an alphanumeric identifier"
    
    if name == 'self':
        return current_func
    
    return get_func_from_name(name, symbol_ids)

def read_number_var(tokens: TokenStream, constants: list[Var]) -> Var | None:
    if not tokens.peek().isdigit():
        return None
    
    # parse number
    num = tokens.advance()
    
    if tokens.peek() == '.':
        raise NotImplementedError("Floats not supported yet")
    
    tokens.expect('`')
    
    # find var
    var = next((c for c in constants if c.data_type == 1 and c.user_data == int(num)), None)
    if var is None:
        raise ValueError(f"Could not find Int constant with content {num}")
    
    return var

def read_string_var(tokens: TokenStream, constants: list[Var]) -> Var | None:
    if tokens.peek() not in "'\"":
        return None
    
    # parse string
    quote_type = tokens.advance()
    string = ""
    
    while tokens.peek() != quote_type and tokens.peek() != "":
        string += ' ' + tokens.advance()
    
    string = string[1:]
    
    if tokens.advance() == "":
        raise ValueError("Unclosed string")
    
    # find var
    var = next((c for c in constants if c.data_type == 3 and c.user_data == string), None)
    if var is None:
        raise ValueError(f"Could not find String constant with content {string!r}")
    
    return var

def read_var_ref(tokens: TokenStream, current_func: functions.FunctionDef, 
                 constants: list[Var], symbol_ids: SymbolIds) -> functions.FunctionDef | ScriptImport | Var | None:
    if (num := read_number_var(tokens, constants)) is not None:
        return num
    elif (string := read_string_var(tokens, constants)) is not None:
        return string
    elif (func := read_function_id(tokens, current_func, symbol_ids)) is not None:
        return func
    else:
        return None