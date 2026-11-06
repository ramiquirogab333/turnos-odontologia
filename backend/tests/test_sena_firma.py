"""C-06 (3.1): verificación de la firma HMAC del webhook de Mercado Pago. Vectores sintéticos fijos."""

from datetime import datetime, timedelta, timezone

import pytest

from app.pagos.pasarela import calcular_firma, verificar_firma

SECRETO = "secreto-sintetico-de-prueba"
DATA_ID = "123456"
REQUEST_ID = "req-sintetico-0001"
TS_MS = "1742505638683"
# HMAC-SHA256 de "id:123456;request-id:req-sintetico-0001;ts:1742505638683;" con SECRETO.
FIRMA_FIJA = "8e7090735fd1e1371c8ba26db06cfb178db8af4abfe728efb868f22cc6c03103"
AHORA = datetime.fromtimestamp(int(TS_MS) / 1000, tz=timezone.utc)


def _ver(cabecera: str | None, *, secreto: str = SECRETO, ahora: datetime = AHORA, data_id: str = DATA_ID) -> bool:
    return verificar_firma(secreto=secreto, x_signature=cabecera, x_request_id=REQUEST_ID, data_id=data_id,
                           ahora=ahora, tolerancia_segundos=300)


def test_calcular_firma_coincide_con_el_vector_fijo() -> None:
    assert calcular_firma(SECRETO, DATA_ID, REQUEST_ID, TS_MS) == FIRMA_FIJA


def test_firma_valida() -> None:
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}") is True


def test_firma_valida_con_espacio_tras_la_coma() -> None:
    assert _ver(f"ts={TS_MS}, v1={FIRMA_FIJA}") is True


def test_otro_secreto_se_rechaza() -> None:
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", secreto="otro-secreto-sintetico") is False


def test_otro_data_id_se_rechaza() -> None:
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", data_id="654321") is False


@pytest.mark.parametrize("cabecera", [
    None, "", f"ts={TS_MS}", f"v1={FIRMA_FIJA}", "basura", f"ts={TS_MS},v1=", "ts=abc,v1=ff",
    f"ts={TS_MS},v1=zz{FIRMA_FIJA[2:]}",
])
def test_cabecera_ausente_o_malformada_se_rechaza(cabecera: str | None) -> None:
    assert _ver(cabecera) is False


def test_ts_dentro_de_la_tolerancia_de_300s() -> None:
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", ahora=AHORA) is True
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", ahora=AHORA + timedelta(seconds=300)) is True
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", ahora=AHORA - timedelta(seconds=299)) is True


def test_ts_fuera_de_la_tolerancia_se_rechaza_aunque_la_firma_sea_valida() -> None:
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", ahora=AHORA + timedelta(seconds=301)) is False
    assert _ver(f"ts={TS_MS},v1={FIRMA_FIJA}", ahora=AHORA - timedelta(seconds=301)) is False


def test_ts_en_segundos_tambien_se_acepta() -> None:
    ts_s = str(int(TS_MS) // 1000)
    firma = calcular_firma(SECRETO, DATA_ID, REQUEST_ID, ts_s)
    assert _ver(f"ts={ts_s},v1={firma}") is True
