"""Proveedor de calendario en memoria para pytest (C-10, D1, O15). Imita el subconjunto de Google que usa el sistema.

Registra las llamadas (``llamadas``) para verificar que la API no llama a Google, y permite simular lo que hace la
profesional en su calendario (``crear_ocupado``, ``mover``, ``borrar_externo``, ``editar_titulo``) y las fallas de
Google (``fallar``, ``revocar_acceso``, ``invalidar_sync_tokens``).
"""

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.integraciones.gcal.contenido import ContenidoEvento
from app.integraciones.gcal.proveedor import (AccesoRevocado, CambiosGoogle, ErrorAutorizacion, ErrorProveedor,
                                              EtagDesactualizado, EventoDuplicado, EventoGoogle, EventoInexistente,
                                              SyncTokenVencido, TokensGoogle)


@dataclass
class _Registro:
    id: str
    estado: str
    inicio: datetime
    fin: datetime
    ocupa: bool
    etag: str
    propias: dict[str, str]
    titulo: str = ""
    descripcion: str = ""
    contenido: ContenidoEvento | None = None


@dataclass
class ProveedorFalso:
    email_cuenta: str = "ana.prueba@example.com"
    eventos: dict[tuple[str, str], _Registro] = field(default_factory=dict)
    llamadas: list[str] = field(default_factory=list)
    _fallas: list[tuple[ErrorProveedor, tuple[str, ...] | None]] = field(default_factory=list)
    _cambios: list[tuple[str, str]] = field(default_factory=list)
    _acceso_revocado: bool = False
    _epoca: int = 0
    _version: itertools.count = field(default_factory=lambda: itertools.count(1))
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    # --- simulación de lo que pasa en Google ----------------------------------------------------------------
    def fallar(self, error: ErrorProveedor, veces: int = 1, *, en: tuple[str, ...] | None = None) -> None:
        """Las próximas ``veces`` llamadas a la API (no al token) lanzan ``error``; ``en`` limita a esos métodos."""
        self._fallas.extend([(error, en)] * veces)

    def revocar_acceso(self) -> None:
        self._acceso_revocado = True

    def invalidar_sync_tokens(self) -> None:
        self._epoca += 1

    def crear_ocupado(self, inicio: datetime, fin: datetime, *, ocupa: bool = True, calendario: str = "primary",
                      evento_id: str | None = None, titulo: str = "Evento sintético") -> str:
        evento_id = evento_id or f"ajeno{next(self._ids):04d}"
        self._poner(calendario, _Registro(evento_id, "confirmed", inicio, fin, ocupa, self._etag(), {}, titulo))
        return evento_id

    def mover(self, evento_id: str, inicio: datetime, fin: datetime, calendario: str = "primary") -> None:
        registro = self.eventos[(calendario, evento_id)]
        registro.inicio, registro.fin = inicio, fin
        self._poner(calendario, registro)

    def borrar_externo(self, evento_id: str, calendario: str = "primary") -> None:
        registro = self.eventos[(calendario, evento_id)]
        registro.estado, registro.ocupa = "cancelled", False
        self._poner(calendario, registro)

    def editar_titulo(self, evento_id: str, titulo: str, calendario: str = "primary") -> None:
        registro = self.eventos[(calendario, evento_id)]
        registro.titulo = titulo
        self._poner(calendario, registro)

    def vigentes(self, calendario: str = "primary") -> list[_Registro]:
        return [r for (c, _), r in self.eventos.items() if c == calendario and r.estado != "cancelled"]

    def _etag(self) -> str:
        return f"\"etag-{next(self._version)}\""

    def _poner(self, calendario: str, registro: _Registro) -> None:
        registro.etag = self._etag()
        self.eventos[(calendario, registro.id)] = registro
        self._cambios.append((calendario, registro.id))

    def _preparar(self, nombre: str) -> None:
        self.llamadas.append(nombre)
        for posicion, (error, metodos) in enumerate(self._fallas):
            if metodos is None or nombre in metodos:
                del self._fallas[posicion]
                raise error

    @staticmethod
    def _vista(r: _Registro) -> EventoGoogle:
        return EventoGoogle(id=r.id, estado=r.estado, inicio=r.inicio, fin=r.fin, ocupa=r.ocupa and r.estado != "cancelled",
                            etag=r.etag, propias=dict(r.propias))

    # --- puerto ------------------------------------------------------------------------------------------------
    async def canjear_codigo(self, codigo: str, verificador: str, redirect_uri: str) -> TokensGoogle:
        self.llamadas.append("canjear_codigo")
        if codigo == "codigo-invalido":
            raise ErrorAutorizacion()
        return TokensGoogle(access_token="token-sintetico-canje", refresh_token="refresh-sintetico-canje",
                            expira_en=datetime.now(timezone.utc) + timedelta(hours=1), email=self.email_cuenta)

    async def renovar_token(self, refresh_token: str) -> TokensGoogle:
        self.llamadas.append("renovar_token")
        if self._acceso_revocado:
            raise AccesoRevocado()
        return TokensGoogle(access_token="token-sintetico-renovado", expira_en=datetime.now(timezone.utc) + timedelta(hours=1))

    async def revocar(self, token: str) -> None:
        self.llamadas.append("revocar")

    async def insertar(self, acceso: str, calendario_id: str, evento_id: str,
                       contenido: ContenidoEvento) -> EventoGoogle:
        self._preparar("insertar")
        if (calendario_id, evento_id) in self.eventos:
            raise EventoDuplicado()
        registro = _Registro(evento_id, "confirmed", contenido.inicio, contenido.fin, True, "",
                             dict(contenido.propiedades_privadas), contenido.titulo, contenido.descripcion, contenido)
        self._poner(calendario_id, registro)
        return self._vista(registro)

    async def actualizar(self, acceso: str, calendario_id: str, evento_id: str, contenido: ContenidoEvento,
                         etag: str) -> EventoGoogle:
        self._preparar("actualizar")
        registro = self.eventos.get((calendario_id, evento_id))
        if registro is None or registro.estado == "cancelled":
            raise EventoInexistente()
        if registro.etag != etag:
            raise EtagDesactualizado()
        registro.inicio, registro.fin = contenido.inicio, contenido.fin
        registro.titulo, registro.descripcion, registro.contenido = contenido.titulo, contenido.descripcion, contenido
        self._poner(calendario_id, registro)
        return self._vista(registro)

    async def borrar(self, acceso: str, calendario_id: str, evento_id: str) -> None:
        self._preparar("borrar")
        registro = self.eventos.get((calendario_id, evento_id))
        if registro is None or registro.estado == "cancelled":
            raise EventoInexistente()
        registro.estado, registro.ocupa = "cancelled", False
        self._poner(calendario_id, registro)

    async def obtener(self, acceso: str, calendario_id: str, evento_id: str) -> EventoGoogle | None:
        self._preparar("obtener")
        registro = self.eventos.get((calendario_id, evento_id))
        return None if registro is None else self._vista(registro)

    async def listar(self, acceso: str, calendario_id: str, sync_token: str | None, desde: datetime | None,
                     hasta: datetime | None) -> CambiosGoogle:
        self._preparar("listar")
        token_nuevo = f"sync-{self._epoca}-{len(self._cambios)}"
        if sync_token is None:
            visibles = [r for (c, _), r in self.eventos.items() if c == calendario_id
                        and (desde is None or hasta is None or (r.inicio < hasta and r.fin > desde))]
            return CambiosGoogle([self._vista(r) for r in visibles], token_nuevo)
        epoca, _, posicion = sync_token.removeprefix("sync-").partition("-")
        if epoca != str(self._epoca) or not posicion.isdigit():
            raise SyncTokenVencido()
        vistos: dict[str, _Registro] = {}
        for c, evento_id in self._cambios[int(posicion):]:
            if c == calendario_id:
                vistos[evento_id] = self.eventos[(c, evento_id)]
        return CambiosGoogle([self._vista(r) for r in vistos.values()], token_nuevo)
