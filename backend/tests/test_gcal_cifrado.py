"""C-10 (3.3): cifrado de tokens en reposo (O1). Tokens sintéticos (R19)."""

import pytest
from cryptography.fernet import Fernet

from app.integraciones.gcal.cifrado import TokenIlegible, cifrar, descifrar

CLAVE = Fernet.generate_key().decode()


def test_ida_y_vuelta_y_el_cifrado_no_contiene_el_token() -> None:
    cifrado = cifrar("token-sintetico-001", CLAVE)
    assert cifrado != "token-sintetico-001" and "token-sintetico-001" not in cifrado
    assert descifrar(cifrado, CLAVE) == "token-sintetico-001"


def test_dos_cifrados_del_mismo_texto_difieren() -> None:
    assert cifrar("token-sintetico-002", CLAVE) != cifrar("token-sintetico-002", CLAVE)


@pytest.mark.parametrize("cifrado_con", ["otra", "basura"])
def test_clave_equivocada_o_texto_corrupto_dan_token_ilegible_sin_el_token(cifrado_con: str) -> None:
    cifrado = cifrar("token-sintetico-003", Fernet.generate_key().decode()) if cifrado_con == "otra" else "no-es-fernet"
    with pytest.raises(TokenIlegible) as error:
        descifrar(cifrado, CLAVE)
    assert "token-sintetico-003" not in str(error.value)
