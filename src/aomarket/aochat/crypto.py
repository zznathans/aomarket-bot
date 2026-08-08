"""AO chat login key derivation and login-blob encryption.

This is a 'half' Diffie-Hellman key exchange (the client already has the
server's public key dhY; dhN is a prime, dhG is a generator for it)
followed by a TEA-family block cipher that encrypts the login blob (random
prefix + big-endian length + the "username|serverseed|password" string +
space padding) under the derived shared secret.

Python's builtin pow(base, exp, mod) handles the modular exponentiation
natively -- no bignum library needed.

Byte order note: this assumes a little-endian host (x86_64).
"""

import secrets
import struct

MASK32 = 0xFFFFFFFF
TEA_DELTA = 0x9E3779B9
TEA_ROUNDS = 32

# Protocol constants (not secrets -- dhY is the AO chat server's public DH
# key, dhN/dhG are the fixed prime/generator).
DH_Y = int(
    "9c32cc23d559ca90fc31be72df817d0e124769e809f936bc14360ff4bed758f260a0d596584eacbbc2b88bdd410416"
    "163e11dbf62173393fbc0c6fefb2d855f1a03dec8e9f105bbad91b3437d8eb73fe2f44159597aa4053cf788d2f9d7012"
    "fb8d7c4ce3876f7d6cd5d0c31754f4cd96166708641958de54a6def5657b9f2e92",
    16,
)
DH_N = int(
    "eca2e8c85d863dcdc26a429a71a9815ad052f6139669dd659f98ae159d313d13c6bf2838e10a69b6478b64a24bd054b"
    "a8248e8fa778703b418408249440b2c1edd28853e240d8a7e49540b76d120d3b1ad2878b1b99490eb4a2a5e84caa8a91"
    "cecbdb1aa7c816e8be343246f80c637abc653b893fd91686cf8d32d6cfe5f2a6f",
    16,
)
DH_G = 5


def _permute(a: int, b: int, key_words: tuple[int, int, int, int]) -> tuple[int, int]:
    """TEA-family block permutation round function.

    All arithmetic kept in unsigned 32-bit space throughout (+, ^, <<, and
    the explicitly-masked >> used here).
    """
    k1, k2, k3, k4 = key_words
    c = 0
    for _ in range(TEA_ROUNDS):
        c = (c + TEA_DELTA) & MASK32
        term1 = (((b << 4) & MASK32 & 0xFFFFFFF0) + k1) & MASK32
        term1 ^= (b + c) & MASK32
        term2 = (((b >> 5) & 0x07FFFFFF) + k2) & MASK32
        a = (a + (term1 ^ term2)) & MASK32

        term3 = (((a << 4) & MASK32 & 0xFFFFFFF0) + k3) & MASK32
        term3 ^= (a + c) & MASK32
        term4 = (((a >> 5) & 0x07FFFFFF) + k4) & MASK32
        b = (b + (term3 ^ term4)) & MASK32
    return a, b


def aochat_crypt(key_hex: str, plain: bytes) -> str:
    """Encrypts the login blob under the derived shared secret.

    `key_hex` must be exactly 32 hex chars (16 bytes); `plain` must be a
    multiple of 8 bytes. Returns the ciphertext as a lowercase hex string
    (this is embedded directly into the login packet's key argument, not
    sent as raw bytes).
    """
    if len(key_hex) != 32:
        raise ValueError("key_hex must be exactly 32 hex characters (16 bytes)")
    if len(plain) % 8 != 0:
        raise ValueError("plain must be a multiple of 8 bytes")

    key_words = struct.unpack("<4I", bytes.fromhex(key_hex))
    data_words = struct.unpack(f"<{len(plain) // 4}I", plain)

    prev0, prev1 = 0, 0
    out_hex = []
    for i in range(0, len(data_words), 2):
        now0 = data_words[i] ^ prev0
        now1 = data_words[i + 1] ^ prev1
        prev0, prev1 = _permute(now0, now1, key_words)
        out_hex.append(struct.pack("<I", prev0).hex())
        out_hex.append(struct.pack("<I", prev1).hex())
    return "".join(out_hex)


def generate_login_key(server_seed: bytes, username: str, password: str) -> str:
    """Derives the login key from the server seed and account credentials.

    Returns "<dhX-hex>-<encrypted-blob-hex>", sent as the AOCP_LOGIN_REQUEST
    packet's key argument.
    """
    dh_x = secrets.randbits(256)
    dh_capital_x = pow(DH_G, dh_x, DH_N)
    dh_k = pow(DH_Y, dh_x, DH_N)

    dh_k_hex = format(dh_k, "x")
    if len(dh_k_hex) < 32:
        dh_k_hex = dh_k_hex.zfill(32)
    else:
        dh_k_hex = dh_k_hex[:32]

    login_str = username.encode() + b"|" + server_seed + b"|" + password.encode()
    prefix = secrets.token_bytes(8)
    length = 8 + 4 + len(login_str)
    pad = b" " * ((8 - length % 8) % 8)
    plain = prefix + struct.pack(">I", len(login_str)) + login_str + pad

    crypted = aochat_crypt(dh_k_hex, plain)
    return f"{format(dh_capital_x, 'x')}-{crypted}"
