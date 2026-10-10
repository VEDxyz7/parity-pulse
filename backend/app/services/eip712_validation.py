"""Bounded structural EIP-712 validation only. Never signs or implies settlement safety."""

import re

from app.models.execution import address, hex_data


def validate_typed_data(typed):
    domain, types = typed["domain"], typed["types"]
    if len(types) > 64 or set(domain) - {"name", "version", "chainId", "verifyingContract", "salt"}:
        raise ValueError("Unknown EIP712 domain or excessive types")
    for name in types:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
            raise ValueError("Invalid EIP712 type identifier")
    if "name" in domain and not isinstance(domain["name"], str):
        raise ValueError("Invalid domain name")
    if "version" in domain and not isinstance(domain["version"], str):
        raise ValueError("Invalid domain version")
    if "salt" in domain and (
        not isinstance(domain["salt"], str)
        or not re.fullmatch(r"0x[0-9a-fA-F]{64}", domain["salt"])
    ):
        raise ValueError("Invalid domain salt")

    def validate(kind, value, depth=0):
        if depth > 16 or not isinstance(kind, str):
            raise ValueError("EIP712 type recursion limit")
        array = re.fullmatch(r"(.+)\[([0-9]*)\]", kind)
        if array:
            if (
                not isinstance(value, list)
                or len(value) > 100
                or array[2]
                and len(value) != int(array[2])
            ):
                raise ValueError("Invalid EIP712 array")
            for item in value:
                validate(array[1], item, depth + 1)
        elif kind in types:
            fields = types[kind]
            if not isinstance(value, dict) or set(value) != {f["name"] for f in fields}:
                raise ValueError("EIP712 struct fields mismatch")
            for field in fields:
                validate(field["type"], value[field["name"]], depth + 1)
        elif kind == "address":
            # Zero is a meaningful value in vendor orders (e.g. "receiver = owner"); semantic
            # checks belong to the vendor verifier, not to this structural pass.
            if value != "0x" + "0" * 40:
                address(value)
        elif kind == "bool":
            if type(value) is not bool:
                raise ValueError("Invalid EIP712 bool")
        elif kind == "string":
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError("Invalid EIP712 string")
        elif kind.startswith("bytes"):
            if value != "0x":
                hex_data(value)
            size = kind[5:]
            if size and (
                not size.isdigit() or not 1 <= int(size) <= 32 or len(value) != 2 + int(size) * 2
            ):
                raise ValueError("Invalid EIP712 bytes width")
        else:
            number = re.fullmatch(r"(u?int)([0-9]+)", kind)
            if not number or int(number[2]) not in range(8, 257, 8):
                raise ValueError("Unsupported EIP712 type")
            if type(value) is not int and not (
                isinstance(value, str) and re.fullmatch(r"-?(0|[1-9][0-9]{0,77})", value)
            ):
                raise ValueError("Invalid EIP712 integer")
            integer = int(value)
            bits = int(number[2])
            minimum = 0 if number[1] == "uint" else -(2 ** (bits - 1))
            maximum = 2**bits - 1 if number[1] == "uint" else 2 ** (bits - 1) - 1
            if not minimum <= integer <= maximum:
                raise ValueError("EIP712 integer overflow")

    validate(typed["primaryType"], typed["message"])
    if "EIP712Domain" in types:
        validate("EIP712Domain", domain)
