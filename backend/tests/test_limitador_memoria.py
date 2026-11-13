"""C-15 (6.1/6.2, D5/O9): limitador de ventana fija en memoria con reloj inyectado (sin dormir)."""

import json

import pytest
from pydantic import ValidationError

from app.shared.limites import (
    LimiteSuperadoOut,
    LimitadorEnMemoria,
    clave_email,
    respuesta_limite_superado,
)


class Reloj:
    """Reloj monótono falso: el test lo avanza a mano."""

    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def limitador(reloj: Reloj) -> LimitadorEnMemoria:
    return LimitadorEnMemoria(reloj=reloj)


async def test_permite_hasta_el_maximo_y_rechaza_el_siguiente(limitador: LimitadorEnMemoria) -> None:
    for _ in range(5):
        assert (await limitador.consumir("rl:v1:t", 5, 900)).permitido
    rechazado = await limitador.consumir("rl:v1:t", 5, 900)
    assert not rechazado.permitido
    assert rechazado.reintentar_en_segundos == 900


async def test_retry_after_baja_con_el_reloj_y_nunca_baja_de_uno(limitador: LimitadorEnMemoria, reloj: Reloj) -> None:
    await limitador.consumir("rl:v1:t", 1, 600)
    reloj.ahora += 100
    assert (await limitador.consumir("rl:v1:t", 1, 600)).reintentar_en_segundos == 500
    reloj.ahora += 499.5  # quedan 0,5 s: se redondea hacia arriba, nunca 0
    assert (await limitador.consumir("rl:v1:t", 1, 600)).reintentar_en_segundos == 1


async def test_en_el_ultimo_segundo_retry_after_es_uno(limitador: LimitadorEnMemoria, reloj: Reloj) -> None:
    await limitador.consumir("rl:v1:t", 1, 60)
    reloj.ahora += 59
    resultado = await limitador.consumir("rl:v1:t", 1, 60)
    assert (resultado.permitido, resultado.reintentar_en_segundos) == (False, 1)


async def test_ventana_vencida_vuelve_a_permitir_y_empieza_otra(limitador: LimitadorEnMemoria, reloj: Reloj) -> None:
    await limitador.consumir("rl:v1:t", 1, 60)
    assert not (await limitador.consumir("rl:v1:t", 1, 60)).permitido
    reloj.ahora += 60  # la ventana vence exactamente a los 60 s
    assert (await limitador.consumir("rl:v1:t", 1, 60)).permitido
    assert not (await limitador.consumir("rl:v1:t", 1, 60)).permitido


async def test_las_claves_son_independientes(limitador: LimitadorEnMemoria) -> None:
    await limitador.consumir("rl:v1:a", 1, 60)
    assert not (await limitador.consumir("rl:v1:a", 1, 60)).permitido
    assert (await limitador.consumir("rl:v1:b", 1, 60)).permitido


async def test_reiniciar_borra_el_contador_y_es_idempotente(limitador: LimitadorEnMemoria) -> None:
    await limitador.consumir("rl:v1:t", 1, 60)
    assert not (await limitador.consumir("rl:v1:t", 1, 60)).permitido
    await limitador.reiniciar("rl:v1:t")
    await limitador.reiniciar("rl:v1:t")
    await limitador.reiniciar("rl:v1:inexistente")
    assert (await limitador.consumir("rl:v1:t", 1, 60)).permitido


async def test_la_transicion_a_rechazado_se_informa_una_sola_vez(limitador: LimitadorEnMemoria) -> None:
    informes = [(await limitador.consumir("rl:v1:t", 3, 60)).recien_bloqueado for _ in range(33)]
    assert informes.count(True) == 1
    assert informes.index(True) == 3  # el cuarto pedido es el primero rechazado


async def test_tras_la_ventana_la_transicion_vuelve_a_informarse(limitador: LimitadorEnMemoria, reloj: Reloj) -> None:
    for _ in range(3):
        await limitador.consumir("rl:v1:t", 1, 60)
    reloj.ahora += 60
    informes = [(await limitador.consumir("rl:v1:t", 1, 60)).recien_bloqueado for _ in range(3)]
    assert informes == [False, True, False]


async def test_consultar_no_incrementa_y_bloquea_cuando_el_contador_llego_al_maximo(limitador: LimitadorEnMemoria) -> None:
    assert (await limitador.consultar("rl:v1:f", 2)).permitido
    await limitador.registrar("rl:v1:f", 900)
    assert (await limitador.consultar("rl:v1:f", 2)).permitido
    await limitador.registrar("rl:v1:f", 900)
    bloqueado = await limitador.consultar("rl:v1:f", 2)
    assert (bloqueado.permitido, bloqueado.reintentar_en_segundos) == (False, 900)
    # Consultar no suma: reiniciar y volver a consultar demuestra que el contador seguía en 2.
    await limitador.reiniciar("rl:v1:f")
    assert (await limitador.consultar("rl:v1:f", 2)).permitido


async def test_consultar_informa_la_transicion_una_sola_vez(limitador: LimitadorEnMemoria) -> None:
    await limitador.registrar("rl:v1:f", 900)
    informes = [(await limitador.consultar("rl:v1:f", 1)).recien_bloqueado for _ in range(30)]
    assert informes.count(True) == 1 and informes[0] is True


def test_la_clave_de_email_no_lleva_el_email_en_claro_y_normaliza() -> None:
    a = clave_email("Recepcion@Turnos.test")
    assert a == clave_email("  recepcion@turnos.test ")
    assert "recepcion" not in a and "turnos.test" not in a
    assert a != clave_email("otra@turnos.test")


def test_respuesta_429_usa_el_esquema_y_retry_after() -> None:
    respuesta = respuesta_limite_superado(300)
    assert respuesta.status_code == 429
    assert respuesta.headers["Retry-After"] == "300"
    cuerpo = json.loads(bytes(respuesta.body))
    assert cuerpo == {"detail": "Demasiados intentos. Probá de nuevo más tarde.", "motivo": "demasiados_intentos"}
    assert LimiteSuperadoOut.model_validate(cuerpo).motivo == "demasiados_intentos"


@pytest.mark.parametrize("segundos", [0, -3])
def test_respuesta_429_nunca_informa_menos_de_un_segundo(segundos: int) -> None:
    assert respuesta_limite_superado(segundos).headers["Retry-After"] == "1"


def test_el_esquema_del_429_rechaza_campos_extra_o_motivos_distintos() -> None:
    with pytest.raises(ValidationError):
        LimiteSuperadoOut.model_validate({"detail": "x", "motivo": "demasiados_intentos", "email": "a@turnos.test"})
    with pytest.raises(ValidationError):
        LimiteSuperadoOut.model_validate({"detail": "x", "motivo": "otro"})
