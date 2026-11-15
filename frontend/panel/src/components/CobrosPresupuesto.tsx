import { useId, useState } from 'react';
import type { Api } from '../lib/api';
import { aplicarCobro, fechaCobroParaEnviar, mensajeDeErrorPresupuesto, normalizarMonto, pesosCompactos, restarMontos, validarCobro, validarMotivo } from '../lib/presupuestos';
import { ErrorSesion } from '../lib/sesion';
import { fechaCorta, hoyClinica } from '../lib/tiempo';
import type { DatosCobro, ErrorClinico, MedioCobro, PagoPresupuesto, Presupuesto } from '../lib/tipos';
import { Dialogo } from './Dialogo';

interface Props {
  readonly api: Api;
  readonly pacienteId: number;
  readonly presupuesto: Presupuesto;
  /** Recepción y admin registran y anulan cobros; los demás roles no llegan a este componente con datos de pagos. */
  readonly puedeRegistrar: boolean;
  /** "Hoy" en la clínica ("YYYY-MM-DD"); por defecto el de este momento. */
  readonly hoy?: string;
  /** El presupuesto cambió (cobro registrado o anulado, o saldo corregido por el servidor). */
  readonly onCambio: (presupuesto: Presupuesto) => void;
}

const MEDIOS: readonly { readonly clave: MedioCobro; readonly etiqueta: string }[] = [
  { clave: 'mercadopago', etiqueta: 'Mercado Pago' },
  { clave: 'transferencia', etiqueta: 'Transferencia' },
];

const etiquetaMedio = (m: MedioCobro): string => MEDIOS.find((x) => x.clave === m)?.etiqueta ?? m;

/** Cobros de un presupuesto: lista (con anulados y su motivo), registro de un cobro y anulación con motivo (RN-PG-06, O14). */
export function CobrosPresupuesto({ api, pacienteId, presupuesto, puedeRegistrar, hoy, onCambio }: Props) {
  const idBase = useId();
  const [hoyFijo] = useState(() => hoy ?? hoyClinica(new Date()));
  const aceptado = presupuesto.estado === 'aceptado';
  const [medio, setMedio] = useState<MedioCobro>('transferencia');
  const [monto, setMonto] = useState(presupuesto.saldo);
  const [saldoPrevio, setSaldoPrevio] = useState(presupuesto.saldo);
  if (presupuesto.saldo !== saldoPrevio) {
    // El saldo cambió (otro cobro, una anulación o el saldo que informó el servidor): el monto sugerido lo sigue.
    setSaldoPrevio(presupuesto.saldo);
    setMonto(presupuesto.saldo);
  }
  const [fecha, setFecha] = useState(hoyFijo);
  const [referencia, setReferencia] = useState('');
  const [errores, setErrores] = useState<{ readonly monto: string | null; readonly referencia: string | null }>({ monto: null, referencia: null });
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [anulando, setAnulando] = useState<PagoPresupuesto | null>(null);
  const [motivo, setMotivo] = useState('');
  const [rechazoAnular, setRechazoAnular] = useState<string | null>(null);
  const [anulandoEnvio, setAnulandoEnvio] = useState(false);

  function conSaldoDelServidor(error: ErrorClinico): void {
    if (error.tipo !== 'monto_excede_saldo' || error.saldo === null) return;
    onCambio({ ...presupuesto, saldo: error.saldo, total_pagado: restarMontos(presupuesto.total_paciente, error.saldo) });
  }

  async function registrar(): Promise<void> {
    if (enviando) return;
    const nuevos = validarCobro({ monto, saldo: presupuesto.saldo, referencia });
    setErrores(nuevos);
    setRechazo(null);
    const normal = normalizarMonto(monto);
    if (nuevos.monto !== null || nuevos.referencia !== null || normal === null) return;
    const fechaCobro = fechaCobroParaEnviar(hoyFijo, fecha);
    const texto = referencia.trim();
    const datos: DatosCobro = {
      medio,
      monto: normal,
      ...(fechaCobro === undefined ? {} : { fecha_cobro: fechaCobro }),
      referencia: texto === '' ? null : texto,
    };
    setEnviando(true);
    try {
      const r = await api.registrarCobro(pacienteId, presupuesto.id, datos);
      if (r.ok) {
        setReferencia('');
        onCambio(aplicarCobro(presupuesto, r.valor));
        return;
      }
      if (r.error.tipo === 'referencia_duplicada') setErrores({ monto: null, referencia: mensajeDeErrorPresupuesto(r.error) });
      else setRechazo(mensajeDeErrorPresupuesto(r.error));
      conSaldoDelServidor(r.error);
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setEnviando(false);
    }
  }

  async function anular(pago: PagoPresupuesto): Promise<void> {
    if (anulandoEnvio) return;
    setAnulandoEnvio(true);
    setRechazoAnular(null);
    try {
      const r = await api.anularCobro(pacienteId, presupuesto.id, pago.id, motivo.trim());
      if (r.ok) {
        setAnulando(null);
        setMotivo('');
        onCambio(aplicarCobro(presupuesto, r.valor));
        return;
      }
      setRechazoAnular(mensajeDeErrorPresupuesto(r.error));
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      throw error;
    } finally {
      setAnulandoEnvio(false);
    }
  }

  const errorMotivo = motivo === '' ? null : validarMotivo(motivo);
  const saldoCero = restarMontos(presupuesto.saldo, '0.00') === '0.00';

  return (
    <section className="cobros" aria-label="Cobros">
      {aceptado && (
        <p className="cobros-resumen">
          Pagado {pesosCompactos(presupuesto.total_pagado)} · Saldo {pesosCompactos(presupuesto.saldo)}
        </p>
      )}
      {presupuesto.pagos.length > 0 && (
        <ul className="lista-cobros" aria-label="Cobros">
          {presupuesto.pagos.map((p) => (
            <li key={p.id} className={`cobro${p.estado === 'anulado' ? ' cobro-anulado' : ''}`}>
              <p>
                {etiquetaMedio(p.medio)} · {pesosCompactos(p.monto)} · {fechaCorta(p.fecha_cobro)}
                {p.referencia !== null ? ` · ${p.referencia}` : ''}
              </p>
              {p.estado === 'anulado' && <p className="nota texto-largo">Anulado · {p.anulado_motivo ?? ''}</p>}
              {puedeRegistrar && p.estado === 'registrado' && (
                <button
                  type="button"
                  className="boton boton-secundario"
                  onClick={() => {
                    setMotivo('');
                    setRechazoAnular(null);
                    setAnulando(p);
                  }}
                >
                  Anular cobro
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {puedeRegistrar && aceptado && (
        saldoCero ? (
          <p className="nota">El presupuesto está cobrado por completo.</p>
        ) : (
          <form
            className="form-cobro"
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void registrar();
            }}
          >
            <h4 className="subtitulo">Registrar cobro</h4>
            <div className="selector" role="group" aria-label="Medio de cobro">
              {MEDIOS.map((m) => (
                <button
                  key={m.clave}
                  type="button"
                  className={`selector-boton${medio === m.clave ? ' activo' : ''}`}
                  aria-pressed={medio === m.clave}
                  onClick={() => {
                    setMedio(m.clave);
                  }}
                >
                  {m.etiqueta}
                </button>
              ))}
            </div>
            <div className="campo">
              <label htmlFor={`${idBase}-monto`}>Monto</label>
              <input
                id={`${idBase}-monto`}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={monto}
                aria-invalid={errores.monto !== null}
                onChange={(e) => {
                  setMonto(e.target.value);
                }}
              />
              {errores.monto !== null && <p className="campo-error">{errores.monto}</p>}
            </div>
            <div className="campo">
              <label htmlFor={`${idBase}-fecha`}>Fecha de cobro</label>
              <input
                id={`${idBase}-fecha`}
                type="date"
                max={hoyFijo}
                value={fecha}
                onChange={(e) => {
                  if (e.target.value !== '' && e.target.value <= hoyFijo) setFecha(e.target.value);
                }}
              />
            </div>
            <div className="campo">
              <label htmlFor={`${idBase}-ref`}>Referencia (opcional)</label>
              <input
                id={`${idBase}-ref`}
                type="text"
                autoComplete="off"
                maxLength={64}
                value={referencia}
                aria-invalid={errores.referencia !== null}
                onChange={(e) => {
                  setReferencia(e.target.value);
                }}
              />
              {errores.referencia !== null && <p className="campo-error">{errores.referencia}</p>}
            </div>
            {rechazo !== null && (
              <p className="aviso aviso-error" role="alert">
                {rechazo}
              </p>
            )}
            <div className="acciones">
              <button type="submit" className="boton boton-primario" disabled={enviando}>
                {enviando ? 'Registrando…' : 'Registrar cobro'}
              </button>
            </div>
          </form>
        )
      )}

      {anulando !== null && (
        <Dialogo
          titulo="¿Anular este cobro?"
          confirmar="Anular cobro"
          enviando={anulandoEnvio}
          confirmarDeshabilitado={validarMotivo(motivo) !== null}
          rechazo={rechazoAnular}
          onVolver={() => {
            setAnulando(null);
          }}
          onConfirmar={() => void anular(anulando)}
        >
          <p>
            {etiquetaMedio(anulando.medio)} · {pesosCompactos(anulando.monto)}. El cobro sigue visible como anulado y el saldo vuelve a sumar su monto.
          </p>
          <div className="campo">
            <label htmlFor={`${idBase}-motivo`}>Motivo</label>
            <textarea
              id={`${idBase}-motivo`}
              rows={3}
              value={motivo}
              onChange={(e) => {
                setMotivo(e.target.value);
              }}
            />
            {errorMotivo !== null && <p className="campo-error">{errorMotivo}</p>}
          </div>
        </Dialogo>
      )}
    </section>
  );
}
