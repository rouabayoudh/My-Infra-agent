"""
security.py — Couche de validation OBLIGATOIRE avant toute opération
sur une VM. Aucune fonction de bridge.py ne doit appeler vmrun ou
l'API REST sans être passée par ce module en amont.

Principe : on ne fait JAMAIS confiance à une chaîne de caractères
venant de l'extérieur (LLM, ligne de commande, Terraform) tant
qu'elle n'a pas été validée ici.
"""

import re
from pathlib import Path

from config import NAMING_PATTERN, VMS_BASE_DIR, TEMPLATES_BASE_DIR


class SecurityError(Exception):
    """Levée pour toute tentative d'opération non sécurisée."""
    pass


_NAME_RE = re.compile(NAMING_PATTERN)


def validate_vm_name(name: str) -> str:
    """
    Vérifie que le nom de VM respecte strictement la convention
    de gouvernance : srv-{environnement}-{role}-{index}

    Lève SecurityError si le nom est invalide ou contient des
    caractères dangereux. Retourne le nom si valide.
    """
    if not isinstance(name, str) or not name:
        raise SecurityError("Nom de VM vide ou invalide.")

    # Première barrière : seuls les caractères attendus existent
    # dans le pattern lui-même, donc tout ce qui matche le regex
    # est par construction sans caractère spécial dangereux.
    if not _NAME_RE.match(name):
        raise SecurityError(
            f"Nom de VM '{name}' ne respecte pas la convention "
            f"'srv-{{dev|staging|prod}}-{{role}}-{{index}}' "
            f"(ex: srv-dev-web-01)."
        )

    return name


def safe_vm_path(vm_name: str) -> Path:
    """
    Construit le chemin .vmx d'une VM gérée par InfraAgent,
    en garantissant qu'il reste contenu dans VMS_BASE_DIR.

    Lève SecurityError en cas de tentative de path traversal.
    """
    validate_vm_name(vm_name)

    candidate = (VMS_BASE_DIR / vm_name / f"{vm_name}.vmx").resolve()

    if not str(candidate).startswith(str(VMS_BASE_DIR)):
        raise SecurityError(
            f"Path traversal détecté pour '{vm_name}': "
            f"{candidate} sort de {VMS_BASE_DIR}"
        )

    return candidate


def safe_template_path(template_id: str) -> Path:
    """
    Construit le chemin .vmx d'un template, en garantissant qu'il
    reste contenu dans TEMPLATES_BASE_DIR.

    template_id est volontairement validé de façon plus permissive
    que le nom de VM (les templates ne suivent pas la convention
    srv-*), mais on bloque toujours tout caractère de traversal.
    """
    if not isinstance(template_id, str) or not template_id:
        raise SecurityError("template_id vide ou invalide.")

    if ".." in template_id or "/" in template_id or "\\" in template_id:
        raise SecurityError(
            f"template_id '{template_id}' contient des caractères "
            f"interdits (path traversal potentiel)."
        )

    if not re.match(r"^[a-zA-Z0-9._-]+$", template_id):
        raise SecurityError(
            f"template_id '{template_id}' contient des caractères "
            f"non autorisés. Seuls lettres, chiffres, '.', '_', '-' "
            f"sont acceptés."
        )

    candidate = (TEMPLATES_BASE_DIR / f"{template_id}.vmx").resolve()

    if not str(candidate).startswith(str(TEMPLATES_BASE_DIR)):
        raise SecurityError(
            f"Path traversal détecté pour template '{template_id}'."
        )

    return candidate


def validate_resources(vcpu: int, ram_gb: int) -> None:
    """
    Vérifie les limites physiques de gouvernance.
    Doit être appelée à la création, indépendamment de ce que le
    LLM a déjà validé en amont — défense en profondeur.
    """
    from config import MAX_VCPU, MAX_RAM_GB

    if not isinstance(vcpu, int) or vcpu < 1 or vcpu > MAX_VCPU:
        raise SecurityError(
            f"vCPU invalide : {vcpu}. Doit être entre 1 et {MAX_VCPU}."
        )

    if not isinstance(ram_gb, int) or ram_gb < 1 or ram_gb > MAX_RAM_GB:
        raise SecurityError(
            f"RAM invalide : {ram_gb} Go. Doit être entre 1 et {MAX_RAM_GB} Go."
        )
