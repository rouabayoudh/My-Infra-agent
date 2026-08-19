"""
monitor.py — Surveillance en temps réel de l'infrastructure VMware.

Toutes les POLL_INTERVAL secondes :
  1. Lit l'inventaire (état attendu)
  2. Interroge vmware_bridge.py pour l'état réel de chaque VM
  3. Compare les deux
  4. Si anomalie → affiche une alerte et demande validation humaine
  5. Si validé → exécute l'action corrective via le bridge

Usage :
    python agent/monitor.py

Arrêt : Ctrl+C
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime, timezone

# --- Configuration ---
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVENTORY_PATH = os.path.join(BASE_DIR, "agent", "state", "inventory.json")
BRIDGE_PATH    = os.path.join(BASE_DIR, "agent", "tools", "vmware_bridge.py")
POLL_INTERVAL  = 60   # secondes entre chaque vérification
LOG_PATH       = os.path.join(BASE_DIR, "agent", "state", "monitor.log")


# ---------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------

def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(message: str) -> None:
    ligne = f"[{timestamp()}] {message}"
    print(ligne)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(ligne + "\n")


def lire_inventaire() -> dict:
    if not os.path.exists(INVENTORY_PATH):
        return {}
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            log("[WARN] inventory.json illisible ou corrompu.")
            return {}


def appeler_bridge(args: list[str]) -> tuple[int, str]:
    """
    Appelle vmware_bridge.py avec les arguments donnés.
    Retourne (code_retour, sortie_texte).
    """
    result = subprocess.run(
        [sys.executable, BRIDGE_PATH] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=BASE_DIR,
    )
    sortie = (result.stdout + result.stderr).strip()
    return result.returncode, sortie


def get_status_reel(vm_name: str) -> str:
    """
    Retourne l'état réel de la VM : PoweredOn, PoweredOff, NotFound.
    """
    code, sortie = appeler_bridge(["status", vm_name])
    if code != 0:
        return "Unknown"
    # La dernière ligne contient le statut
    lignes = [l.strip() for l in sortie.splitlines() if l.strip()]
    return lignes[-1] if lignes else "Unknown"


# ---------------------------------------------------------------------
# Logique de réconciliation
# ---------------------------------------------------------------------

def analyser_anomalie(vm_name: str, etat_attendu: str, etat_reel: str) -> str:
    """
    Formule un diagnostic clair pour l'opérateur humain.
    """
    if etat_reel == "NotFound":
        return (
            f"CRITIQUE : La VM '{vm_name}' est introuvable sur le système. "
            f"Elle a peut-être été supprimée manuellement depuis VMware. "
            f"Action suggérée : recréer la VM depuis le template."
        )
    elif etat_attendu == "running" and etat_reel == "PoweredOff":
        return (
            f"ALERTE : La VM '{vm_name}' devrait être en cours d'exécution "
            f"mais elle est éteinte. Cause possible : extinction manuelle, "
            f"crash système, ou manque de ressources. "
            f"Action suggérée : rallumer la VM."
        )
    elif etat_attendu == "stopped" and etat_reel == "PoweredOn":
        return (
            f"INFO : La VM '{vm_name}' devrait être éteinte "
            f"mais elle tourne encore. "
            f"Action suggérée : éteindre la VM."
        )
    else:
        return (
            f"ANOMALIE : VM '{vm_name}' — "
            f"état attendu='{etat_attendu}', état réel='{etat_reel}'."
        )


def proposer_action(vm_name: str, etat_attendu: str, etat_reel: str) -> str | None:
    """
    Retourne la commande bridge à exécuter pour corriger l'anomalie,
    ou None si aucune action automatique n'est possible.
    """
    if etat_attendu == "running" and etat_reel in ("PoweredOff", "NotFound"):
        return "start"
    elif etat_attendu == "stopped" and etat_reel == "PoweredOn":
        return "stop"
    return None


def demander_validation(diagnostic: str, action: str, vm_name: str) -> bool:
    """
    Affiche le diagnostic et demande confirmation à l'opérateur.
    Retourne True si l'opérateur valide, False sinon.
    JAMAIS d'action automatique sans validation explicite.
    """
    print("\n" + "=" * 60)
    print("  [ALERTE MONITORING]")
    print("=" * 60)
    print(f"\n  {diagnostic}\n")
    print(f"  Action proposée : {action.upper()} '{vm_name}'")
    print("\n  Tapez 'yes' pour exécuter, autre chose pour ignorer.")
    print("=" * 60)

    try:
        reponse = input("  Votre décision : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    return reponse == "yes"


def executer_correction(action: str, vm_name: str) -> None:
    """
    Exécute l'action corrective via le bridge après validation humaine.
    """
    log(f"[ACTION] Execution : {action} {vm_name}")
    code, sortie = appeler_bridge([action, vm_name])
    if code == 0:
        log(f"[OK] Correction appliquée : {action} {vm_name}")
        print(f"  [OK] {sortie}")
    else:
        log(f"[ERREUR] Correction échouée : {sortie}")
        print(f"  [ERREUR] {sortie}")


# ---------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------

def verifier_infrastructure() -> None:
    """
    Une passe de vérification : compare inventaire vs réalité.
    """
    inventaire = lire_inventaire()

    if not inventaire:
        log("[INFO] Inventaire vide — aucune VM à surveiller.")
        return

    anomalies_detectees = 0

    for vm_name, infos in inventaire.items():
        etat_attendu = infos.get("expected_state", "running")
        etat_reel    = get_status_reel(vm_name)

        log(f"[CHECK] {vm_name} | attendu={etat_attendu} | réel={etat_reel}")

        # Correspondance attendu → réel
        correspondance = {
            "running": "PoweredOn",
            "stopped": "PoweredOff",
        }

        etat_reel_attendu = correspondance.get(etat_attendu)

        if etat_reel == etat_reel_attendu:
            # Tout va bien
            continue

        # Anomalie détectée
        anomalies_detectees += 1
        diagnostic = analyser_anomalie(vm_name, etat_attendu, etat_reel)
        action     = proposer_action(vm_name, etat_attendu, etat_reel)

        log(f"[ANOMALIE] {diagnostic}")

        if action is None:
            log(f"[INFO] Aucune action automatique disponible pour {vm_name}.")
            continue

        # Demande validation humaine — jamais automatique
        valide = demander_validation(diagnostic, action, vm_name)

        if valide:
            executer_correction(action, vm_name)
        else:
            log(f"[INFO] Action '{action}' sur '{vm_name}' ignorée par l'opérateur.")

    if anomalies_detectees == 0:
        log("[OK] Infrastructure conforme — aucune anomalie détectée.")


def main():
    print("=" * 60)
    print("  ai-infra-agent — Monitoring")
    print(f"  Intervalle : toutes les {POLL_INTERVAL} secondes")
    print("  Arrêt : Ctrl+C")
    print("=" * 60)
    print()

    log("[START] Démarrage du monitoring.")

    try:
        while True:
            verifier_infrastructure()
            print(f"\n[INFO] Prochaine vérification dans {POLL_INTERVAL}s...\n")
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log("[STOP] Monitoring arrêté par l'opérateur.")
        print("\n[INFO] Monitoring arrêté.")


if __name__ == "__main__":
    main()
