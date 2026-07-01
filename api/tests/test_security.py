from app.security import generate_extension_token, hash_token, verify_token


def test_token_roundtrip():
    tok = generate_extension_token()
    assert tok.startswith("chr_")
    h = hash_token(tok)
    assert h != tok  # stored form is the hash, not the plaintext
    assert len(h) == 64  # sha256 hex
    assert verify_token(tok, h)


def test_wrong_token_rejected():
    h = hash_token(generate_extension_token())
    assert not verify_token(generate_extension_token(), h)


def test_empty_inputs_rejected():
    assert not verify_token("", hash_token("x"))
    assert not verify_token("x", None)


def test_tokens_are_unique():
    assert generate_extension_token() != generate_extension_token()
