"""C-11 (2.2): catálogo FDI y estado vigente del odontograma, puros, sin base. Datos sintéticos (R19)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.clinica.odontograma import PIEZAS_FDI, RegistroOdonto, registro_valido, vigente

T0 = datetime(2031, 3, 3, 12, 0, tzinfo=timezone.utc)


def test_hay_52_piezas_validas() -> None:
    assert len(PIEZAS_FDI) == 52
    assert len(set(PIEZAS_FDI)) == 52


@pytest.mark.parametrize("pieza,valida", [
    (11, True), (18, True), (19, False), (10, False), (21, True), (48, True), (49, False), (50, False),
    (51, True), (55, True), (56, False), (85, True), (86, False), (0, False), (99, False)])
def test_bordes_de_piezas(pieza: int, valida: bool) -> None:
    assert (pieza in PIEZAS_FDI) is valida
    assert registro_valido(pieza, None, "sano") is valida


@pytest.mark.parametrize("estado,cara,valido", [
    ("caries", "O", True), ("caries", None, False), ("obturado", "M", True), ("obturado", None, False),
    ("corona", None, True), ("corona", "O", False), ("ausente", None, True), ("ausente", "D", False),
    ("extraccion_indicada", None, True), ("endodoncia", "V", False), ("implante", None, True),
    ("sano", None, True), ("sano", "L", True), ("caries", "X", False), ("inexistente", None, False)])
def test_coherencia_cara_estado(estado: str, cara: str | None, valido: bool) -> None:
    assert registro_valido(16, cara, estado) is valido


def _r(id_: int, pieza: int, cara: str | None, estado: str, dias: int = 0) -> RegistroOdonto:
    return RegistroOdonto(id=id_, pieza=pieza, cara=cara, estado=estado, registrado_en=T0 + timedelta(days=dias))


def test_caries_luego_obturado_en_la_misma_cara() -> None:
    v = vigente([_r(1, 16, "O", "caries", 0), _r(2, 16, "O", "obturado", 1)])
    assert v[16].caras == {"O": "obturado"}
    assert v[16].estado_pieza is None
    assert list(v) == [16]


def test_sano_de_cara_limpia_solo_esa_cara() -> None:
    v = vigente([_r(1, 16, "O", "caries"), _r(2, 16, "M", "caries"), _r(3, 16, "O", "sano", 1)])
    assert v[16].caras == {"M": "caries"}


def test_sano_de_pieza_limpia_caras_anteriores_y_el_estado_de_pieza() -> None:
    v = vigente([_r(1, 26, None, "endodoncia"), _r(2, 26, "M", "caries"), _r(3, 26, None, "sano", 1)])
    assert 26 not in v


def test_hallazgo_posterior_al_sano_de_pieza_si_cuenta() -> None:
    v = vigente([_r(1, 26, "M", "caries"), _r(2, 26, None, "sano", 1), _r(3, 26, "D", "obturado", 2)])
    assert v[26].caras == {"D": "obturado"}


def test_estado_de_pieza_reemplaza_al_anterior() -> None:
    v = vigente([_r(1, 36, None, "ausente"), _r(2, 36, None, "implante", 1)])
    assert v[36].estado_pieza == "implante"


def test_igual_fecha_desempata_por_id_mayor_aunque_llegue_desordenado() -> None:
    v = vigente([_r(9, 46, "O", "obturado"), _r(5, 46, "O", "caries")])
    assert v[46].caras == {"O": "obturado"}


def test_sin_registros_no_hay_piezas() -> None:
    assert vigente([]) == {}


def test_piezas_distintas_no_se_pisan() -> None:
    v = vigente([_r(1, 16, "O", "caries"), _r(2, 17, None, "ausente")])
    assert set(v) == {16, 17}
