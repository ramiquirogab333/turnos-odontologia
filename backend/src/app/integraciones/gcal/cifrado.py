"""Cifrado de los tokens de Google en reposo (C-10, O1): Fernet con la clave ``GCAL_TOKEN_CLAVE`` del entorno.

Nunca se loguea ni se incluye un token en un mensaje de error: el error ``TokenIlegible`` no lleva el texto.
"""

from cryptography.fernet import Fernet, InvalidToken


class TokenIlegible(Exception):
    """El texto guardado no se pudo descifrar (clave rotada o dato corrupto). Sin el token en el mensaje."""

    def __init__(self) -> None:
        super().__init__("No se pudo descifrar un token guardado")


def cifrar(texto: str, clave: str) -> str:
    """Cifra ``texto`` con la clave Fernet; cada llamada produce un resultado distinto."""
    return Fernet(clave.encode()).encrypt(texto.encode()).decode()


def descifrar(cifrado: str, clave: str) -> str:
    """Descifra un texto producido por ``cifrar``; ``TokenIlegible`` si la clave no corresponde o está corrupto."""
    try:
        return Fernet(clave.encode()).decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        raise TokenIlegible() from None
