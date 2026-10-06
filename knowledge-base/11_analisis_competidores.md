# Análisis de Competidores y Mercado

Extra justificado: la discovery trae relevamiento de 18+ sistemas en 3 frentes con matriz ponderada; ese material no cabe en los canónicos y debe preservarse como referencia de producto. Fuente: `docs/discovery/informe-discovery.md` §4, `docs/discovery/Validación Discovery.md`, `state.discovery.sources` (verificadas 2026-09-29).

## Situación actual

Cómo lo resuelven hoy: sistemas dispersos, principalmente **Google Calendar + WhatsApp manual**. Sin scraping directo (Calendar interno, sin URL pública).

## Conclusión del relevamiento

La agenda genérica está cubierta (AgendaPro, Doctoralia); el gap argentino es la **localización comprobable**: obras sociales + nomenclador + AFIP/ARCA + Mercado Pago + WhatsApp con costo explícito + sillones/sobreturnos anti-solape. Solo los nativos AR la declaran.

## Rivales directos (AR)

| Sistema | Notas verificadas |
|---------|-------------------|
| DentalSoft AR (dentalsoft.com.ar) | Rival directo: localización AR + WA + anti-solape + precio ARS. Declara +300 clínicas y −82% ausencias (**autodeclarado, sin auditoría**). Validación confirma: agenda drag&drop con detección de solape, WA, MP |
| Bilog (dev.bilog.com.ar) | +20 años, SaaS + app móvil, odontograma, turnos online, facturación electrónica (sugiere AFIP). Precio no publicado (demo). Corrección menor de validación: sí tienen anamnesis/facturación |
| DentalSaaS / DelRioTech | Nomenclador OS AR, WA ilimitado, $59k/mes |
| Dentiqa (dentiqa.app/ar) | Chatbot Claude WA 24/7, cobro por MP |
| OdontoSoft Millennium (odontosoft.com) | 30 años, Windows local, sin nube/online/WA |

## LatAm (referencia funcional, sin localización AR)

| Sistema | Notas |
|---------|-------|
| Dentalink (CL) | Estándar clínico LatAm; WA, odontograma, periodontograma; 15.000 clientes / 12M pacientes declarados. Precio AR no público (cotizar). Capterra AR: 5.0 con solo 2 reseñas, desde US$ 29/mes |
| DentiDesk (CL) | Profundidad por especialidades, WA automático, foco SII Chile |
| Doctocliq (PE) | Gratis + USD 19–49, odontograma; mejor modelo de entrada |
| AgendaPro (CL) | Agenda/marketing excelente, sin odontograma (declarado oficialmente) |
| SaludTools (CO) | Compliance DIAN/RIPS + GCal, sin odontograma |
| Simples Dental (BR) | Mejor flujo odontograma→presupuesto→cobro (Pix), cadeiras (sillones) |
| Dentalsoft.pro (MX) | CFDI + nómina, sin reserva pública evidenciada |

## Internacional (patrones a clonar)

| Sistema | Patrón útil |
|---------|-------------|
| Open Dental (USA) | ASAP List + API + boxes → clonar con WhatsApp |
| Curve Dental (USA) | GRO todo incluido + Smart Fill |
| tab32 (USA) | Pricing startup + usage-based + API abierta |
| CareStack / Dentrix Ascend / Dentally | Enterprise/seguridad (SOC2, GDPR, auditoría) |
| Doctoralia | Marketplace + agenda, sin gestión odontológica |

## Descartados con fundamento

Boreal Salud (prepaga, no software), OdontoGo BR (agencia marketing), DentalGest (plugin español), «Softly», Qure, Egestiona, Medilink dental AR, Clinic Cloud dental AR (sin evidencia verificable). Gesden / Nubimed / DentalTap: sin relevancia AR directa.

## Advertencia metodológica

Las cifras de adopción del mercado son autodeclaraciones sin auditoría. Informe completo (tabla 18 sistemas, matriz ponderada, recomendación con 5 demos y 3 refs UX) entregado en la conversación del 2026-09-29, fuera de los archivos ingeridos.
