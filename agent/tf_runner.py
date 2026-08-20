"""
tf_runner.py — Orchestrateur principal du projet ai-infra-agent.

Flux complet :
    1. Lit input/servers.yaml
    2. Valide chaque serveur (gouvernance + champ action)
    3. Appelle llm_agent.py pour générer terraform/main.tf
    4. Execute terraform apply ou terraform destroy selon l'action YAML
    5. Affiche le résultat final

Usage :
    python agent/tf_runner.py
"""

import os
import sys
import subprocess
import yaml
from dotenv import load_dotenv

load_dotenv()

# --- Chemins ---
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH   = os.path.join(BASE_DIR, "input", "servers.yaml")
TF_DIR      = os.path.join(BASE_DIR, "terraform")
AGENT_DIR   = os.path.join(BASE_DIR, "agent")

# --- Règles de gouvernance ---
MAX_VCPU   = 8
MAX_RAM_GB = 16
ACTIONS_VALIDES = {"create", "destroy"}

import re
NAMING_PATTERN = re.compile(r"^srv-(dev|staging|prod)-[a-z0-9]+-\d{2}$")


# ---------------------------------------------------------------------
# Étape 1 — Lecture et validation du YAML
# ---------------------------------------------------------------------

def lire_et_valider_yaml(yaml_path: str) -> list[dict]:
    """
    Lit le fichier YAML et valide chaque serveur.
    Lève une exception claire si une règle de gouvernance est violée.
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "servers" not in data:
        raise ValueError("Le fichier YAML doit contenir une clé 'servers'.")

    servers = data["servers"]
    if not isinstance(servers, list) or len(servers) == 0:
        raise ValueError("La liste 'servers' est vide ou invalide.")

    erreurs = []

    for i, srv in enumerate(servers):
        numero = i + 1

        # Champs obligatoires
        for champ in ["name", "action", "template", "cpu", "ram_gb"]:
            if champ not in srv:
                erreurs.append(f"Serveur #{numero} : champ obligatoire '{champ}' manquant.")

        if erreurs:
            continue

        nom    = srv["name"]
        action = srv["action"]
        cpu    = srv["cpu"]
        ram_gb = srv["ram_gb"]

        # Validation du nom
        if not NAMING_PATTERN.match(nom):
            erreurs.append(
                f"Serveur #{numero} : nom '{nom}' invalide. "
                f"Format attendu : srv-{{dev|staging|prod}}-{{role}}-{{index}} "
                f"(ex: srv-dev-web-01)."
            )

        # Validation de l'action
        if action not in ACTIONS_VALIDES:
            erreurs.append(
                f"Serveur #{numero} '{nom}' : action '{action}' invalide. "
                f"Valeurs acceptées : {ACTIONS_VALIDES}."
            )

        # Validation des ressources (gouvernance)
        if not isinstance(cpu, int) or cpu < 1 or cpu > MAX_VCPU:
            erreurs.append(
                f"Serveur #{numero} '{nom}' : cpu={cpu} invalide. "
                f"Doit être entre 1 et {MAX_VCPU}."
            )

        if not isinstance(ram_gb, (int, float)) or ram_gb < 1 or ram_gb > MAX_RAM_GB:
            erreurs.append(
                f"Serveur #{numero} '{nom}' : ram_gb={ram_gb} invalide. "
                f"Doit être entre 1 et {MAX_RAM_GB} Go."
            )

    if erreurs:
        print("\n[ERREUR] Validation YAML echouee :\n")
        for e in erreurs:
            print(f"  - {e}")
        print()
        raise ValueError("Demande rejetee : règles de gouvernance non respectees.")

    return servers


# ---------------------------------------------------------------------
# Étape 2 — Génération du Terraform via le LLM
# ---------------------------------------------------------------------

def generer_terraform(yaml_path: str) -> None:
    """
    Appelle llm_agent.py pour générer terraform/main.tf.
    """
    print("[INFO] Generation du fichier Terraform via l'IA...")

    llm_script = os.path.join(AGENT_DIR, "llm_agent.py")
    result = subprocess.run(
        [sys.executable, llm_script],
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("Echec de la generation Terraform par le LLM.")

    print("[OK] main.tf genere avec succes.")


# ---------------------------------------------------------------------
# Étape 3 — Exécution Terraform
# ---------------------------------------------------------------------

def _run_terraform(args: list[str]) -> int:
    """
    Execute une commande terraform dans le dossier terraform/.
    Affiche la sortie en temps réel.
    Retourne le code de retour.
    """
    cmd = ["terraform"] + args
    print(f"\n[INFO] Execution : {' '.join(cmd)}\n")

    process = subprocess.Popen(
        cmd,
        cwd=TF_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # Affichage en temps réel ligne par ligne
    for line in process.stdout:
        print(line, end="")

    process.wait()
    return process.returncode


def executer_terraform(servers: list[dict]) -> None:
    """
    Détermine l'action à exécuter selon le champ 'action' du YAML.
    Si plusieurs serveurs ont des actions différentes, on fait
    d'abord les destroy puis les create.
    """

    actions = {srv["action"] for srv in servers}

    # Terraform init (toujours, au cas où)
    code = _run_terraform(["init", "-input=false"])
    if code != 0:
        raise RuntimeError("terraform init a echoue.")

    # Si tous les serveurs sont à destroy
    if actions == {"destroy"}:
        print("\n[INFO] Action : DESTROY de toute l'infrastructure\n")
        _confirmer_destroy()
        code = _run_terraform(["destroy", "-auto-approve"])
        if code != 0:
            raise RuntimeError("terraform destroy a echoue.")
        print("\n[OK] Infrastructure detruite avec succes.")

    # Si tous les serveurs sont à create (ou mixte)
    else:
        print("\n[INFO] Action : APPLY de l'infrastructure\n")
        code = _run_terraform(["plan"])
        if code != 0:
            raise RuntimeError("terraform plan a echoue.")

        print("\n" + "=" * 60)
        print("  Plan affiche ci-dessus.")
        print("  Voulez-vous appliquer ces changements ?")
        print("  Tapez yes pour confirmer, autre chose pour annuler.")
        print("=" * 60)

        try:
            reponse = input("  Votre decision : ").strip().lower()
        except:
            print("\n[INFO] Apply annule.")
            return

        if reponse != "yes":
            print("\n[INFO] Apply annule par operateur.")
            return

        code = _run_terraform(["apply", "-auto-approve"])
        if code != 0:
            raise RuntimeError("terraform apply a echoue.")
        print("\n[OK] Infrastructure deployee avec succes.")


def _confirmer_destroy() -> None:
    """
    Demande une confirmation explicite avant un destroy.
    Terraform destroy est irréversible — on ne l'automatise jamais
    sans validation humaine.
    """
    print("=" * 60)
    print("  ATTENTION : Cette action va SUPPRIMER des VMs.")
    print("  Tapez 'yes' pour confirmer, autre chose pour annuler.")
    print("=" * 60)
    reponse = input("  Confirmer la destruction ? : ").strip().lower()
    if reponse != "yes":
        print("\n[INFO] Destruction annulee par l'operateur.")
        sys.exit(0)


# ---------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  ai-infra-agent — Orchestrateur")
    print("=" * 60)

    # Étape 1 — Lecture et validation
    print(f"\n[INFO] Lecture de {YAML_PATH}...")
    try:
        servers = lire_et_valider_yaml(YAML_PATH)
    except ValueError as e:
        print(f"\n[ERREUR] {e}")
        sys.exit(1)

    print(f"[OK] {len(servers)} serveur(s) valide(s) :")
    for srv in servers:
        print(f"     - {srv['name']} | action={srv['action']} | "
              f"{srv['cpu']} vCPU | {srv['ram_gb']} Go RAM | "
              f"template={srv['template']}")

    # Étape 2 — Génération Terraform
    try:
        generer_terraform(YAML_PATH)
    except RuntimeError as e:
        print(f"\n[ERREUR] {e}")
        sys.exit(1)

    # Étape 3 — Exécution Terraform
    try:
        executer_terraform(servers)
    except RuntimeError as e:
        print(f"\n[ERREUR] {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Mission accomplie.")
    print("=" * 60)


if __name__ == "__main__":
    main()

