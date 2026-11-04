import { Suspense, use, useEffect, useRef, useState } from 'react';
import { obtenerDisponibilidad, reservarTurno } from '../lib/api';
import type { ErrorApi } from '../lib/errores';
import { diaClinica, etiquetaDiaLarga, horaClinica, hoyClinica, sumarDias } from '../lib/tiempo';
import type { Alternativa, Catalogo, ReservaCreada, Slot } from '../lib/tipos';
import { puedeAvanzar, validarNombre, validarTelefono, type Paso } from '../lib/validacion';
import { Cargando } from './Cargando';
import { Confirmacion } from './Confirmacion';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';
import { PasoContacto } from './PasoContacto';
import { PasoHorario } from './PasoHorario';
import { PasoTratamiento } from './PasoTratamiento';
import { Progreso } from './Progreso';

const DIAS_DE_BUSQUEDA = 14;

const TITULOS: Readonly<Record<Paso, string>> = {
  1: '¿Qué tratamiento necesitás?',
  2: 'Elegí día y horario',
  3: 'Confirmá tus datos',
};

interface Props {
  readonly catalogo: Promise<Catalogo>;
  readonly onNueva: () => void;
}

export function Reserva({ catalogo: promesa, onNueva }: Props) {
  const catalogo = use(promesa);
  const [paso, setPaso] = useState<Paso>(1);
  const [tratamientoId, setTratamientoId] = useState<number | null>(null);
  const [profesionalElegido, setProfesionalElegido] = useState<number | null>(null);
  const [slots, setSlots] = useState<Promise<Slot[]> | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [nombre, setNombre] = useState('');
  const [telefono, setTelefono] = useState('');
  const [intentado, setIntentado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorApi | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [reserva, setReserva] = useState<ReservaCreada | null>(null);
  const titulo = useRef<HTMLHeadingElement>(null);

  // Con un único profesional no hay nada que elegir: se deriva, no se guarda.
  const profesionalId =
    profesionalElegido ?? (catalogo.profesionales.length === 1 ? (catalogo.profesionales[0]?.id ?? null) : null);
  const tratamiento = catalogo.tratamientos.find((t) => t.id === tratamientoId);
  const profesional = catalogo.profesionales.find((p) => p.id === profesionalId);
  const estado = { tratamientoId, profesionalId, slot, nombre, telefono };

  useEffect(() => {
    titulo.current?.focus();
  }, [paso]);

  function pedirHorarios(): void {
    if (tratamientoId === null || profesionalId === null) return;
    const hoy = hoyClinica(new Date());
    setSlots(
      obtenerDisponibilidad({
        profesionalId,
        tratamientoId,
        desde: hoy,
        hasta: sumarDias(hoy, DIAS_DE_BUSQUEDA),
      }),
    );
  }

  function irAHorarios(): void {
    setSlot(null);
    pedirHorarios();
    setPaso(2);
  }

  function elegirOtroHorario(): void {
    setError(null);
    setAviso(null);
    irAHorarios();
  }

  function cambiarCampo(poner: () => void): void {
    poner();
    if (error?.tipo === 'validacion') setError(null);
  }

  function elegirAlternativa(a: Alternativa): void {
    if (profesionalId === null) return;
    setSlot({ inicio: a.inicio, fin: a.fin, profesional_id: profesionalId, sillon_id: a.sillon_id });
    setError(null);
    setAviso(`Cambiamos tu horario al ${etiquetaDiaLarga(diaClinica(a.inicio))} a las ${horaClinica(a.inicio)}. Confirmá para reservarlo.`);
  }

  async function enviar(): Promise<void> {
    if (enviando || slot === null || tratamientoId === null || profesionalId === null) return;
    setIntentado(true);
    setAviso(null);
    if (validarNombre(nombre) !== null || validarTelefono(telefono) !== null) return;
    setEnviando(true);
    setError(null);
    const resultado = await reservarTurno({
      nombre,
      telefono,
      tratamiento_id: tratamientoId,
      profesional_id: profesionalId,
      inicio: slot.inicio,
    });
    setEnviando(false);
    if (resultado.ok) {
      setReserva(resultado.reserva);
      return;
    }
    setError(resultado.error);
    // El horario ocupado ya no sirve: se refresca la grilla para cuando vuelva a elegir.
    if (resultado.error.tipo === 'conflicto') pedirHorarios();
  }

  if (reserva && tratamiento && profesional) {
    return <Confirmacion reserva={reserva} tratamiento={tratamiento} profesional={profesional} onNueva={onNueva} />;
  }

  return (
    <>
      <Progreso actual={paso} />
      <h2 className="titulo-paso" ref={titulo} tabIndex={-1}>
        {TITULOS[paso]}
      </h2>

      {paso === 1 && (
        <PasoTratamiento
          catalogo={catalogo}
          tratamientoId={tratamientoId}
          profesionalId={profesionalId}
          onTratamiento={setTratamientoId}
          onProfesional={setProfesionalElegido}
          onContinuar={irAHorarios}
          puedeContinuar={puedeAvanzar(1, estado)}
        />
      )}

      {paso === 2 && slots && (
        <ErrorBoundary
          onReintentar={pedirHorarios}
          fallback={(reintentar) => (
            <ErrorCarga mensaje="No pudimos cargar los horarios. Revisá tu conexión e intentá de nuevo." onReintentar={reintentar} />
          )}
        >
          <Suspense fallback={<Cargando texto="Buscando horarios libres…" />}>
            <PasoHorario
              slots={slots}
              elegido={slot}
              onElegir={setSlot}
              onContinuar={() => {
                setPaso(3);
              }}
              onVolver={() => {
                setPaso(1);
              }}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {paso === 3 && slot && tratamiento && profesional && (
        <PasoContacto
          tratamiento={tratamiento}
          profesional={profesional}
          slot={slot}
          nombre={nombre}
          telefono={telefono}
          intentado={intentado}
          enviando={enviando}
          error={error}
          aviso={aviso}
          onNombre={(v) => {
            cambiarCampo(() => {
              setNombre(v);
            });
          }}
          onTelefono={(v) => {
            cambiarCampo(() => {
              setTelefono(v);
            });
          }}
          onEnviar={() => {
            void enviar();
          }}
          onVolver={() => {
            setError(null);
            setAviso(null);
            setPaso(2);
          }}
          onOtroHorario={elegirOtroHorario}
          onAlternativa={elegirAlternativa}
        />
      )}
    </>
  );
}
