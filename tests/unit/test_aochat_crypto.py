import pytest

from aomarket.aochat import crypto


def test_aochat_crypt_rejects_wrong_key_length():
    with pytest.raises(ValueError):
        crypto.aochat_crypt("deadbeef", b"12345678")


def test_aochat_crypt_rejects_non_multiple_of_8_plaintext():
    with pytest.raises(ValueError):
        crypto.aochat_crypt("0" * 32, b"1234567")


def test_aochat_crypt_is_deterministic_for_fixed_inputs():
    key = "00112233445566778899aabbccddeeff"[:32]
    plain = b"abcdefgh" * 3

    first = crypto.aochat_crypt(key, plain)
    second = crypto.aochat_crypt(key, plain)

    assert first == second
    assert len(first) == len(plain) * 2  # 2 hex chars per byte


def test_aochat_crypt_output_changes_with_plaintext():
    key = "0" * 32
    out_a = crypto.aochat_crypt(key, b"abcdefgh")
    out_b = crypto.aochat_crypt(key, b"abcdefgi")

    assert out_a != out_b


def test_aochat_crypt_output_changes_with_key():
    plain = b"abcdefgh"
    out_a = crypto.aochat_crypt("0" * 32, plain)
    out_b = crypto.aochat_crypt("1" * 32, plain)

    assert out_a != out_b


def test_aochat_crypt_chains_blocks_not_ecb():
    # If the same 8-byte plaintext block repeats, the propagating-cipher
    # chaining (prev ciphertext feeds into the next block's XOR) must
    # produce *different* ciphertext for the second occurrence, unlike ECB.
    key = "0" * 32
    plain = b"repeated" + b"repeated"

    out = crypto.aochat_crypt(key, plain)
    first_block, second_block = out[:16], out[16:]

    assert first_block != second_block


def test_generate_login_key_shape():
    key = crypto.generate_login_key(b"someserverseed12", "myusername", "mypassword")

    assert "-" in key
    dh_x_hex, crypted_hex = key.split("-", 1)
    int(dh_x_hex, 16)  # must be valid hex
    int(crypted_hex, 16)  # must be valid hex
    assert len(crypted_hex) % 2 == 0


def test_generate_login_key_is_randomized_across_calls():
    key_a = crypto.generate_login_key(b"seed", "user", "pass")
    key_b = crypto.generate_login_key(b"seed", "user", "pass")

    assert key_a != key_b
