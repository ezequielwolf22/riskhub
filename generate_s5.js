const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";

const D="1C1C1C",W="FFFFFF",G="F3F3F3",DG="2D2D2D";
const MUT="6B6B6B",SMUT="9A9A9A",WMUT="888888";
const ACC="D64D00",BLU="1B5FA8",GRN="1A5C35",TEA="0E6674",RED="8B1A1A";

function dk(s){s.background={color:D};}
function wh(s){s.background={color:W};}
function r(s,x,y,w,h,f,l){s.addShape(pres.shapes.RECTANGLE,{x,y,w,h,fill:{color:f},line:{color:l||f}});}
function t(s,text,x,y,w,h,o={}){s.addText(text,{x,y,w,h,fontFace:"Calibri",...o});}

function sec(title,sub){
  const s=pres.addSlide();dk(s);
  t(s,title,0.65,1.75,9,0.9,{fontSize:50,color:W,bold:true,lineSpacingMultiple:1.05});
  if(sub)t(s,sub,0.65,2.78,9,0.42,{fontSize:17,color:WMUT});
  return s;
}
function ws(title,sub){
  const s=pres.addSlide();wh(s);
  t(s,title,0.5,0.25,9.1,0.52,{fontSize:27,color:D,bold:true});
  if(sub)t(s,sub,0.5,0.82,9.1,0.3,{fontSize:12.5,color:MUT});
  return s;
}

function ctrlENS(title,sub,controls){
  const s=pres.addSlide();wh(s);
  t(s,title,0.38,0.16,9.2,0.44,{fontSize:20,color:D,bold:true});
  if(sub)t(s,sub,0.38,0.63,9.2,0.27,{fontSize:11,color:MUT});
  const hY=0.95,cx=[0.38,2.05,4.22,6.4],cw=[1.62,2.12,2.12,2.88];
  ["Control","Propósito y riesgo","Evidencia clave","ENS equivalente (825)"].forEach((h,i)=>{
    r(s,cx[i],hY,cw[i]-0.02,0.3,D,D);
    t(s,h,cx[i]+0.06,hY,cw[i]-0.1,0.3,{fontSize:9.5,color:W,bold:true,valign:"middle"});
  });
  controls.forEach((c,i)=>{
    const y=1.28+i*0.53,bg=i%2===0?W:G;
    r(s,0.38,y,9.2,0.51,bg,bg);
    r(s,0.38,y,0.05,0.51,TEA,TEA);
    t(s,c.code,0.48,y+0.04,0.72,0.2,{fontSize:8.5,color:TEA,bold:true,fontFace:"Calibri"});
    t(s,c.name,0.48,y+0.25,1.52,0.22,{fontSize:10,color:D,bold:true});
    t(s,c.risk,cx[1]+0.05,y+0.04,cw[1]-0.12,0.44,{fontSize:10,color:D,lineSpacingMultiple:1.25});
    t(s,c.ev,  cx[2]+0.05,y+0.04,cw[2]-0.12,0.44,{fontSize:10,color:MUT,lineSpacingMultiple:1.25});
    r(s,cx[3]+0.05,y+0.08,cw[3]-0.15,0.26,GRN,GRN);
    t(s,c.ens,cx[3]+0.1,y+0.08,cw[3]-0.22,0.26,{fontSize:9,color:W,bold:true,valign:"middle",fontFace:"Calibri"});
    if(c.ensd)t(s,c.ensd,cx[3]+0.05,y+0.36,cw[3]-0.12,0.14,{fontSize:8.5,color:MUT,italic:true});
  });
  return s;
}

// ─────────────────────────────────────────
// SLIDE 01 COVER
// ─────────────────────────────────────────
{const s=pres.addSlide();dk(s);
t(s,"Sesión 5",0.65,0.7,8,0.35,{fontSize:15,color:WMUT});
t(s,"A.8 · Certificación ISO 27001\nDeclaración ENS\n+ Intro Continuidad de Negocio",0.65,1.08,9,2.5,{fontSize:42,color:W,bold:true,lineSpacingMultiple:1.06});
t(s,"Retomamos S4 · Avanzamos hacia el módulo de BCM · ISO 22301 · ENS [op.cont.*]",0.65,3.7,9,0.35,{fontSize:13,color:WMUT});
r(s,0.65,4.2,1.1,0.04,WMUT,WMUT);
t(s,"ISO 27001:2022 + ENS (RD 311/2022)",0.65,4.38,8,0.28,{fontSize:11,color:SMUT});
s.addNotes(`PORTADA S5
0:00–0:05

Retomamos los bloques 2 y 3 de la sesión 4 que no pudimos ver: controles A.8 y el proceso de certificación. Después arrancamos el tema de continuidad de negocio — aunque no lo veremos completo hoy, empezamos a construir la base conceptual.`);}

// ─────────────────────────────────────────
// SLIDE 02 AGENDA
// ─────────────────────────────────────────
{const s=pres.addSlide();dk(s);
t(s,"Agenda",0.65,0.55,4,0.58,{fontSize:36,color:W,bold:true});
t(s,"Sesión 5 · 3 horas",0.65,1.18,4,0.3,{fontSize:14,color:WMUT});
const items=[
  {n:"00",t:"Repaso S4 · Kahoot 10 preguntas",tm:"0:00–0:25",note:""},
  {n:"01",t:"[Pendiente S4] Controles A.8 — Los 34 controles tecnológicos",tm:"0:25–1:05",note:"S4 B2"},
  {n:"02",t:"[Pendiente S4] Certificación ISO 27001 · Declaración ENS",tm:"1:05–1:25",note:"S4 B3"},
  {n:"⏸",t:"PAUSA",tm:"1:25–1:45",note:""},
  {n:"03",t:"Continuidad de Negocio — Introducción y fundamentos",tm:"1:45–2:50",note:"BCM"},
  {n:"✓",t:"Síntesis · Preview S6 (BCM completo)",tm:"2:50–3:00",note:""},
];
items.forEach((it,i)=>{
  const y=1.6+i*0.64;
  r(s,5.1,y,4.6,0.56,DG,DG);
  t(s,it.n,5.1,y,0.55,0.56,{fontSize:14,color:it.n==="⏸"?ACC:it.note?TEA:WMUT,bold:true,align:"center",valign:"middle"});
  t(s,it.t,5.7,y+0.06,3.85,0.26,{fontSize:12.5,color:W,bold:true});
  t(s,it.tm,5.7,y+0.34,3.85,0.2,{fontSize:10,color:SMUT,fontFace:"Calibri"});
});
s.addNotes("AGENDA S5\n0:03–0:06");}

// ─────────────────────────────────────────
// A.8 CONTROLS CARRY-OVER
// ─────────────────────────────────────────
sec("Bloque 01 [pendiente S4]\nControles A.8","Los 34 controles tecnológicos · Comparativa ISO 27001 ↔ ENS")
  .addNotes("INTRO A.8");

const a8I=[
  {code:"A.8.1",name:"Dispositivos usuario final",risk:"Datos corporativos en dispositivos no gestionados → fuga o malware desde endpoints",ev:"Política de dispositivos, inventario, MDM con cifrado activo",ens:"[mp.eq.1] Puesto de trabajo",ensd:"Configuración segura y cifrado del puesto"},
  {code:"A.8.2",name:"Accesos privilegiados",risk:"Cuenta privilegiada comprometida → acceso total a sistemas críticos",ev:"Inventario cuentas privilegiadas, solución PAM, auditoría de uso",ens:"[op.acc.4] Gestión derechos de acceso",ensd:"Ciclo de vida de derechos privilegiados"},
  {code:"A.8.3",name:"Restricción acceso info",risk:"Over-provisioning: usuario accede más allá de su función → fuga interna",ev:"ACLs por rol implementadas, evidencia de pruebas de acceso",ens:"[op.acc.2] Requisitos de acceso",ensd:"Acceso basado en necesidad de conocer"},
  {code:"A.8.5",name:"Autenticación segura",risk:"Credenciales robadas o débiles → compromiso sin detección",ev:"Config MFA, política de contraseñas técnicamente aplicada en AD",ens:"[op.acc.6] Autenticación",ensd:"MFA para accesos remotos y privilegiados"},
  {code:"A.8.6",name:"Gestión de capacidad",risk:"Falta de recursos → degradación o caída → disponibilidad comprometida",ev:"Registros de monitorización, umbrales de alerta, plan de escalado",ens:"[op.pl.4] Dimensionamiento",ensd:"Planificación de capacidad documentada"},
  {code:"A.8.7",name:"Protección frente a malware",risk:"Ransomware, troyano, spyware → pérdida o cifrado de activos críticos",ev:"EDR/AV desplegado y actualizado, política de ejecución de software",ens:"[op.exp.6] Código dañino",ensd:"Protección y detección de malware"},
  {code:"A.8.8",name:"Gestión de vulnerabilidades",risk:"Vulnerabilidad conocida sin parchear → vector de ataque predecible",ev:"Informes de escaneo, tickets de remediación, SLA de parcheo por CVSSv3",ens:"[op.mon.3]+[op.exp.4]",ensd:"Vigilancia + Mantenimiento"},
];
const a8II=[
  {code:"A.8.9",name:"Gestión de configuración",risk:"Config por defecto insegura o deriva de hardening → superficie de ataque ampliada",ev:"Baselines CIS Benchmarks documentadas, informes de cumplimiento",ens:"[op.exp.2]+[op.exp.3]",ensd:"Configuración + Gestión de cambios"},
  {code:"A.8.10",name:"Eliminación de información",risk:"Datos residuales en sistemas dados de baja → recuperación de info sensible",ev:"Política, registros de borrado seguro o destrucción, certificados",ens:"[mp.si.3] Borrado y destrucción",ensd:"Eliminación segura de soportes"},
  {code:"A.8.11",name:"Enmascaramiento de datos",risk:"Datos reales en entornos de prueba → exposición innecesaria de datos sensibles",ev:"Política de masking en entornos no-prod, evidencia técnica",ens:"[mp.info.4] Cifrado (parcial)",ensd:"Protección de confidencialidad"},
  {code:"A.8.12",name:"Prevención fugas (DLP)",risk:"Exfiltración de datos por email, USB o cloud personal sin detección",ev:"Herramienta DLP configurada, políticas activas, registros de alertas",ens:"[mp.com.2] Confidencialidad",ensd:"Protección de la confidencialidad en tránsito"},
  {code:"A.8.13",name:"Copias de seguridad",risk:"Pérdida de datos por ransomware o fallo sin capacidad de recuperación",ev:"Política con RTO/RPO, registros de backup Y pruebas de restauración",ens:"[mp.info.6] Copias de seguridad",ensd:"Backup con pruebas de restauración"},
  {code:"A.8.15",name:"Registro de actividad (logging)",risk:"Incidente sin rastro → imposible determinar qué pasó y cuándo",ev:"Política de logging con retención definida, SIEM o colector central",ens:"[op.exp.8] Registro de actividad",ensd:"Logs centralizados con retención mínima"},
  {code:"A.8.16",name:"Monitorización actividades",risk:"Actividad maliciosa no detectada hasta que el daño está hecho",ev:"SIEM activo, reglas de detección documentadas, registros de alertas",ens:"[op.mon.1]+[op.mon.2]",ensd:"Detección intrusión + Vigilancia"},
];
const a8III=[
  {code:"A.8.20",name:"Seguridad de redes",risk:"Red sin controles → acceso libre entre segmentos y sistemas críticos",ev:"Arquitectura documentada, reglas de firewall revisadas, inventario servicios expuestos",ens:"[mp.com.1] Perímetro seguro",ensd:"Defensa perimetral documentada"},
  {code:"A.8.22",name:"Segmentación de redes",risk:"Red plana → movimiento lateral del atacante a todos los sistemas",ev:"Diagrama de VLANs/DMZ, reglas de segmentación auditadas",ens:"[mp.com.4] Separación de flujos",ensd:"Segmentación de flujos de información"},
  {code:"A.8.23",name:"Filtrado web",risk:"Usuarios acceden a URLs maliciosas → malware por descarga o phishing",ev:"Proxy/DNS filtering activo, categorías bloqueadas, logs de intentos",ens:"[mp.s.2] Navegación web",ensd:"Protección de la navegación web"},
  {code:"A.8.24",name:"Uso de criptografía",risk:"Datos en tránsito o reposo sin cifrar → interceptación o robo directo",ev:"Política criptográfica, inventario certificados, gestión de claves",ens:"[mp.si.2]+[op.exp.10]",ensd:"Criptografía + Gestión de claves"},
  {code:"A.8.25",name:"Ciclo de vida seguro (SDLC)",risk:"Software sin seguridad incorporada → vulnerabilidades estructurales desde el diseño",ev:"Política SDLC, checklist de seguridad por fase, threat modeling",ens:"[mp.sw.1] Desarrollo",ensd:"Requisitos de seguridad en desarrollo"},
  {code:"A.8.28",name:"Codificación segura",risk:"Vulnerabilidades en código propio (OWASP Top 10, inyecciones, XSS)",ev:"Guía de codificación segura, resultados de SAST/DAST, revisión de código",ens:"[mp.sw.1] (parcial)",ensd:"Desarrollo seguro — prácticas OWASP"},
  {code:"A.8.29",name:"Pruebas de seguridad",risk:"Sistema con vulnerabilidades llega a producción sin ser probado",ev:"Resultados VA/pentest, SAST/DAST en CI/CD, criterios de aceptación",ens:"[mp.sw.2] Aceptación y puesta en servicio",ensd:"Pruebas obligatorias antes del go-live"},
];

ctrlENS("A.8 · Controles tecnológicos I","Endpoints, accesos privilegiados, malware y vulnerabilidades — A.8.1 a A.8.8",a8I)
  .addNotes("A.8-I");

ctrlENS("A.8 · Controles tecnológicos II","Configuración, DLP, backups y monitorización — A.8.9 a A.8.16",a8II)
  .addNotes("A.8-II");

ctrlENS("A.8 · Controles tecnológicos III","Redes, criptografía y desarrollo seguro — A.8.20 a A.8.29",a8III)
  .addNotes("A.8-III");

// ─────────────────────────────────────────
// EJERCICIO A.8
// ─────────────────────────────────────────
{const s=pres.addSlide();dk(s);
t(s,"Ejercicio · 8 minutos",0.65,0.5,8,0.28,{fontSize:12,color:SMUT,bold:true,charSpacing:2});
t(s,"TechServ: los 5 controles A.8 más urgentes",0.65,0.85,9,0.58,{fontSize:34,color:W,bold:true});
t(s,"Sistemas ALTA: nóminas · expedientes · sede electrónica. Sin SGSI previo.",0.65,1.5,9,0.32,{fontSize:13,color:WMUT});
r(s,0.5,1.95,9.1,2.65,DG,DG);
t(s,"Para cada control elegido indicad: código · riesgo TechServ que lo justifica · acción concreta · evidencia · ENS equivalente (825)",0.7,2.05,8.7,0.35,{fontSize:12,color:W,bold:true,lineSpacingMultiple:1.2});
const hints=["A.8.5 MFA — accesos remotos de personal y de los usuarios de las 3 Consejerías","A.8.8 Vulnerabilidades — sistemas operacionales críticos para AAPP","A.8.13 Backup — pérdida de nóminas o expedientes = catástrofe legal","A.8.12 DLP — datos de ciudadanos y funcionarios en sistemas TechServ","A.8.16 Monitorización — detectar accesos anómalos en sistemas con datos sensibles","A.8.22 Segmentación — separar el entorno de nóminas del de expedientes y la sede"];
hints.forEach((h,i)=>t(s,"→ "+h,0.88,2.5+i*0.35,8.3,0.32,{fontSize:11.5,color:WMUT,lineSpacingMultiple:1.2}));
r(s,0.5,4.68,9.1,0.7,D,D);
t(s,"Puesta en común: 1 portavoz · máx. 2 min · debate sobre qué controles NO implementaría TechServ y por qué (exclusiones justificadas para la SoA)",0.7,4.72,8.7,0.6,{fontSize:11,color:WMUT,lineSpacingMultiple:1.35});
s.addNotes("EJERCICIO A.8");}

// ─────────────────────────────────────────
// CERTIFICACIÓN — SECCIÓN
// ─────────────────────────────────────────
sec("Bloque 02 [pendiente S4]\nCertificación ISO 27001\ny Declaración ENS","El proceso completo · Qué evalúa el auditor · Diferencias entre ambos")
  .addNotes("INTRO CERT");

// ─────────────────────────────────────────
// CERTIFICACIÓN ISO — 7 FASES
// ─────────────────────────────────────────
{const s=ws("El camino a la certificación ISO 27001","7 fases · Tiempos orientativos · Lo que evalúa el auditor en cada paso");
const steps=[
  {n:"1",t:"GAP\nAnalysis",d:"Diagnóstico estado actual vs. ISO 27001. Identifica brechas. No es auditoría.",tm:"2-4 sem",c:DG},
  {n:"2",t:"Imple-\nmentación",d:"SoA, PTR, políticas, controles, evidencias, formación.",tm:"6-18 m",c:DG},
  {n:"3",t:"Auditoría\ninterna",d:"Cl. 9.2: auditar el SGSI propio. Cerrar NCs antes del externo.",tm:"1-2 sem",c:"333333"},
  {n:"4",t:"Revisión\ndirección",d:"Cl. 9.3: 9 puntos. Dirección aprueba para certificación. Acta.",tm:"1 día",c:DG},
  {n:"5",t:"Etapa 1\nDoc.",d:"Auditor externo revisa documentación. Major gap = para el proceso.",tm:"1-2 d",c:"333333"},
  {n:"6",t:"Etapa 2\nIn situ",d:"Verifica que la implementación es real: entrevistas, evidencias.",tm:"2-5 d",c:DG},
  {n:"7",t:"Certif.\n3 años",d:"Emitido por organismo acreditado ENAC. Seguimiento anual.",tm:"3 años",c:GRN},
];
steps.forEach((st,i)=>{
  const x=0.38+i*1.35;
  r(s,x,1.05,1.22,0.55,st.c,st.c);
  t(s,st.n,x+0.04,1.08,0.3,0.48,{fontSize:19,color:WMUT,bold:true,align:"center",valign:"middle"});
  t(s,st.t,x+0.38,1.1,0.82,0.45,{fontSize:9.5,color:W,bold:true,lineSpacingMultiple:1.1});
  if(i<6){r(s,x+1.22,1.25,0.12,0.18,SMUT,SMUT);}
});
steps.forEach((st,i)=>{
  const x=0.38+i*1.35;
  r(s,x,1.68,1.22,3.1,i%2===0?G:W,i%2===0?G:W);
  r(s,x,1.68,1.22,0.25,st.c,st.c);
  t(s,st.tm,x+0.04,1.7,1.15,0.21,{fontSize:8.5,color:W,align:"center",valign:"middle"});
  t(s,st.d,x+0.06,1.98,1.12,2.65,{fontSize:10,color:D,lineSpacingMultiple:1.45});
});
r(s,0.38,4.88,9.22,0.58,D,D);
t(s,"TechServ sin SGSI previo: 12–18 meses hasta el certificado. Con base implementada: 6–12 meses. La Etapa 1 falla → vuelves a implementación. La Etapa 2 con NC mayor → certificado en espera.",0.58,4.92,8.95,0.5,{fontSize:11.5,color:WMUT,lineSpacingMultiple:1.35});
s.addNotes("CERTIFICACIÓN ISO 27001");}

// ─────────────────────────────────────────
// DECLARACIÓN ENS
// ─────────────────────────────────────────
{const s=ws("Declaración de Conformidad ENS","Proceso · Portal CCN · Tabla comparativa ISO 27001 vs. Declaración ENS");
r(s,0.45,0.95,4.55,4.42,G,G);
t(s,"Proceso — Declaración de Conformidad ENS",0.62,1.04,4.22,0.28,{fontSize:13,color:D,bold:true});
const ep=["Categorizar el sistema según Anexo I DCIAT — ya hecho.","Aplicar medidas del Anexo II según categoría. Construir evidencias.","Auditoría ENS: ordinaria cada 2 años (MEDIA/ALTA), autoevaluación (BÁSICA).","Organismo de auditoría emite informe: conforme / no conforme.","La entidad publica la Declaración en el portal ENS: ens.ccn.cni.es"];
ep.forEach((e,i)=>{
  r(s,0.62,1.42+i*0.72,0.44,0.54,D,D);
  t(s,""+(i+1),0.62,1.42+i*0.72,0.44,0.54,{fontSize:16,color:W,bold:true,align:"center",valign:"middle"});
  r(s,1.1,1.42+i*0.72,3.72,0.54,W,W);
  t(s,e,1.2,1.5+i*0.72,3.56,0.38,{fontSize:11,color:D,lineSpacingMultiple:1.3});
});
r(s,5.18,0.95,4.42,4.42,D,D);
t(s,"ISO 27001 vs. Declaración ENS",5.36,1.04,4.08,0.28,{fontSize:13,color:W,bold:true});
const comp=[
  {d:"Naturaleza",a:"Certificación externa",b:"Declaración + auditoría"},
  {d:"¿Quién certifica?",a:"Organismo acreditado ENAC",b:"La entidad + auditor ENS"},
  {d:"Periodicidad",a:"Anual + recertif. 3 años",b:"Cada 2 años (MEDIA/ALTA)"},
  {d:"Reconocimiento",a:"Internacional",b:"Nacional (España)"},
  {d:"Ámbito",a:"Toda la org. o parte",b:"Por sistema de información"},
  {d:"Catálogo público",a:"No hay registro único",b:"Portal ENS del CCN"},
];
comp.forEach((c,i)=>{
  const y=1.42+i*0.62;
  r(s,5.3,y,1.6,0.54,DG,DG);
  t(s,c.d,5.38,y+0.09,1.48,0.36,{fontSize:9.5,color:WMUT,lineSpacingMultiple:1.2});
  r(s,6.95,y,1.32,0.54,DG,DG);
  t(s,c.a,7.0,y+0.09,1.22,0.36,{fontSize:9.5,color:BLU,bold:true,lineSpacingMultiple:1.3});
  r(s,8.32,y,1.22,0.54,DG,DG);
  t(s,c.b,8.37,y+0.09,1.12,0.36,{fontSize:9.5,color:GRN,bold:true,lineSpacingMultiple:1.3});
});
t(s,"ISO",6.95,1.04,1.32,0.28,{fontSize:10,color:W,bold:true,align:"center",valign:"middle"});
t(s,"ENS",8.32,1.04,1.22,0.28,{fontSize:10,color:W,bold:true,align:"center",valign:"middle"});
s.addNotes("DECLARACIÓN ENS");}

// ─────────────────────────────────────────
// PAUSA
// ─────────────────────────────────────────
{const s=pres.addSlide();dk(s);
t(s,"⏸",4.0,1.4,2,1.5,{fontSize:90,color:WMUT,align:"center"});
t(s,"Pausa",2.5,2.9,5,0.85,{fontSize:60,color:W,bold:true,align:"center"});
t(s,"20 minutos · Volvemos a las :",2.5,3.85,5,0.45,{fontSize:18,color:WMUT,align:"center"});
s.addNotes("PAUSA");}

// ─────────────────────────────────────────
// BCM SECTION
// ─────────────────────────────────────────
sec("Bloque 03\nContinuidad de Negocio","BIA · RTO/RPO · BCP vs DRP · ENS [op.cont.*] · ISO 22301")
  .addNotes("INTRO BCM");

// ─────────────────────────────────────────
// ¿POR QUÉ BCM?
// ─────────────────────────────────────────
{const s=ws("¿Por qué existe la continuidad de negocio?","Porque los incidentes ocurren. La pregunta no es si — es cuándo y qué tan preparados estáis.");
const cases=[
  {org:"Hospital Clínic · Barcelona · 2023",d:"RansomHouse cifra sistemas durante semanas. 150 operaciones canceladas. Sin BCP operativo, no había plan alternativo de trabajo. La continuidad del servicio dependía 100% de los sistemas comprometidos.",cost:"Semanas sin servicio · datos de pacientes filtrados",color:RED},
  {org:"Ayuntamiento de Sevilla · 2023",d:"LockBit3 ataca los sistemas municipales. Servicios al ciudadano interrumpidos durante meses. Expedientes inaccesibles. Pagos paralizados. Sin un DRP probado, la recuperación fue lenta y costosa.",cost:"Meses de recuperación · servicios al ciudadano paralizados",color:RED},
  {org:"Maersk · Global · 2017 (NotPetya)",d:"Toda la infraestructura IT global cifrada en horas. 45.000 PCs destruidos. 4.000 servidores. La empresa reinstauró 45.000 equipos en 10 días gracias a un BCP maduro. Coste: ~300M$.",cost:"300M$ · recuperados en 10 días gracias al BCP",color:"1A5C35"},
];
cases.forEach((c,i)=>{
  const y=1.05+i*1.46;
  r(s,0.45,y,9.1,1.32,i%2===0?G:W,i%2===0?G:W);
  r(s,0.45,y,0.06,1.32,c.color,c.color);
  t(s,c.org,0.6,y+0.1,3.5,0.28,{fontSize:11,color:D,bold:true,fontFace:"Calibri"});
  t(s,c.d,0.6,y+0.42,6.0,0.78,{fontSize:11.5,color:D,lineSpacingMultiple:1.35});
  r(s,6.72,y+0.1,2.7,0.55,c.color,c.color);
  t(s,c.cost,6.82,y+0.12,2.55,0.5,{fontSize:10,color:W,lineSpacingMultiple:1.35});
});
s.addNotes("¿POR QUÉ BCM?");}

// ─────────────────────────────────────────
// BIA
// ─────────────────────────────────────────
{const s=ws("Business Impact Analysis (BIA)","El primer paso de cualquier plan de continuidad · ENS [op.cont.1]");
// Left: what is BIA
r(s,0.45,0.95,4.55,4.6,G,G);
t(s,"¿Qué es el BIA?",0.62,1.02,4.22,0.3,{fontSize:13,color:D,bold:true});
t(s,"Análisis sistemático que identifica:\n① Las funciones críticas del negocio\n② El impacto progresivo de su interrupción en el tiempo\n③ Las dependencias entre funciones y sistemas\n④ Los requisitos de recuperación (RTO, RPO)\n\nEl BIA es la base de todo plan de continuidad. Sin BIA, el BCP es un documento de ficción.",0.62,1.38,4.22,3.95,{fontSize:12,color:D,lineSpacingMultiple:1.6});

// Right: BIA table example
t(s,"Ejemplo de BIA para TechServ",5.18,0.95,4.45,0.3,{fontSize:13,color:D,bold:true});
const biaH=["Función crítica","Impacto 1h","Impacto 24h","RTO obj.","RPO obj."];
const biaW=[1.55,0.85,0.85,0.7,0.7];
const biaCx=[5.18,6.76,7.64,8.52,9.25];
biaH.forEach((h,i)=>{
  r(s,biaCx[i],1.32,biaW[i]-0.02,0.28,D,D);
  t(s,h,biaCx[i]+0.04,1.32,biaW[i]-0.06,0.28,{fontSize:8,color:W,bold:true,valign:"middle"});
});
const biaRows=[
  ["Sede electrónica","ALTO\nSin tramitación","MUY ALTO\nSanción ENS","4 h","1 h"],
  ["BBDD Nóminas","MEDIO\nDatos íntegros","ALTO\nPago en riesgo","8 h","0 h"],
  ["Expedientes","BAJO\nAcceso manual","ALTO\nPlazo legal incumplido","24 h","4 h"],
  ["Correo corp.","BAJO","MEDIO\nComun. alternativa","48 h","4 h"],
  ["VPN / acceso remoto","MEDIO\nSolo presencial","ALTO\nProductividad cero","2 h","N/A"],
];
biaRows.forEach((row,ri)=>{
  const by=1.62+ri*0.72, bg=ri%2===0?W:G;
  biaCx.forEach((bx,ci)=>{
    r(s,bx,by,biaW[ci]-0.02,0.68,bg,bg);
    t(s,row[ci],bx+0.04,by+0.06,biaW[ci]-0.08,0.56,{fontSize:ci===0?10.5:9.5,color:ci===0?D:MUT,bold:ci===0,lineSpacingMultiple:1.2});
  });
});
s.addNotes("BIA");}

// ─────────────────────────────────────────
// RTO / RPO
// ─────────────────────────────────────────
{const s=ws("RTO y RPO — Los dos parámetros clave de la continuidad","Recovery Time Objective · Recovery Point Objective · MAD / MTPD");

// Visual timeline
r(s,0.5,1.05,8.8,0.06,D,D);
t(s,"TIEMPO →",9.0,1.0,0.7,0.2,{fontSize:9,color:MUT,align:"left"});

// Incident point
r(s,2.5,0.65,0.05,0.85,RED,RED);
t(s,"Incidente\nocurre",2.1,0.42,0.9,0.38,{fontSize:10,color:RED,bold:true,align:"center",lineSpacingMultiple:1.2});

// Last backup
r(s,1.2,0.65,0.05,0.85,"888888","888888");
t(s,"Último\nbackup",0.8,0.42,0.8,0.38,{fontSize:10,color:MUT,align:"center",lineSpacingMultiple:1.2});

// Recovery point
r(s,2.5,1.11,6.0,0.06,RED,RED);
t(s,"RPO",5.0,0.72,0.6,0.25,{fontSize:11,color:RED,bold:true,align:"center"});
t(s,"Datos perdidos en esta ventana",4.0,0.92,2.5,0.2,{fontSize:9.5,color:MUT,align:"center"});

// RTO
r(s,2.5,1.11,4.5,0.06,"1B5FA8","1B5FA8");
t(s,"RTO",4.3,1.16,0.6,0.22,{fontSize:11,color:BLU,bold:true,align:"center"});
t(s,"Tiempo para restaurar el servicio",3.0,1.38,2.8,0.2,{fontSize:9.5,color:MUT,align:"center"});

// Recovery point marker
r(s,7.0,0.65,0.05,0.85,GRN,GRN);
t(s,"Servicio\nrestaurado",6.7,0.42,0.9,0.38,{fontSize:10,color:GRN,bold:true,align:"center",lineSpacingMultiple:1.2});

// Definitions
const defs=[
  {t:"RTO — Recovery Time Objective",d:"Tiempo máximo tolerable desde el incidente hasta que el servicio está restaurado. Lo define el negocio basándose en el impacto (BIA). Implica tecnología de recuperación: backups, HA, DR site. RTO bajo = mayor inversión.",color:BLU},
  {t:"RPO — Recovery Point Objective",d:"Cantidad máxima de datos que se puede perder. Determina la frecuencia de backup. RPO=0h → replicación síncrona. RPO=4h → backup cada 4h. RPO=24h → backup diario. RPO bajo = mayor coste de almacenamiento.",color:RED},
  {t:"MAD / MTPD — Tiempo máximo de interrupción tolerable",d:"Tiempo máximo que la organización puede sobrevivir sin la función, antes de consecuencias irreversibles (pérdida de clientes, incumplimiento legal, insolvencia). El RTO siempre debe ser menor que el MAD.",color:ACC},
];
defs.forEach((d,i)=>{
  r(s,0.45,1.75+i*1.2,9.1,1.12,i%2===0?G:W,i%2===0?G:W);
  r(s,0.45,1.75+i*1.2,0.07,1.12,d.color,d.color);
  t(s,d.t,0.62,1.82+i*1.2,3.0,0.28,{fontSize:12,color:D,bold:true});
  t(s,d.d,0.62,2.14+i*1.2,8.7,0.64,{fontSize:11.5,color:MUT,lineSpacingMultiple:1.4});
});
s.addNotes("RTO / RPO / MAD");}

// ─────────────────────────────────────────
// BCP vs DRP
// ─────────────────────────────────────────
{const s=ws("BCP y DRP — Dos planes complementarios","Business Continuity Plan · Disaster Recovery Plan · ¿Cuál hace qué?");
// Left: BCP
r(s,0.45,0.95,4.5,4.5,G,G);
r(s,0.45,0.95,4.5,0.06,BLU,BLU);
t(s,"BCP — Plan de Continuidad de Negocio",0.62,1.06,4.18,0.28,{fontSize:13,color:D,bold:true});
const bcpPts=["Foco: el NEGOCIO continúa aunque los sistemas fallen","Cubre: procedimientos manuales alternativos, activación de sitio alternativo, comunicación con clientes/AAPP, roles de crisis","Alcance: toda la organización — RRHH, finanzas, operaciones, TI","Activa cuando: un incidente impacta significativamente la operación normal","Ejemplo TechServ: si la sede electrónica cae, el BCP define cómo TechServ atiende las tramitaciones urgentes manualmente mientras TI recupera los sistemas"];
bcpPts.forEach((p,i)=>t(s,p,0.62,1.42+i*0.62,4.18,0.55,{fontSize:11.5,color:D,lineSpacingMultiple:1.35,bullet:true}));

// Right: DRP
r(s,5.15,0.95,4.5,4.5,D,D);
r(s,5.15,0.95,4.5,0.06,GRN,GRN);
t(s,"DRP — Plan de Recuperación ante Desastres",5.32,1.06,4.18,0.28,{fontSize:13,color:W,bold:true});
const drpPts=["Foco: los SISTEMAS TIC se recuperan al estado operativo","Cubre: recuperación de servidores, BBDD, redes, aplicaciones desde backup o sitio DR","Alcance: equipo de TI — sysadmins, DBAs, sec ops","Activa cuando: los sistemas TIC fallan o son comprometidos","Ejemplo TechServ: el DRP define paso a paso cómo restaurar la BBDD de nóminas desde el backup en el sitio alternativo, con RTO de 8 horas"];
drpPts.forEach((p,i)=>t(s,p,5.32,1.42+i*0.62,4.18,0.55,{fontSize:11.5,color:WMUT,lineSpacingMultiple:1.35,bullet:true}));

// Footer
r(s,0.45,5.52,9.2,0.06,D,D);
s.addNotes("BCP vs DRP");}

// ─────────────────────────────────────────
// ENS [op.cont.*]
// ─────────────────────────────────────────
{const s=ws("ENS Anexo II — Medidas de continuidad [op.cont.*]","Las 4 medidas del marco operacional de continuidad · Categorías de aplicación");
const measures=[
  {code:"[op.cont.1]",name:"Análisis de impacto",req:"Identificar las funciones esenciales del sistema, sus dependencias y el impacto de su interrupción en el tiempo. Determinar RTO y RPO. Revisar periódicamente y ante cambios significativos.",cat:"BÁSICA/MEDIA/ALTA",iso:"ISO 22301 cl.8.2 · BIA",color:BLU},
  {code:"[op.cont.2]",name:"Plan de continuidad",req:"Documentar los procedimientos para mantener los servicios esenciales y recuperar las funciones críticas dentro de los RTO/RPO establecidos en el BIA. Incluye BCP y DRP.",cat:"MEDIA/ALTA",iso:"ISO 22301 cl.8.4",color:BLU},
  {code:"[op.cont.3]",name:"Pruebas periódicas",req:"Realizar pruebas periódicas de los planes de continuidad para verificar su eficacia. Documentar los resultados. Actualizar los planes según los resultados. Frecuencia mínima: anual.",cat:"MEDIA/ALTA",iso:"ISO 22301 cl.8.6",color:"333333"},
  {code:"[op.cont.4]",name:"Medios alternativos",req:"Disponer de medios alternativos que permitan mantener el servicio en caso de fallo de los medios principales. Puede ser un sitio alternativo, medios manuales o proveedores de backup.",cat:"ALTA",iso:"ISO 22301 cl.8.3",color:"333333"},
];
measures.forEach((m,i)=>{
  const y=1.0+i*1.1;
  r(s,0.45,y,9.1,1.02,i%2===0?G:W,i%2===0?G:W);
  r(s,0.45,y,0.06,1.02,m.color,m.color);
  t(s,m.code,0.6,y+0.08,1.0,0.22,{fontSize:10,color:m.color,bold:true,fontFace:"Calibri"});
  t(s,m.name,0.6,y+0.32,1.5,0.26,{fontSize:11,color:D,bold:true});
  t(s,m.req,2.22,y+0.1,5.05,0.82,{fontSize:11.5,color:D,lineSpacingMultiple:1.35});
  r(s,7.32,y+0.1,0.92,0.3,"8B1A1A","8B1A1A");
  t(s,m.cat,7.34,y+0.12,0.88,0.26,{fontSize:8.5,color:W,bold:true,align:"center",valign:"middle"});
  t(s,m.iso,7.32,y+0.48,1.65,0.42,{fontSize:9,color:MUT,lineSpacingMultiple:1.3});
});
r(s,0.45,5.42,9.1,0.14,D,D);
t(s,"Para TechServ (sistemas ALTA): las 4 medidas son obligatorias · [op.cont.1] aplica también en BÁSICA",0.65,5.43,8.7,0.12,{fontSize:10,color:WMUT,valign:"middle"});
s.addNotes("ENS [op.cont.*]");}

// ─────────────────────────────────────────
// ISO 22301
// ─────────────────────────────────────────
{const s=ws("ISO 22301 — El estándar de gestión de la continuidad de negocio","Cómo se relaciona con ISO 27001 y el ENS · No es obligatorio pero es la referencia");
// 2 columns
r(s,0.45,0.95,4.55,4.42,G,G);
t(s,"¿Qué es ISO 22301?",0.62,1.04,4.22,0.3,{fontSize:13,color:D,bold:true});
t(s,"Estándar internacional para Sistemas de Gestión de la Continuidad de Negocio (BCMS). Define los requisitos para planificar, establecer, implementar, operar, monitorizar, revisar, mantener y mejorar los planes de continuidad.\n\nEs certificable independientemente de ISO 27001.\n\nComparte la estructura HLS (High Level Structure) con ISO 27001 — mismas cláusulas 4-10, mismo ciclo PDCA.",0.62,1.42,4.22,3.8,{fontSize:12,color:D,lineSpacingMultiple:1.55});
r(s,5.18,0.95,4.42,4.42,D,D);
t(s,"ISO 27001 · ISO 22301 · ENS",5.36,1.04,4.08,0.3,{fontSize:13,color:W,bold:true});
const rels=[
  {t:"ISO 27001",d:"Cubre la SI incluyendo la continuidad de la SI (A.5.29, A.5.30). No cubre continuidad de negocio integral."},
  {t:"ISO 22301",d:"Cubre la continuidad del negocio completo. Incluye SI pero también procesos, personas, instalaciones."},
  {t:"ENS [op.cont.*]",d:"Requiere los elementos clave de BCM (BIA, BCP, DRP, pruebas) para sistemas MEDIA y ALTA. ISO 22301 es la referencia para cumplirlos."},
  {t:"Relación",d:"ISO 27001 + ISO 22301 son complementarios. Muchas organizaciones maduran primero en ISO 27001 y luego certifican ISO 22301."},
];
rels.forEach((rel,i)=>{
  r(s,5.3,1.42+i*0.82,4.12,0.74,DG,DG);
  t(s,rel.t,5.46,1.5+i*0.82,1.2,0.22,{fontSize:10,color:TEA,bold:true});
  t(s,rel.d,5.46,1.74+i*0.82,3.82,0.38,{fontSize:10.5,color:WMUT,lineSpacingMultiple:1.3});
});
s.addNotes("ISO 22301");}

// ─────────────────────────────────────────
// EJERCICIO BIA TECHSERV
// ─────────────────────────────────────────
{const s=pres.addSlide();dk(s);
t(s,"Ejercicio · 8 minutos",0.65,0.48,8,0.28,{fontSize:12,color:SMUT,bold:true,charSpacing:2});
t(s,"BIA básico para TechServ",0.65,0.84,9,0.58,{fontSize:34,color:W,bold:true});
t(s,"Construid el análisis de impacto para los 3 sistemas principales de TechServ",0.65,1.5,9,0.3,{fontSize:13,color:WMUT});
r(s,0.5,1.92,9.1,3.0,DG,DG);
// BIA blank table
const bCols=["Sistema","Función crítica","Impacto 1h","Impacto 24h","RTO objetivo","RPO objetivo","Dependencias TI"];
const bW=[1.5,1.55,0.95,0.95,0.85,0.85,1.0];
const bX=[0.62,2.15,3.73,4.71,5.69,6.57,7.45];
bCols.forEach((h,i)=>{r(s,bX[i],1.98,bW[i]-0.03,0.28,D,D);t(s,h,bX[i]+0.04,1.98,bW[i]-0.06,0.28,{fontSize:7.5,color:W,bold:true,valign:"middle"});});
const systems=["Sistema de nóminas","Sistema de expedientes","Sede electrónica"];
systems.forEach((sys,i)=>{
  const sy=2.3+i*0.6;
  r(s,0.62,sy,8.83,0.54,i%2===0?"2D2D2D":"222222",i%2===0?"2D2D2D":"222222");
  t(s,sys,0.66,sy+0.12,1.45,0.28,{fontSize:10.5,color:W,bold:true});
  ["?","?","?","?","?","?"].forEach((v,vi)=>t(s,v,bX[vi+1]+0.28,sy+0.12,0.4,0.28,{fontSize:14,color:SMUT,align:"center"}));
});
r(s,0.5,5.02,9.1,0.6,D,D);
t(s,"Pista: usad los RTO/RPO que definisteis en el análisis de riesgo de S2/S3 como punto de partida. Para la columna de impacto pensad en consecuencias legales (ENS), operativas (servicios a ciudadanos) y reputacionales.",0.7,5.06,8.7,0.5,{fontSize:11,color:WMUT,lineSpacingMultiple:1.35});
s.addNotes("EJERCICIO BIA");}

// ─────────────────────────────────────────
// 5 IDEAS + PREVIEW S6
// ─────────────────────────────────────────
{const s=pres.addSlide();dk(s);
t(s,"5 ideas para llevarse de la Sesión 5",0.65,0.35,9,0.52,{fontSize:29,color:W,bold:true});
const ideas=[
  {t:"A.8.13 sin prueba de restauración = no backup","d":"Backups sin restauración probada es seguridad ficticia. El auditor pide el último resultado de restauración con fecha. Sin eso, el control no existe."},
  {t:"Etapa 1 documental, Etapa 2 evidencias","d":"Si Etapa 1 falla, no hay Etapa 2. Si Etapa 2 tiene NC mayor, el certificado espera. La diferencia entre ambas: documentación vs. realidad implementada."},
  {t:"RTO < MAD siempre","d:"El tiempo de recuperación debe ser menor que el tiempo máximo de interrupción tolerable. Si no, el daño es irreversible antes de recuperarse."},
  {t:"BCP ≠ DRP","d:"El DRP recupera los sistemas. El BCP garantiza que el negocio sigue funcionando mientras los sistemas se recuperan. Necesitas los dos."},
  {t:"[op.cont.1] aplica a TODAS las categorías ENS","d:"El BIA es obligatorio para BÁSICA, MEDIA y ALTA. No hay excepción. Es el único control de continuidad que aplica incluso a sistemas de bajo riesgo."},
];
ideas.forEach((id,i)=>{
  const x=0.45+(i%3)*3.18,y=i<3?1.02:3.0,w=i>=3?4.72:3.0,xf=i===3?0.45:i===4?5.27:x;
  r(s,xf,y,w,1.78,DG,DG);
  t(s,""+(i+1),xf+0.15,y+0.1,0.38,0.32,{fontSize:12,color:WMUT,bold:true});
  t(s,id.t,xf+0.15,y+0.46,w-0.3,0.3,{fontSize:12,color:W,bold:true,lineSpacingMultiple:1.1});
  t(s,id.d,xf+0.15,y+0.82,w-0.3,0.88,{fontSize:10.5,color:WMUT,lineSpacingMultiple:1.35});
});
r(s,0.45,4.87,9.1,0.62,D,D);
t(s,"Próxima sesión S6 — Continuidad de Negocio completo:",0.65,4.9,3.5,0.24,{fontSize:11,color:TEA,bold:true});
t(s,"Taller: BCP y DRP completos para TechServ · Pruebas de continuidad · ISO 22301 en profundidad · Gestión de crisis · Ejercicio de simulacro tabletop",4.28,4.9,5.1,0.55,{fontSize:10.5,color:WMUT,lineSpacingMultiple:1.35});
s.addNotes("CIERRE S5");}

pres.writeFile({fileName:"S5_A8_Cert_BCM.pptx"})
  .then(()=>console.log("✓ Presentación generada: S5_A8_Cert_BCM.pptx"))
  .catch(e=>console.error("Error:",e));
