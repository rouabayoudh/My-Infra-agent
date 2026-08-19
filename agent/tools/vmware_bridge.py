"""
vmware_bridge.py — Passerelle entre Terraform (via local-exec) et
VMware Workstation Pro.

Usage en ligne de commande :
    python vmware_bridge.py create <template_id> <vm_name>
    python vmware_bridge.py delete <vm_name>
    python vmware_bridge.py status <vm_name>
    python vmware_bridge.py start <vm_name>
    python vmware_bridge.py stop <vm_name>
    python vmware_bridge.py list

Toutes les opérations passent par security.py AVANT toute exécution
de commande. Aucune exception : pas de raccourci.
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
import subprocess
import logging
from datetime import datetime, timezone

import requests
from requests.auth import HTTPBasicAuth

from config import (
    VMRUN_PATH,
    VMREST_BASE_URL,
    VMREST_USER,
    VMREST_PASSWORD,
    INVENTORY_PATH,
    LOG_PATH,
)
from security import (
    SecurityError,
    validate_vm_name,
    safe_vm_path,
    safe_template_path,
)

# --- Logging ---
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("vmware_bridge")


class BridgeError(Exception):
    """Erreur métier du bridge (distincte d'une erreur de sécurité)."""
    pass


# ---------------------------------------------------------------------
# Couche basse : exécution sécurisée de vmrun
# ---------------------------------------------------------------------

def _run_vmrun(args: list[str], timeout: int = 120) -> str:
    """
    Exécute vmrun avec une LISTE d'arguments (jamais shell=True).
    Retourne stdout. Lève BridgeError en cas d'échec.
    """
    cmd = [VMRUN_PATH, "-T", "ws"] + args
    logger.info(f"Exécution: {cmd}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # JAMAIS True — voir security.py
        )
    except FileNotFoundError:
        raise BridgeError(
            f"vmrun introuvable à {VMRUN_PATH}. "
            f"Vérifie config.py / variable d'env VMRUN_PATH."
        )
    except subprocess.TimeoutExpired:
        raise BridgeError(f"vmrun a dépassé le timeout de {timeout}s.")

    if result.returncode != 0:
        logger.error(f"vmrun a échoué: {result.stderr.strip()}")
        raise BridgeError(f"vmrun a échoué: {result.stderr.strip()}")

    logger.info(f"vmrun OK: {result.stdout.strip()}")
    return result.stdout


# ---------------------------------------------------------------------
# Couche basse : appels API REST (vmrest)
# ---------------------------------------------------------------------

def _vmrest_get(path: str) -> dict | list:
    url = f"{VMREST_BASE_URL}{path}"
    headers = {"Accept": "application/vnd.vmware.vmw.rest-v1+json"}
    try:
        resp = requests.get(
            url,
            headers=headers,
            auth=HTTPBasicAuth(VMREST_USER, VMREST_PASSWORD),
            timeout=15,
        )
    except requests.exceptions.ConnectionError:
        raise BridgeError(
            "Impossible de joindre vmrest. Le service est-il démarré "
            "(vmrest.exe) ?"
        )

    if resp.status_code != 200:
        raise BridgeError(f"vmrest GET {path} -> HTTP {resp.status_code}: {resp.text}")

    return resp.json()


def _vmrest_put_power(vm_id: str, state: str) -> None:
    url = f"{VMREST_BASE_URL}/vms/{vm_id}/power"
    headers = {"Content-Type": "application/vnd.vmware.vmw.rest-v1+json"}
    resp = requests.put(
        url,
        headers=headers,
        auth=HTTPBasicAuth(VMREST_USER, VMREST_PASSWORD),
        data=state,
        timeout=30,
    )
    if resp.status_code != 200:
        raise BridgeError(f"vmrest PUT power -> HTTP {resp.status_code}: {resp.text}")


def _vmrest_find_vm_id(vmx_path: str) -> str | None:
    """
    L'API REST identifie les VMs par un id généré, pas par leur nom.
    On doit toujours retrouver l'id à partir du chemin .vmx connu.
    """
    vms = _vmrest_get("/vms")
    for vm in vms:
        # Comparaison insensible à la casse, Windows ne distingue pas
        if vm.get("path", "").lower() == vmx_path.lower():
            return vm["id"]
    return None


# ---------------------------------------------------------------------
# Inventaire (source de vérité locale)
# ---------------------------------------------------------------------

def _load_inventory() -> dict:
    if not INVENTORY_PATH.exists():
        return {}
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_inventory(inv: dict) -> None:
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2, ensure_ascii=False)


def _update_inventory(vm_name: str, **fields) -> None:
    inv = _load_inventory()
    entry = inv.get(vm_name, {})
    entry.update(fields)
    entry["last_updated"] = datetime.now(timezone.utc).isoformat()
    inv[vm_name] = entry
    _save_inventory(inv)


def _remove_from_inventory(vm_name: str) -> None:
    inv = _load_inventory()
    if vm_name in inv:
        del inv[vm_name]
        _save_inventory(inv)


# ---------------------------------------------------------------------
# Opérations exposées (appelées depuis main())
# ---------------------------------------------------------------------

def create(template_id: str, vm_name: str) -> None:
    """Clone un template vers une nouvelle VM, puis l'allume."""
    validate_vm_name(vm_name)
    template_path = safe_template_path(template_id)
    dest_path = safe_vm_path(vm_name)

    if not template_path.exists():
        raise BridgeError(f"Template introuvable: {template_path}")

    if dest_path.exists():
        raise BridgeError(
            f"La VM '{vm_name}' existe déjà à {dest_path}. "
            f"Utilise delete d'abord si tu veux la recréer."
        )

    logger.info(f"Clonage {template_path} -> {dest_path}")
    _run_vmrun([
        "clone",
        str(template_path),
        str(dest_path),
        "full",
        f"-cloneName={vm_name}",
    ])

    logger.info(f"Démarrage de {vm_name}")
    _run_vmrun(["start", str(dest_path), "nogui"])

    _update_inventory(
        vm_name,
        status="PoweredOn",
        template=template_id,
        vmx_path=str(dest_path),
        created_at=datetime.now(timezone.utc).isoformat(),
        expected_state="running",
    )

    print(f"[OK] VM '{vm_name}' créée et démarrée depuis le template '{template_id}'.")


def delete(vm_name: str) -> None:
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)

    if not vmx_path.exists():
        logger.warning(f"delete: '{vm_name}' deja absent, no-op.")
        _remove_from_inventory(vm_name)
        print(f"[OK] VM '{vm_name}' deja absente (no-op).")
        return

    # Supprimer les verrous VMware avant toute operation
    vm_dir = vmx_path.parent
    for lck in vm_dir.glob("*.lck"):
        try:
            import shutil
            shutil.rmtree(lck)
            logger.info(f"Verrou supprime: {lck}")
        except Exception as e:
            logger.warning(f"Impossible de supprimer {lck}: {e}")

    # Extinction : soft d'abord, hard en fallback
    try:
        _run_vmrun(["stop", str(vmx_path), "soft"])
    except BridgeError:
        try:
            _run_vmrun(["stop", str(vmx_path), "hard"])
        except BridgeError as e:
            logger.warning(f"stop hard aussi echoue: {e}")

    # Suppression
    _run_vmrun(["deleteVM", str(vmx_path)])
    _remove_from_inventory(vm_name)
    print(f"[OK] VM '{vm_name}' arretee et supprimee.")

def status(vm_name: str) -> str:
    """
    Retourne l'état réel de la VM en interrogeant vmrun list
    (VMs en cours d'exécution) — vmrun ne liste pas les VMs
    éteintes, donc on déduit l'état via l'existence du fichier
    + présence dans la liste des VMs actives.
    """
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)

    if not vmx_path.exists():
        return "NotFound"

    running_output = _run_vmrun(["list"])
    is_running = str(vmx_path).lower() in running_output.lower()

    state = "PoweredOn" if is_running else "PoweredOff"
    _update_inventory(vm_name, status=state)
    return state


def start(vm_name: str) -> None:
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)
    if not vmx_path.exists():
        raise BridgeError(f"VM '{vm_name}' introuvable, impossible de démarrer.")
    _run_vmrun(["start", str(vmx_path), "nogui"])
    _update_inventory(vm_name, status="PoweredOn")
    print(f"[OK] VM '{vm_name}' démarrée.")


def stop(vm_name: str) -> None:
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)
    if not vmx_path.exists():
        raise BridgeError(f"VM '{vm_name}' introuvable, impossible d'arrêter.")
    _run_vmrun(["stop", str(vmx_path), "soft"])
    _update_inventory(vm_name, status="PoweredOff")
    print(f"[OK] VM '{vm_name}' arrêtée.")

def snapshot(vm_name: str, snapshot_name: str) -> None:
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)
    if not vmx_path.exists():
        raise BridgeError(f"VM '{vm_name}' introuvable.")
    _run_vmrun(["snapshot", str(vmx_path), snapshot_name])
    _update_inventory(vm_name, last_snapshot=snapshot_name)
    print(f"[OK] Snapshot '{snapshot_name}' cree pour '{vm_name}'.")


def list_snapshots(vm_name: str) -> None:
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)
    if not vmx_path.exists():
        raise BridgeError(f"VM '{vm_name}' introuvable.")
    output = _run_vmrun(["listSnapshots", str(vmx_path)])
    print(output)


def revert_snapshot(vm_name: str, snapshot_name: str) -> None:
    validate_vm_name(vm_name)
    vmx_path = safe_vm_path(vm_name)
    if not vmx_path.exists():
        raise BridgeError(f"VM '{vm_name}' introuvable.")
    _run_vmrun(["revertToSnapshot", str(vmx_path), snapshot_name])
    print(f"[OK] VM '{vm_name}' restauree au snapshot '{snapshot_name}'.")
    
def list_all() -> None:
    """Liste l'inventaire local connu (pas uniquement les VMs actives)."""
    inv = _load_inventory()
    print(json.dumps(inv, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1]

    try:
        if command == "create":
            if len(sys.argv) != 4:
                raise BridgeError("Usage: create <template_id> <vm_name>")
            create(sys.argv[2], sys.argv[3])

        elif command == "delete":
            if len(sys.argv) != 3:
                raise BridgeError("Usage: delete <vm_name>")
            delete(sys.argv[2])

        elif command == "status":
            if len(sys.argv) != 3:
                raise BridgeError("Usage: status <vm_name>")
            print(status(sys.argv[2]))

        elif command == "start":
            if len(sys.argv) != 3:
                raise BridgeError("Usage: start <vm_name>")
            start(sys.argv[2])

        elif command == "stop":
            if len(sys.argv) != 3:
                raise BridgeError("Usage: stop <vm_name>")
            stop(sys.argv[2])
        elif command == "snapshot":
            if len(sys.argv) != 4:
                raise BridgeError("Usage: snapshot <vm_name> <snapshot_name>")
            snapshot(sys.argv[2], sys.argv[3])

        elif command == "list_snapshots":
            if len(sys.argv) != 3:
                raise BridgeError("Usage: list_snapshots <vm_name>")
            list_snapshots(sys.argv[2])

        elif command == "revert_snapshot":
            if len(sys.argv) != 4:
                raise BridgeError("Usage: revert_snapshot <vm_name> <snapshot_name>")
            revert_snapshot(sys.argv[2], sys.argv[3])   

        elif command == "list":
            list_all()

        else:
            print(f"Commande inconnue: {command}")
            print(__doc__)
            return 1

    except SecurityError as e:
        logger.error(f"SECURITY VIOLATION: {e}")
        print(f"[ERREUR] Refusé (sécurité): {e}", file=sys.stderr)
        return 2

    except BridgeError as e:
        logger.error(f"BRIDGE ERROR: {e}")
        print(f"[ERREUR] Erreur: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
