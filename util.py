from typing import Any

def read_string(section: bytes, offset_words: int) -> str:
    buffer = section[offset_words * 4:]
    bytelen = buffer.index(0)
    return str(buffer[:bytelen], 'utf-8')

class SymbolIds:
    layers: list[dict]
    
    def __init__(self, *, layers: list[dict] | None = None):
        self.layers = layers if layers is not None else [{}]
    
    def get(self, id: int) -> Any:
        for layer in reversed(self.layers):
            if id in layer:
                return layer[id]
        
        return id
    
    def add(self, value, *, id = None):
        self.layers[-1][id if id is not None else value.id] = value
    
    def push(self):
        self.layers.append({})
    
    def pop(self):
        if len(self.layers) > 1:
            self.layers.pop()
    
    def copy(self):
        return SymbolIds(layers=[layer.copy() for layer in self.layers])
