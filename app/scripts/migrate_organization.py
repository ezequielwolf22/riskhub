#!/usr/bin/env python3
"""
Script de migración de contenido entre organizaciones.

Uso:
  python migrate_organization.py --from-org-id 1 --to-org-id 2

  O desde el servidor:
  docker exec riskhub python -m app.scripts.migrate_organization --from-org-id 1 --to-org-id 2
"""
import sys
import argparse
from datetime import datetime
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# Agregar el directorio padre al path
sys.path.insert(0, '/app')

from app.config import settings
from app.models import (
    Organization, Risk, Asset, Threat, Vulnerability, ControlImplementation,
    Incident, NonConformity, TreatmentTask, Policy, AuditProgram, Supplier,
    ProcessingActivity, DPIA, OSINTFinding, Document, ExternalFinding,
    SupplierQuestionnaire
)


def get_db():
    """Conectar a la BD."""
    engine = create_engine(settings.db_url)
    Session = sessionmaker(bind=engine)
    return Session()


def migrate_organization(from_org_id: int, to_org_id: int):
    """Migra TODO el contenido de una org a otra, excepto configuraciones."""
    db = get_db()

    print(f"\n{'='*70}")
    print(f"MIGRACION DE CONTENIDO: Org #{from_org_id} → Org #{to_org_id}")
    print(f"{'='*70}\n")

    try:
        # Validar orgs
        from_org = db.query(Organization).filter(Organization.id == from_org_id).first()
        to_org = db.query(Organization).filter(Organization.id == to_org_id).first()

        if not from_org:
            print(f"❌ Organización origen #{from_org_id} no existe")
            return False
        if not to_org:
            print(f"❌ Organización destino #{to_org_id} no existe")
            return False

        print(f"📦 Origen: {from_org.name} (#{from_org_id})")
        print(f"📦 Destino: {to_org.name} (#{to_org_id})\n")

        # Confirmar
        response = input("⚠️  Esta operación migrará TODO el contenido. Escribe 'MIGRAR' para continuar: ")
        if response != "MIGRAR":
            print("❌ Migración cancelada")
            return False

        # Crear log
        timestamp = datetime.now().isoformat()
        log_file = f"/tmp/migration_{from_org_id}_to_{to_org_id}_{timestamp.replace(':', '-')}.log"
        log = open(log_file, 'w')

        def log_msg(msg):
            print(msg)
            log.write(msg + "\n")

        log_msg(f"\n[{timestamp}] Iniciando migración...\n")

        # Contar items antes
        stats = {
            'risks': db.query(Risk).filter(Risk.organization_id == from_org_id).count(),
            'assets': db.query(Asset).filter(Asset.organization_id == from_org_id).count(),
            'threats': db.query(Threat).filter(Threat.organization_id == from_org_id).count(),
            'vulns': db.query(Vulnerability).filter(Vulnerability.organization_id == from_org_id).count(),
            'controls': db.query(ControlImplementation).filter(ControlImplementation.organization_id == from_org_id).count(),
            'incidents': db.query(Incident).filter(Incident.organization_id == from_org_id).count(),
            'nonconforms': db.query(NonConformity).filter(NonConformity.organization_id == from_org_id).count(),
            'tasks': db.query(TreatmentTask).filter(TreatmentTask.organization_id == from_org_id).count(),
            'policies': db.query(Policy).filter(Policy.organization_id == from_org_id).count(),
            'audits': db.query(AuditProgram).filter(AuditProgram.organization_id == from_org_id).count(),
            'suppliers': db.query(Supplier).filter(Supplier.organization_id == from_org_id).count(),
            'documents': db.query(Document).filter(Document.organization_id == from_org_id).count(),
            'osint': db.query(OSINTFinding).filter(OSINTFinding.organization_id == from_org_id).count(),
            'activities': db.query(ProcessingActivity).filter(ProcessingActivity.organization_id == from_org_id).count(),
            'dpias': db.query(DPIA).filter(DPIA.organization_id == from_org_id).count(),
        }

        log_msg("📊 CONTENIDO A MIGRAR:")
        total = 0
        for key, count in stats.items():
            if count > 0:
                log_msg(f"  {key}: {count}")
                total += count
        log_msg(f"  TOTAL: {total} items\n")

        if total == 0:
            log_msg("⚠️  No hay contenido para migrar")
            log.close()
            return True

        # Migrar por entidad
        entities = [
            (Risk, "Riesgos"),
            (Asset, "Activos"),
            (Threat, "Amenazas custom"),
            (Vulnerability, "Vulnerabilidades custom"),
            (ControlImplementation, "Implementaciones de controles"),
            (Incident, "Incidentes"),
            (NonConformity, "No conformidades"),
            (TreatmentTask, "Tareas"),
            (Policy, "Políticas"),
            (AuditProgram, "Programas de auditoría"),
            (Supplier, "Proveedores"),
            (Document, "Documentos"),
            (OSINTFinding, "Hallazgos OSINT"),
            (ProcessingActivity, "Actividades RGPD"),
            (DPIA, "DPIAs"),
            (SupplierQuestionnaire, "Cuestionarios de proveedores"),
        ]

        migrated = 0
        for model, label in entities:
            items = db.query(model).filter(model.organization_id == from_org_id).all()
            for item in items:
                item.organization_id = to_org_id
                migrated += 1
            if items:
                log_msg(f"✓ {label}: {len(items)} items")

        db.commit()
        log_msg(f"\n✅ Migración completada: {migrated} items trasladados")
        log_msg(f"📁 Log guardado en: {log_file}\n")

        print(f"\n✅ MIGRACIÓN EXITOSA: {migrated} items trasladados")
        print(f"📁 Log: {log_file}\n")

        log.close()
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migra TODO el contenido entre organizaciones (excepto configuraciones)"
    )
    parser.add_argument("--from-org-id", type=int, required=True, help="ID de org origen")
    parser.add_argument("--to-org-id", type=int, required=True, help="ID de org destino")

    args = parser.parse_args()

    success = migrate_organization(args.from_org_id, args.to_org_id)
    sys.exit(0 if success else 1)
