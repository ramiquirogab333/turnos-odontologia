"""C-15 (3.1): vencimientos y claims de los tokens de una sesión (unit, sin base). Datos sintéticos (R19)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.auth.service import create_access_token, decode_token
from app.auth.sesiones import calcular_vencimientos, emitir_tokens
from app.shared.settings import get_settings

AHORA = datetime.now(timezone.utc).replace(microsecond=0)


def _emitir(expira_en: datetime, **extra: object):
    return emitir_tokens(sid=uuid4(), usuario_id=7, email="recepcion@turnos.test", roles=["recepcion"], ahora=AHORA,
                         expira_en=expira_en, access_minutos=15, refresh_minutos=10080, **extra)  # type: ignore[arg-type]


def test_lejos_del_tope_rigen_las_duraciones_normales() -> None:
    v = calcular_vencimientos(AHORA, AHORA + timedelta(hours=12), access_minutos=15, refresh_minutos=10080)
    assert v.access == AHORA + timedelta(minutes=15)
    assert v.refresh == AHORA + timedelta(hours=12)  # 7 días > tope de 12 h: manda el tope


def test_cerca_del_tope_ambos_vencen_a_lo_sumo_en_el_tope() -> None:
    tope = AHORA + timedelta(minutes=10)
    v = calcular_vencimientos(AHORA, tope, access_minutos=15, refresh_minutos=10080)
    assert v.access == tope and v.refresh == tope


def test_refresh_corto_gana_al_tope_lejano() -> None:
    v = calcular_vencimientos(AHORA, AHORA + timedelta(days=30), access_minutos=15, refresh_minutos=60)
    assert v.refresh == AHORA + timedelta(minutes=60)


def test_access_y_refresh_tienen_jti_distintos_y_el_mismo_sid() -> None:
    tokens = _emitir(AHORA + timedelta(hours=12))
    acceso, refresco = decode_token_sin_tiempo(tokens.access_token), decode_token_sin_tiempo(tokens.refresh_token)
    assert acceso["jti"] != refresco["jti"]
    assert acceso["sid"] == refresco["sid"]
    assert acceso["type"] == "access" and refresco["type"] == "refresh"
    assert refresco["jti"] == str(tokens.refresh_jti)


def test_los_vencimientos_firmados_respetan_el_tope() -> None:
    tope = AHORA + timedelta(minutes=5)
    tokens = _emitir(tope)
    assert decode_token_sin_tiempo(tokens.access_token)["exp"] == int(tope.timestamp())
    assert decode_token_sin_tiempo(tokens.refresh_token)["exp"] == int(tope.timestamp())
    assert tokens.refresh_expira_en == tope


def test_decode_token_exige_sid() -> None:
    sin_sid = create_access_token({"sub": "1", "roles": [], "email": "a@turnos.test", "jti": str(uuid4())})
    with pytest.raises(jwt.InvalidTokenError, match="sid"):
        decode_token(sin_sid)
    con_sid = create_access_token({"sub": "1", "roles": [], "email": "a@turnos.test", "jti": str(uuid4()),
                                   "sid": str(uuid4())})
    assert decode_token(con_sid)["sub"] == "1"


def decode_token_sin_tiempo(token: str) -> dict[str, object]:
    ajustes = get_settings()
    return jwt.decode(token, ajustes.jwt_secret_key, algorithms=[ajustes.jwt_algorithm],
                      options={"verify_exp": False, "verify_iat": False})
