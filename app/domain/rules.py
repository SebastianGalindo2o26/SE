"""Base declarativa de reglas y motor de encadenamiento hacia adelante."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    description: str
    priority: int
    condition: str
    conclusion: str | None = None
    recommendation: str | None = None


RULES = [
    RuleDefinition("R01", "Servicio disponible", "HTTP esperado dentro del umbral de latencia", 10, "healthy", "servicio_funcionando"),
    RuleDefinition("R02", "Error interno", "El servidor respondió HTTP 500", 60, "status_500", "error_servidor", "Revisar logs de aplicación y dependencias del backend."),
    RuleDefinition("R03", "Falla de gateway", "El gateway respondió HTTP 502", 55, "status_502", "error_gateway", "Revisar el gateway, proxy y conexión con el servidor de origen."),
    RuleDefinition("R04", "Servicio no disponible", "El servidor respondió HTTP 503", 65, "status_503", "servicio_no_disponible", "Revisar disponibilidad, capacidad y mantenimiento del servicio."),
    RuleDefinition("R05", "Timeout de gateway", "El gateway respondió HTTP 504", 60, "status_504", "timeout_gateway", "Revisar latencia del servidor de origen y límites de espera del gateway."),
    RuleDefinition("R06", "Autenticación requerida", "El servidor respondió HTTP 401", 35, "status_401", "autenticacion_requerida", "Verificar credenciales, token y configuración de autenticación."),
    RuleDefinition("R07", "Acceso prohibido", "El servidor respondió HTTP 403", 35, "status_403", "acceso_prohibido", "Verificar permisos y políticas de acceso para este recurso."),
    RuleDefinition("R08", "Recurso no encontrado", "El servidor respondió HTTP 404", 25, "status_404", "recurso_no_encontrado", "Verificar la URL y la ruta del recurso; un 404 puede ser esperado."),
    RuleDefinition("R09", "Límite de solicitudes", "El servidor respondió HTTP 429", 45, "status_429", "limite_solicitudes", "Reducir la frecuencia de solicitudes y revisar Retry-After."),
    RuleDefinition("R10", "Rendimiento degradado", "HTTP esperado con latencia superior al umbral", 40, "slow", "rendimiento_degradado", "Revisar tiempos de consulta, carga y dependencias externas."),
    RuleDefinition("R11", "Error de conexión", "La solicitud falló por timeout o conexión", 55, "connection_error", "error_conexion", "Verificar conectividad, DNS, TLS y disponibilidad del destino."),
    RuleDefinition("R12", "Falla persistente", "Tres monitoreos recientes consecutivos con 5xx o timeout", 75, "persistent", "falla_persistente", "Investigar el incidente; se observan tres fallas consecutivas."),
    RuleDefinition("R13", "Incidente de prioridad alta: servidor", "HTTP 500 junto con falla persistente", 95, "high_server", "prioridad_alta", "Atender de inmediato; revisar logs, dependencias y cambios recientes."),
    RuleDefinition("R14", "Incidente de prioridad alta: disponibilidad", "HTTP 503 junto con falla persistente", 95, "high_unavailable", "prioridad_alta", "Atender de inmediato; revisar salud, capacidad y estado del proveedor."),
    RuleDefinition("R15", "Revisión inmediata", "Se detectó un incidente de prioridad alta", 100, "high_priority", "revision_inmediata", "Escalar al responsable de guardia y documentar el incidente."),
]
SUPPORTED_CONDITIONS = {rule.condition for rule in RULES}


@dataclass
class InferenceResult:
    facts: dict[str, Any] = field(default_factory=dict)
    fired_rules: list[RuleDefinition] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    severity: str = "informativa"
    summary: str = "No se encontró una regla diagnóstica específica; información insuficiente."


def _matches(rule: RuleDefinition, facts: dict[str, Any]) -> bool:
    status = facts.get("status_code")
    return {
        "healthy": status == facts.get("expected_status") and facts.get("latency_ms") is not None and facts["latency_ms"] <= facts["slow_threshold_ms"],
        "status_500": status == 500 and status != facts.get("expected_status"),
        "status_502": status == 502 and status != facts.get("expected_status"),
        "status_503": status == 503 and status != facts.get("expected_status"),
        "status_504": status == 504 and status != facts.get("expected_status"),
        "status_401": status == 401 and status != facts.get("expected_status"),
        "status_403": status == 403 and status != facts.get("expected_status"),
        "status_404": status == 404 and status != facts.get("expected_status"),
        "status_429": status == 429 and status != facts.get("expected_status"),
        "slow": status == facts.get("expected_status") and facts.get("latency_ms") is not None and facts["latency_ms"] > facts["slow_threshold_ms"],
        "connection_error": bool(facts.get("error_type")),
        "persistent": facts.get("consecutive_failures", 0) >= 3,
        "high_server": status == 500 and status != facts.get("expected_status") and "falla_persistente" in facts["conclusions"],
        "high_unavailable": status == 503 and status != facts.get("expected_status") and "falla_persistente" in facts["conclusions"],
        "high_priority": "prioridad_alta" in facts["conclusions"],
    }[rule.condition]


def infer(initial_facts: dict[str, Any], rules: list[RuleDefinition] | None = None) -> InferenceResult:
    """Aplica reglas hasta que no aparezcan nuevas conclusiones."""
    facts = {**initial_facts, "conclusions": []}
    available = sorted(RULES if rules is None else rules, key=lambda rule: (rule.priority, rule.id))
    fired: list[RuleDefinition] = []
    seen: set[str] = set()
    changed = True
    while changed:
        changed = False
        for rule in available:
            if rule.id in seen or not _matches(rule, facts):
                continue
            seen.add(rule.id)
            fired.append(rule)
            changed = True
            if rule.conclusion and rule.conclusion not in facts["conclusions"]:
                facts["conclusions"].append(rule.conclusion)
    recs = list(dict.fromkeys(r.recommendation for r in fired if r.recommendation))
    if "prioridad_alta" in facts["conclusions"]:
        severity = "alta"
    elif any(c in facts["conclusions"] for c in ("error_servidor", "servicio_no_disponible", "falla_persistente", "error_conexion", "error_gateway", "timeout_gateway")):
        severity = "media"
    elif any(c in facts["conclusions"] for c in ("rendimiento_degradado", "autenticacion_requerida", "acceso_prohibido", "recurso_no_encontrado", "limite_solicitudes")):
        severity = "baja"
    elif "servicio_funcionando" in facts["conclusions"]:
        severity = "normal"
    else:
        severity = "informativa"
    facts["conclusions"] = facts["conclusions"] or []
    labels = [r.name for r in fired]
    summary = "; ".join(labels) if labels else "Información insuficiente para emitir un diagnóstico."
    return InferenceResult(facts=facts, fired_rules=fired, recommendations=recs, severity=severity, summary=summary)
