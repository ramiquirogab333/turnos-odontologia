# Discovery — turnos-odontologia

**Fecha**: 2026-09-29
**Fuentes investigadas**: sin URLs aportadas por el usuario; relevamiento de mercado propio con 3 frentes (Argentina, LatAm, internacional) sobre fuentes oficiales verificadas — ver §4 y `state.discovery.sources`.

## 1. Problema que resuelve

Coordinar turnos odontológicos en consultorios y clínicas chicas hoy es un caos: WhatsApp, papel, teléfono y Google Calendar dispersos generan dobles reservas, ausentismo alto y tiempo perdido confirmando manualmente cada turno.

## 2. Usuarios / roles

- **Paciente**: reserva, cancela y reprograma sus turnos sin llamar.
- **Odontólogo/a**: ve su agenda por día/semana vía panel de control.
- **Recepción/admin**: gestiona agenda, pacientes, ausentismo y liquidaciones vía panel de control.

## 3. Casos de uso

1. Como paciente, quiero ver los horarios libres y reservar un turno sin tener que llamar ni escribir por WhatsApp.
2. Como paciente, quiero cancelar o reprogramar mi turno respetando la anticipación mínima para liberar el horario.
3. Como paciente, quiero recibir recordatorios por WhatsApp para no olvidar mi turno.
4. Como odontólogo/a, quiero ver mi agenda del día/semana por profesional para saber a quién atiendo y cuándo.
5. Como recepción/admin, quiero gestionar pacientes, ausentes, ocupación por sillón y cierres de caja desde un panel.

Núcleo priorizado por el usuario: 1, 2 y 3 (reserva, cancelación/reprogramación, recordatorios WhatsApp).

## 4. Competidores / soluciones existentes

Cómo lo resuelven hoy: diversos sistemas, principalmente **Google Calendar + WhatsApp manual**. Sin scraping directo (Calendar es interno, sin URL pública).

**Estudio de mercado ad-hoc (2026-09-29, solo fuentes oficiales/verificadas):** se relevaron 18+ sistemas en tres frentes. Conclusión: la agenda genérica está cubierta (AgendaPro, Doctoralia); el gap argentino es la **localización comprobable** (obras sociales + nomenclador + AFIP/ARCA + Mercado Pago + WhatsApp con costo explícito + sillones/sobreturnos anti-solape). Solo los nativos la declaran.

| Sistema | Origen | Veredicto corto |
|---|---|---|
| DentalSoft AR (dentalsoft.com.ar) | AR | Rival directo: único con localización AR + WA + anti-solape + precio ARS evidenciados |
| Bilog (dev.bilog.com.ar) | AR | Trayectoria +20 años, SaaS + app, precio no publicado |
| DentalSaaS/DelRioTech | AR | Nomenclador OS AR, WA ilimitado, $59k/mes |
| Dentiqa (dentiqa.app/ar) | AR | Chatbot Claude WA 24/7, cobro por MP |
| Dentalink (softwaredentalink.com) | CL | Estándar clínico LatAm, sin localización AR ni precio público |
| DentiDesk (dentidesk.com) | CL | Profundidad por especialidades, WA automático «próximo», foco SII Chile |
| Doctocliq (doctocliq.com) | PE | Gratis + USD 19–49, odontograma, el mejor modelo de entrada |
| AgendaPro (agendapro.com) | CL | Agenda/marketing excelente, sin odontograma (declarado oficialmente) |
| Doctoralia (pro.doctoralia.com/ar) | PL/ES | Marketplace + agenda, sin gestión odontológica |
| OdontoSoft Millennium (odontosoft.com) | AR/US | 30 años, Windows local, sin nube/online/WA |
| SaludTools (saludtools.com) | CO | Compliance DIAN/RIPS + GCal, sin odontograma |
| Simples Dental (simplesdental.com) | BR | Mejor flujo odontograma→presupuesto→cobro (Pix), cadeiras |
| Dentalsoft.pro (dentalsoft.pro) | MX | CFDI + nómina, sin reserva pública evidenciada |
| Open Dental (opendental.com) | USA | Referencia: ASAP List + API + boxes (patrón a clonar con WA) |
| Curve Dental (curvedental.com) | USA | Referencia: GRO todo incluido + Smart Fill |
| tab32 (tab32.com) | USA | Referencia: pricing startup + usage-based + API abierta |
| CareStack / Dentrix Ascend / Dentally | USA/UK | Referencia enterprise/seguridad (SOC2, GDPR, auditoría) |
| Gesden / Nubimed / DentalTap | ES/UA | Sin relevancia AR directa |

Descartados con fundamento: Boreal Salud (prepaga, no software), OdontoGo BR (agencia marketing), DentalGest (plugin español), «Softly», Qure, Egestiona, Medilink dental AR, Clinic Cloud dental AR (sin evidencia verificable).
Informe completo entregado en la conversación del 2026-09-29 (tabla 18 sistemas, matriz ponderada, análisis C y recomendación D con 5 demos, 3 refs UX y MVP).

## 5. Funcionalidades necesarias

Orden del usuario (MVP): panel admin → recordatorio WhatsApp → reserva online → cancelación/reprogramación → agenda por profesional. En concreto: agenda multi-profesional + sillones con anti-solape; reserva online sin registro obligatorio (nombre + teléfono); cancelación/reprogramación con regla 24 hs; recordatorios y confirmación por WhatsApp con botones; panel admin (ocupación, ausentismo, recupero, caja); ficha + odontograma FDI básico + presupuestos con cobertura OS; nomenclador OS AR precargado; Mercado Pago + transferencia; sincronía Google Calendar bidireccional; roles y auditoría básica; exportación masiva.

## 6. Funcionalidades opcionales

Historia de turnos por paciente extendida; periodontograma avanzado e imágenes/RX con IA; facturación electrónica ARCA nativa completa; portal paciente con historia y cuotas; campañas de recupero y controles periódicos; API pública y webhooks; app móvil dedicada; multi-sucursal, laboratorio e inventario; firma digital y consentimientos; IA de secretaría 24/7.

## 7. Reglas de negocio

- No se puede cancelar un turno con menos de 24 horas de anticipación.
- Duración fija por tratamiento, a definir según tratamiento (tabla configurable por el admin, no fija en código).
- Un profesional no puede tener dos turnos superpuestos (sin superposición).

## 8. Integraciones

- WhatsApp (recordatorios y confirmación; a definir manual vs. automático vía API tipo Twilio/Meta).
- Google Calendar (sincronía con la agenda del profesional; hoy es el sistema principal en uso).
- Sin obra social/facturación electrónica en la v1 más allá del nomenclador precargado y Mercado Pago.

## 9. Restricciones

Sin restricciones: libertad total de stack, plazo y plataforma. Se asume como criterio de diseño que debe andar bien en celular (la mayoría reserva desde el teléfono).

## 10. Riesgos

- **Supuesto sin probar**: que los pacientes prefieran reservar online en vez de seguir mandando WhatsApp por costumbre.
- **Riesgo**: si el admin no mantiene la disponibilidad actualizada, el sistema muestra horarios que en realidad no están libres.
- **Riesgo**: las reglas (duraciones por tratamiento, ventana de 24 hs) cambian a mitad de camino y obligan a re-modelar la agenda.
- **Riesgo de mercado**: competidores nativos (DentalSoft AR) ya ocupan el wedge de localización; las cifras de adopción del mercado son autodeclaraciones sin auditoría.

## 11. Preguntas abiertas

- ¿Uno o varios odontólogos desde el día 1? (impacta agenda por profesional y sillones).
- ¿Hace falta login para el paciente, o alcanza con nombre + teléfono por turno?
- ¿WhatsApp manual o automático vía API (costo por mensaje)?
- ¿Tabla concreta tratamiento→duración para la v1?
