"""Sprint 6 final integration test (no password hashing required)."""
import os, sys, tempfile

tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tf.close()
os.environ.update({
    "RISKHUB_DATABASE_URL": f"sqlite:///{tf.name}",
    "RISKHUB_SECRET_KEY":   "test-key-32-chars-padding-needed!",
    "RISKHUB_ENV":          "development",
})

sys.path.insert(0, ".")
import sqlalchemy as sa

# Import models BEFORE create_all so metadata is populated
from app.models import (
    Organization, User, Control, ControlImplementation,
    Policy, PolicyStatus, BCPPlan, ComplianceFrameworkStatus,
    TenantChangeInboxItem,
)
from app.database import Base, engine, SessionLocal
Base.metadata.create_all(bind=engine)

db = SessionLocal()

org = Organization(name="Test Org", plan="enterprise")
db.add(org); db.flush()

user = User(
    organization_id=org.id, email="admin@test.com", full_name="Test Admin",
    hashed_password="$2b$12$placeholder", role="admin", is_active=True,
)
db.add(user); db.flush()

ctrl = Control(
    code="8.10", name="Eliminacion de informacion",
    description="Descripcion original", theme="technological",
)
db.add(ctrl); db.flush()
db.commit()
print(f"OK: org={org.name!r}, ctrl={ctrl.code}")

impl = ControlImplementation(
    organization_id=org.id, control_id=ctrl.id, name="Impl test", status="planned"
)
pol = Policy(
    organization_id=org.id, code="POL-TEST", title="SGSI Test",
    status=PolicyStatus.PUBLISHED, iso_clauses=["8.10"],
)
plan = BCPPlan(
    organization_id=org.id, code="BCP-TEST", name="BCP Test",
    plan_type="bcp", status="approved"
)
req = ComplianceFrameworkStatus(
    organization_id=org.id, framework_code="iso27001",
    requirement_id="8.10", status="implemented",
)
db.add_all([impl, pol, plan, req]); db.commit()
impl_id, pol_id, plan_id, req_id = impl.id, pol.id, plan.id, req.id
print(f"IDs: impl={impl_id}, pol={pol_id}, plan={plan_id}, req={req_id}")

# -- regwatch setup --------------------------------------------------------
from app.services.regwatch_service import (
    get_or_create_settings, create_and_publish_pack, review_inbox_item
)
from app.services.regwatch_propagation import compute_full_impact

s = get_or_create_settings(db, org.id)
s.is_enabled = True
db.commit()

pack = create_and_publish_pack(
    db,
    framework_code="ISO_27001",
    severity="breaking",
    title_es="ISO 27001:2024",
    description_es="Control 8.10 modificado",
    controls_modified=[{
        "control_id": "8.10",
        "field": "description",
        "before": "Descripcion original",
        "after": "Borrado seguro v2",
    }],
)
db.commit()
pack_id = pack.id
print(f"Pack id={pack_id}")

item = db.query(TenantChangeInboxItem).filter_by(organization_id=org.id).first()
assert item, "No inbox item created by create_and_publish_pack"

# -- impact preview --------------------------------------------------------
impact = compute_full_impact(db, org.id, pack)
print(f"Impact: {impact}")
assert impact["control_implementations"] >= 1, f"Expected CI>=1: {impact}"
assert impact["bcp_plans"] >= 1, f"Expected BCP>=1: {impact}"
assert impact["compliance_requirements"] >= 1, f"Expected req>=1: {impact}"

# -- apply change ----------------------------------------------------------
result = review_inbox_item(db, org.id, item.id, user, {"action": "apply"})
db.commit()
print(f"Result: {result}")

prop = result["propagation"]
assert prop["control_implementations_flagged"] >= 1, f"CI: {prop}"
assert prop["policies_flagged"] >= 1, f"Policies: {prop}"
assert prop["bcp_plans_flagged"] >= 1, f"BCP: {prop}"
assert prop["compliance_requirements_flagged"] >= 1, f"Req: {prop}"

# -- verify DB state -------------------------------------------------------
def q(sql, **kw):
    return db.execute(sa.text(sql), kw).fetchone()

ci = q("SELECT regwatch_review_at FROM control_implementations WHERE id=:id", id=impl_id)
p  = q("SELECT regwatch_review_at, status FROM policies WHERE id=:id", id=pol_id)
bp = q("SELECT regwatch_review_at, status FROM bcp_plans WHERE id=:id", id=plan_id)
rq = q("SELECT regwatch_review_at FROM compliance_framework_status WHERE id=:id", id=req_id)
c  = q("SELECT description FROM controls WHERE code=:c", c="8.10")
pk = q("SELECT applied_to_catalog_at FROM regwatch_change_packs WHERE id=:id", id=pack_id)

assert ci[0] is not None, "ControlImplementation not flagged"
assert p[0]  is not None, "Policy not flagged"
assert p[1].lower() == "review", f"Policy status={p[1]}, expected 'review'"
assert bp[0] is not None, "BCPPlan not flagged"
assert bp[1] == "under_review", f"BCP status={bp[1]}, expected 'under_review'"
assert rq[0] is not None, "ComplianceFrameworkStatus not flagged"
assert c[0]  == "Borrado seguro v2", f"Control description not updated: {c[0]}"
assert pk[0] is not None, "ChangePack.applied_to_catalog_at not set"

print()
print("[CI ]", ci[0])
print("[POL]", p[0], "| status:", p[1])
print("[BCP]", bp[0], "| status:", bp[1])
print("[REQ]", rq[0])
print("[CTL]", c[0])
print()
print("=== SPRINT 6 FULL INTEGRATION: ALL ASSERTIONS PASSED ===")

db.close()
engine.dispose()
try:
    os.unlink(tf.name)
except PermissionError:
    pass  # Windows: SQLite may keep the file handle briefly
