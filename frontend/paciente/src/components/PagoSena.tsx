import { useEffect, useRef, useState } from 'react';
import { iniciarSena } from '../lib/api';
import { guardarPendiente } from '../lib/almacen';
import { montoExacto } from '../lib/formato';
import { diaClinica, etiquetaDiaLarga, horaClinica } from '../lib/tiempo';
import type { ErrorSena, InicioSena, MedioSena, Profesional, ReservaEnEspera, Tratamiento } from '../lib/tipos';
import { EsperaAcreditacion } from './EsperaAcreditacion';

interface Props {
  readonly reserva: ReservaEnEspera;
  readonly tratamiento: Tratamiento;
  readonly profesional: Profesional;
  readonly onNueva: () => void;
  /** Redirección al checkout; inyectable para probar sin navegar. */
  readonly irA?: (url: string) => void;
}

const ETIQUETA_MEDIO: Readonly<Record<MedioSena, string>> = {
  mercadopago: 'Pagar con Mercado Pago',
  transferencia: 'Pagar por transferencia',
};

function irAlCheckout(url: string): void {
  window.location.assign(url);
}

function BotonCopiar({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <>
      <button
        type="button"
        className="boton boton-secundario boton-copiar"
        aria-label={`Copiar ${etiqueta}`}
        onClick={() => {
          void navigator.clipboard.writeText(valor).then(
            () => {
              setCopiado(true);
            },
            () => {
              setCopiado(false);
            },
          );
        }}
      >
        Copiar
      </button>
      <span className="copiado" aria-live="polite">
        {copiado ? 'Copiado' : ''}
      </span>
    </>
  );
}

function Dato({
  nombre,
  valor,
  copiar,
  etiquetaCopia = nombre.toLowerCase(),
}: {
  readonly nombre: string;
  readonly valor: string;
  readonly copiar?: string;
  readonly etiquetaCopia?: string;
}) {
  return (
    <div className="dato">
      <div className="dato-texto">
        <span className="dato-nombre">{nombre}</span>
        <strong className="dato-valor">{valor}</strong>
      </div>
      {copiar !== undefined && <BotonCopiar etiqueta={etiquetaCopia} valor={copiar} />}
    </div>
  );
}

function DatosTransferencia({ sena }: { readonly sena: InicioSena }) {
  const vence = sena.vence_en;
  return (
    <>
      <h2 className="titulo-paso">Transferí la seña</h2>
      <section aria-label="Datos para transferir" className="datos-transferencia" role="region">
        <Dato nombre="Alias" valor={sena.alias ?? ''} copiar={sena.alias ?? ''} />
        <Dato nombre="CBU" valor={sena.cbu ?? ''} copiar={sena.cbu ?? ''} etiquetaCopia="CBU" />
        {sena.titular !== null && <Dato nombre="Titular" valor={sena.titular} />}
        <Dato nombre="Monto" valor={montoExacto(sena.monto)} copiar={sena.monto} />
        <Dato
          nombre="Código de referencia"
          valor={sena.referencia_concepto ?? ''}
          copiar={sena.referencia_concepto ?? ''}
        />
        <p className="nota">Poné este código en el concepto de la transferencia.</p>
      </section>
      {vence !== null && (
        <p className="nota">
          {`Tenés hasta el ${etiquetaDiaLarga(diaClinica(vence))} a las ${horaClinica(vence)} para transferir.`}
        </p>
      )}
      <p className="aviso aviso-ok">La clínica confirma tu turno al acreditar la transferencia.</p>
    </>
  );
}

function AvisoError({ error, onNueva }: { readonly error: ErrorSena; readonly onNueva: () => void }) {
  if (error.tipo === 'vencida' || error.tipo === 'horario_tomado') {
    const vencida = error.tipo === 'vencida';
    return (
      <section className="espera" aria-labelledby="titulo-error-sena">
        <h2 id="titulo-error-sena" tabIndex={-1}>
          {vencida ? 'La reserva venció' : 'El horario se ocupó'}
        </h2>
        <p>
          {vencida
            ? 'Pasó el tiempo para pagar la seña y liberamos el horario.'
            : 'Otra persona confirmó este horario antes que vos. No se te cobró nada.'}
        </p>
        <div className="acciones">
          <button type="button" className="boton boton-primario" onClick={onNueva}>
            Elegir otro horario
          </button>
        </div>
      </section>
    );
  }
  const mensaje =
    error.tipo === 'pasarela' || error.tipo === 'medio' || error.tipo === 'limite' || error.tipo === 'desconocido'
      ? error.mensaje
      : 'No encontramos tu reserva.';
  return (
    <div className="aviso aviso-error" role="alert">
      <p>{mensaje}</p>
    </div>
  );
}

export function PagoSena({ reserva, tratamiento, profesional, onNueva, irA = irAlCheckout }: Props) {
  const { sena } = reserva;
  const titulo = useRef<HTMLHeadingElement>(null);
  const [enCurso, setEnCurso] = useState<MedioSena | null>(null);
  const [error, setError] = useState<ErrorSena | null>(null);
  const [transferencia, setTransferencia] = useState<InicioSena | null>(null);

  useEffect(() => {
    titulo.current?.focus();
  }, []);

  async function elegir(medio: MedioSena): Promise<void> {
    if (enCurso !== null) return;
    setEnCurso(medio);
    setError(null);
    const r = await iniciarSena(reserva.turno_id, reserva.codigo_gestion, medio);
    setEnCurso(null);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    if (medio === 'mercadopago' && r.sena.checkout_url !== null) {
      guardarPendiente({ turnoId: reserva.turno_id, codigoGestion: reserva.codigo_gestion, venceEn: r.sena.vence_en ?? sena.vence_en });
      irA(r.sena.checkout_url);
      return;
    }
    setTransferencia(r.sena);
  }

  if (error !== null && (error.tipo === 'vencida' || error.tipo === 'horario_tomado')) {
    return <AvisoError error={error} onNueva={onNueva} />;
  }

  if (transferencia !== null) {
    return (
      <>
        <EsperaAcreditacion
          turnoId={reserva.turno_id}
          codigoGestion={reserva.codigo_gestion}
          onNueva={onNueva}
          encabezado={<DatosTransferencia sena={transferencia} />}
        />
        <div className="acciones">
          <button
            type="button"
            className="boton boton-texto"
            onClick={() => {
              setTransferencia(null);
            }}
          >
            Elegir otro medio de pago
          </button>
        </div>
      </>
    );
  }

  return (
    <section aria-labelledby="titulo-sena" className="sena">
      <h2 id="titulo-sena" className="titulo-paso" ref={titulo} tabIndex={-1}>
        Pagá la seña para confirmar tu turno
      </h2>
      <p>
        {etiquetaDiaLarga(diaClinica(reserva.inicio))}, {horaClinica(reserva.inicio)} a {horaClinica(reserva.fin)}
      </p>
      <p className="nota">
        {tratamiento.nombre} con {profesional.nombre}. Hora de Buenos Aires.
      </p>
      <div className="sena-monto">
        <span>Seña a pagar</span>
        <strong>{montoExacto(sena.monto)}</strong>
      </div>
      <p className="sena-vence">{`Tu reserva vence a las ${horaClinica(sena.vence_en)}`}</p>
      <p className="aviso aviso-ok">Tu turno no está confirmado hasta acreditar la seña.</p>
      <p className="politica">{sena.texto_politica_reembolso}</p>

      {error !== null && <AvisoError error={error} onNueva={onNueva} />}

      <div className="acciones acciones-columna">
        {sena.medios_habilitados.map((medio) => (
          <button
            key={medio}
            type="button"
            className={`boton ${medio === 'mercadopago' ? 'boton-primario' : 'boton-secundario'}`}
            disabled={enCurso !== null}
            onClick={() => {
              void elegir(medio);
            }}
          >
            {enCurso === medio ? 'Un momento…' : ETIQUETA_MEDIO[medio]}
          </button>
        ))}
      </div>
    </section>
  );
}
