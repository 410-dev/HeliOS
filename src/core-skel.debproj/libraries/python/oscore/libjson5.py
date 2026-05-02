import os
import re
import codecs


def parse(text):
    """
    Parses a JSON5 formatted string into a Python object (dict, list, etc.).
    Supports:
    - Single and multi-line comments
    - Unquoted keys
    - Single-quoted strings
    - Trailing commas in objects and arrays
    - Hexadecimal numbers
    - Infinity and NaN
    - Explicit plus signs and decimal extensions
    """

    # 1. Lexical Scanner (Tokenizer)
    # Define regex patterns for JSON5 elements. re.VERBOSE allows multi-line regex for readability.
    token_pattern = re.compile(r"""
        (?P<WHITESPACE>\s+) |
        (?P<LINE_COMMENT>//[^\n]*) |
        (?P<BLOCK_COMMENT>/\*.*?\*/) |
        (?P<STRING_DOUBLE>"(?:\\.|[^"\\])*") |
        (?P<STRING_SINGLE>'(?:\\.|[^'\\])*') |
        (?P<NUMBER>[-+]?(?:0[xX][0-9a-fA-F]+|(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?|Infinity|NaN)) |
        (?P<IDENTIFIER>[a-zA-Z_$][a-zA-Z0-9_$]*) |
        (?P<PUNCTUATION>[{}[\]:,]) |
        (?P<UNRECOGNIZED>.)
    """, re.VERBOSE | re.DOTALL)

    tokens = []
    for match in token_pattern.finditer(text):
        kind = match.lastgroup
        value = match.group()

        # Strip out formatting and comments before parsing
        if kind in ('WHITESPACE', 'LINE_COMMENT', 'BLOCK_COMMENT'):
            continue
        if kind == 'UNRECOGNIZED':
            raise ValueError(f"Unrecognized token found at index {match.start()}: {value}")

        tokens.append((kind, value))

    # 2. Recursive Descent Parser
    class JSON5Parser:
        def __init__(self, token_list):
            self.tokens = token_list
            self.pos = 0

        def peek(self):
            if self.pos < len(self.tokens):
                return self.tokens[self.pos]
            return None, None

        def consume(self, expected_kind=None, expected_value=None):
            kind, value = self.peek()
            if expected_kind and kind != expected_kind:
                raise ValueError(f"Parse error: Expected token kind '{expected_kind}', got '{kind}'")
            if expected_value and value != expected_value:
                raise ValueError(f"Parse error: Expected value '{expected_value}', got '{value}'")
            self.pos += 1
            return kind, value

        def decode_string(self, s):
            # Remove the surrounding quotes and decode escape characters
            inner = s[1:-1]
            return codecs.decode(inner.encode('utf-8'), 'unicode_escape')

        def parse_value(self):
            kind, value = self.peek()
            if not kind:
                raise ValueError("Unexpected end of input")

            if kind == 'PUNCTUATION':
                if value == '{':
                    return self.parse_object()
                if value == '[':
                    return self.parse_array()
                raise ValueError(f"Unexpected punctuation: {value}")

            self.consume()  # Move past the value token

            if kind in ('STRING_DOUBLE', 'STRING_SINGLE'):
                return self.decode_string(value)

            if kind == 'NUMBER':
                # Handle special JSON5 number formats
                if value.endswith('Infinity'):
                    return float('inf') if not value.startswith('-') else float('-inf')
                if value.endswith('NaN'):
                    return float('nan')
                if 'x' in value or 'X' in value:
                    return int(value, 16)
                if '.' in value or 'e' in value or 'E' in value:
                    return float(value)
                return int(value)

            if kind == 'IDENTIFIER':
                # Handle boolean and null literals
                if value == 'true': return True
                if value == 'false': return False
                if value == 'null': return None
                raise ValueError(f"Unexpected identifier outside of object key: {value}")

            raise ValueError(f"Unexpected token: {value}")

        def parse_object(self):
            self.consume('PUNCTUATION', '{')
            obj = {}

            while True:
                kind, value = self.peek()

                # Check for empty object or end of object
                if kind == 'PUNCTUATION' and value == '}':
                    self.consume()
                    break

                # Parse the key (can be an identifier, single-quoted string, or double-quoted string)
                if kind == 'IDENTIFIER':
                    key = value
                    self.consume()
                elif kind in ('STRING_DOUBLE', 'STRING_SINGLE'):
                    key = self.decode_string(value)
                    self.consume()
                else:
                    raise ValueError(f"Expected object key, got {value}")

                # Colon separator
                self.consume('PUNCTUATION', ':')

                # Parse the value assigned to the key
                obj[key] = self.parse_value()

                # Handle commas and trailing commas
                kind, value = self.peek()
                if kind == 'PUNCTUATION' and value == ',':
                    self.consume()  # Trailing commas are gracefully ignored on the next loop
                elif kind == 'PUNCTUATION' and value == '}':
                    pass  # Will be handled at the start of the next iteration
                else:
                    raise ValueError(f"Expected ',' or '}}' in object, got {value}")

            return obj

        def parse_array(self):
            self.consume('PUNCTUATION', '[')
            arr = []

            while True:
                kind, value = self.peek()

                # Check for empty array or end of array
                if kind == 'PUNCTUATION' and value == ']':
                    self.consume()
                    break

                # Parse the item
                arr.append(self.parse_value())

                # Handle commas and trailing commas
                kind, value = self.peek()
                if kind == 'PUNCTUATION' and value == ',':
                    self.consume()
                elif kind == 'PUNCTUATION' and value == ']':
                    pass  # Handled at the start of next iteration
                else:
                    raise ValueError(f"Expected ',' or ']' in array, got {value}")

            return arr

    # 3. Execute the parser
    parser = JSON5Parser(tokens)
    result = parser.parse_value()

    # Ensure there is no trailing garbage data
    if parser.pos < len(tokens):
        raise ValueError("Extra unrecognized data after parsed JSON5 value")

    return result

def load(path: str) -> dict:
    """Load JSON5 from a file."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return parse(f.read())
