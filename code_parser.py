import functions
from other_types import ScriptImport
from util import SymbolIds

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
    
    def expect(self, token: str) -> str:
        assert self.advance() == token
        return token

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
