"""Persistencia y validación de la base de conocimiento."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Rule
from ..domain.rules import RULES, SUPPORTED_CONDITIONS, RuleDefinition

logger = logging.getLogger(__name__)


def seed_rules(db: Session) -> None:
    """Carga R01-R15 una sola vez; conserva ediciones y activaciones posteriores."""
    for definition in RULES:
        if db.get(Rule, definition.id) is None:
            db.add(Rule(
                id=definition.id,
                name=definition.name,
                description=definition.description,
                priority=definition.priority,
                active=True,
                definition={
                    "condition": definition.condition,
                    "conclusion": definition.conclusion,
                    "recommendation": definition.recommendation,
                },
            ))
    db.commit()


def active_rules(db: Session) -> list[RuleDefinition]:
    rows = db.scalars(select(Rule).where(Rule.active.is_(True)).order_by(Rule.priority, Rule.id)).all()
    definitions = []
    for row in rows:
        payload = row.definition
        if not isinstance(payload, dict) or payload.get("condition") not in SUPPORTED_CONDITIONS:
            logger.warning("Invalid rule definition for %s; skipping", row.id)
            continue
        definitions.append(RuleDefinition(
            id=row.id,
            name=row.name,
            description=row.description,
            priority=row.priority,
            condition=payload["condition"],
            conclusion=payload.get("conclusion"),
            recommendation=payload.get("recommendation"),
        ))
    return definitions
