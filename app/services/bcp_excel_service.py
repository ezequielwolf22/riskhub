"""Servicio de importación/exportación Excel para el módulo BCP."""
import html
import io
import logging

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.bcp_excel")

_HEADER_FILL = PatternFill("solid", fgColor="59008D")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")


def _write_header(ws, headers: list[str]) -> None:
    ws.append(headers)
    for col, cell in enumerate(ws[1], 1):
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 22
    ws.row_dimensions[1].height = 30


def generate_excel_template() -> bytes:
    """Genera la plantilla Excel BCP para importación."""
    wb = openpyxl.Workbook()

    # Hoja 1: Procesos BIA
    ws_proc = wb.active
    ws_proc.title = "Procesos"
    _write_header(ws_proc, [
        "Nombre *", "Criticidad (critical/high/medium/low)",
        "RTO (horas)", "RPO (horas)", "MTPD (horas)",
        "Descripcion", "Propietario (email)", "Prioridad",
    ])
    ws_proc.append(["Proceso ERP", "critical", 4, 1, 8,
                    "Sistema ERP principal de la organización", "admin@empresa.com", 1])
    ws_proc.append(["Portal clientes", "high", 8, 4, 24,
                    "Portal web de atención al cliente", "", 2])
    ws_proc.append(["Backup diario", "medium", 24, 4, 48,
                    "Proceso de respaldo de datos", "", 3])

    # Hoja 2: Dependencias
    ws_dep = wb.create_sheet("Dependencias")
    _write_header(ws_dep, [
        "Proceso (nombre exacto) *",
        "Tipo (IT_system/personnel/facility/supplier/utility/communication/transport/external_service) *",
        "Nombre dependencia *", "RTO necesario (horas)", "Es critico (si/no)",
    ])
    ws_dep.append(["Proceso ERP", "IT_system", "Servidor base de datos principal", 2, "si"])
    ws_dep.append(["Proceso ERP", "personnel", "DBA Senior", 4, "si"])
    ws_dep.append(["Portal clientes", "IT_system", "Servidor web", 4, "si"])

    # Hoja 3: Proveedores BCM
    ws_sup = wb.create_sheet("Proveedores BCM")
    _write_header(ws_sup, [
        "Proveedor (nombre exacto en sistema) *",
        "Criticidad BCM (critical/high/medium/low)",
        "RTO impacto (horas)",
    ])
    ws_sup.append(["AWS", "critical", 1])
    ws_sup.append(["Microsoft 365", "high", 4])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_excel_preview(content: bytes) -> dict:
    """Parsea el Excel BCP y devuelve preview con errores."""
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    errors = []
    processes = []
    dependencies = []
    suppliers = []

    # -- Procesos --
    if "Procesos" in wb.sheetnames:
        ws = wb["Procesos"]
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not row or not row[0]:
                continue
            name = str(row[0]).strip()
            if not name:
                continue
            crit = str(row[1]).strip().lower() if len(row) > 1 and row[1] else "medium"
            if crit not in ("critical", "high", "medium", "low"):
                # html.escape previene XSS cuando el error se renderiza en el frontend
                errors.append(f"Procesos fila {i}: criticidad inválida '{html.escape(crit)}'")
                crit = "medium"
            processes.append({
                "name": name,
                "criticality": crit,
                "rto_hours": _safe_int(row[2]) if len(row) > 2 else None,
                "rpo_hours": _safe_int(row[3]) if len(row) > 3 else None,
                "mtpd_hours": _safe_int(row[4]) if len(row) > 4 else None,
                "description": str(row[5]).strip() if len(row) > 5 and row[5] else None,
                "owner_email": str(row[6]).strip() if len(row) > 6 and row[6] else None,
                "priority": _safe_int(row[7]) if len(row) > 7 else None,
            })
    else:
        errors.append("Hoja 'Procesos' no encontrada en el archivo")

    # -- Dependencias --
    if "Dependencias" in wb.sheetnames:
        ws = wb["Dependencias"]
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not row or not row[0]:
                continue
            dependencies.append({
                "process_name": str(row[0]).strip() if row[0] else "",
                "dependency_type": str(row[1]).strip() if len(row) > 1 and row[1] else "IT_system",
                "name": str(row[2]).strip() if len(row) > 2 and row[2] else "",
                "rto_hours": _safe_int(row[3]) if len(row) > 3 else None,
                "is_critical": str(row[4]).strip().lower() in ("si", "yes", "true", "1")
                    if len(row) > 4 and row[4] else False,
            })

    # -- Proveedores BCM --
    if "Proveedores BCM" in wb.sheetnames:
        ws = wb["Proveedores BCM"]
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not row or not row[0]:
                continue
            crit = str(row[1]).strip().lower() if len(row) > 1 and row[1] else "medium"
            if crit not in ("critical", "high", "medium", "low"):
                crit = "medium"
            suppliers.append({
                "supplier_name": str(row[0]).strip(),
                "criticality": crit,
                "rto_impact_hours": _safe_int(row[2]) if len(row) > 2 else None,
            })

    return {
        "errors": errors,
        "summary": {
            "processes_found": len(processes),
            "dependencies_found": len(dependencies),
            "suppliers_found": len(suppliers),
        },
        "processes": processes[:3],   # solo primeras 3 filas para preview UI
        "all_processes": processes,
        "all_dependencies": dependencies,
        "all_suppliers": suppliers,
    }


def confirm_excel_import(db: Session, preview: dict, org_id: int) -> dict:
    """Crea los registros en BD a partir del preview parseado."""
    from app.models import BusinessProcess, BCPDependency, BCPSupplierLink, Supplier, User

    created = {"processes": 0, "dependencies": 0, "supplier_links": 0}
    proc_map: dict[str, int] = {}  # nombre → id

    # Crear procesos
    for pd in preview.get("all_processes", []):
        name = pd["name"]
        existing = db.query(BusinessProcess).filter_by(
            organization_id=org_id, name=name
        ).first()
        if existing:
            proc_map[name] = existing.id
            continue
        owner = None
        if pd.get("owner_email"):
            owner = db.query(User).filter_by(email=pd["owner_email"]).first()
        p = BusinessProcess(
            organization_id=org_id,
            name=name,
            criticality=pd.get("criticality", "medium"),
            rto_hours=pd.get("rto_hours"),
            rpo_hours=pd.get("rpo_hours"),
            mtpd_hours=pd.get("mtpd_hours"),
            description=pd.get("description"),
            priority=pd.get("priority"),
            owner_id=owner.id if owner else None,
        )
        db.add(p)
        db.flush()
        proc_map[name] = p.id
        created["processes"] += 1

    # Crear dependencias
    for dd in preview.get("all_dependencies", []):
        proc_id = proc_map.get(dd.get("process_name", ""))
        if not proc_id or not dd.get("name"):
            continue
        dep = BCPDependency(
            organization_id=org_id,
            process_id=proc_id,
            dependency_type=dd.get("dependency_type", "IT_system"),
            name=dd["name"],
            rto_hours=dd.get("rto_hours"),
            is_critical=dd.get("is_critical", False),
        )
        db.add(dep)
        created["dependencies"] += 1

    # Crear vínculos de proveedor BCM
    for sd in preview.get("all_suppliers", []):
        sup = db.query(Supplier).filter_by(
            organization_id=org_id, name=sd["supplier_name"]
        ).first()
        if not sup:
            continue
        already = db.query(BCPSupplierLink).filter_by(
            organization_id=org_id, supplier_id=sup.id
        ).first()
        if already:
            continue
        sl = BCPSupplierLink(
            organization_id=org_id,
            supplier_id=sup.id,
            criticality=sd.get("criticality", "medium"),
            rto_impact_hours=sd.get("rto_impact_hours"),
        )
        db.add(sl)
        created["supplier_links"] += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Excel import rollback: %s", exc)
        raise ValueError(f"Error guardando datos: {exc}") from exc

    return created


def _safe_int(val) -> int | None:
    try:
        return int(float(str(val))) if val is not None else None
    except (ValueError, TypeError):
        return None
