"""
pdf_agent.py — Agent IA dédié à l'analyse de documents PDF
et à la génération de servers.yaml.

Contrairement à pdf_reader.py (simple extraction),
cet agent mène une vraie conversation en plusieurs étapes :

  Tour 1 : Analyse le document et extrait les serveurs
  Tour 2 : Vérifie la gouvernance et pose des questions si besoin
  Tour 3 : Génère le YAML final corrigé et validé

Usage :
    python agent/pdf_agent.py chemin/vers/document.pdf
"""

import os
import sys
import re
import json
import yaml
from dotenv import load_dotenv
from groq import Groq

try:
    import pdfplumber
except ImportError:
    print("[ERREUR] pdfplumber non installé. Lance : pip install pdfplumber")
    sys.exit(1)

load_dotenv()

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join(BASE_DIR, "input", "servers.yaml")
MODEL     = "openai/gpt-oss-120b"

MAX_VCPU   = 8
MAX_RAM_GB = 16
NAMING_RE  = re.compile(r"^srv-(dev|staging|prod)-[a-z0-9]+-\d{2}$")
ACTIONS_VALIDES = {"create", "destroy"}

# ---------------------------------------------------------------------
# Prompt système de l'agent PDF
# ---------------------------------------------------------------------

SYSTEM_PROMPT = """Tu es un agent IA spécialisé en analyse de documents
d'infrastructure. Ton rôle est d'analyser des documents (bons de commande,
cahiers des charges, demandes de provisioning) et d'en extraire des
spécifications de serveurs.

Tu travailles en collaboration avec un opérateur humain.
Tu peux et tu DOIS poser des questions si des informations sont manquantes
ou ambiguës. Ne devine pas — demande.

RÈGLES DE GOUVERNANCE STRICTES :
- Nom obligatoire : srv-{dev|staging|prod}-{role}-{index}
  Exemples : srv-dev-web-01, srv-prod-db-02, srv-staging-api-01
- CPU maximum : 8 vCPU
- RAM maximum : 16 Go
- Action : 'create' ou 'destroy' uniquement
- Index toujours sur 2 chiffres : 01, 02, 03...

Si une règle est violée dans le document :
- Signale-le clairement
- Propose une correction
- Demande validation à l'opérateur

Quand tu poses des questions, liste-les de façon numérotée et concise.
Quand tu génères le YAML final, réponds UNIQUEMENT avec le YAML brut,
sans explication, sans markdown, sans backticks.
"""

# ---------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------

def extraire_texte_pdf(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")
    if not pdf_path.lower().endswith(".pdf"):
        raise ValueError(f"'{pdf_path}' n'est pas un PDF.")

    texte_complet = []
    with pdfplumber.open(pdf_path) as pdf:
        nb_pages = len(pdf.pages)
        print(f"[INFO] PDF ouvert : {nb_pages} page(s).")
        for i, page in enumerate(pdf.pages, 1):
            texte = page.extract_text()
            if texte:
                texte_complet.append(f"--- Page {i} ---\n{texte}")

    if not texte_complet:
        raise ValueError("Aucun texte extractible dans ce PDF.")

    return "\n\n".join(texte_complet)


def appeler_llm(messages: list[dict]) -> str:
    """Appelle Groq avec l'historique complet de la conversation."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def nettoyer_yaml(texte: str) -> str:
    return (
        texte
        .replace("```yaml", "")
        .replace("```yml", "")
        .replace("```", "")
        .strip()
    )


def valider_yaml(yaml_brut: str) -> tuple[list[dict], list[str]]:
    """
    Parse et valide le YAML.
    Retourne (servers, erreurs).
    erreurs est vide si tout est correct.
    """
    try:
        data = yaml.safe_load(yaml_brut)
    except yaml.YAMLError as e:
        return [], [f"YAML invalide : {e}"]

    if not data or "servers" not in data:
        return [], ["Le YAML ne contient pas de clé 'servers'."]

    servers = data.get("servers", [])
    erreurs = []

    for i, srv in enumerate(servers):
        numero = i + 1
        nom    = srv.get("name", f"serveur#{numero}")

        if not NAMING_RE.match(str(nom)):
            erreurs.append(
                f"Serveur #{numero} '{nom}' : nom invalide "
                f"(format attendu : srv-{{dev|staging|prod}}-{{role}}-{{index}})."
            )

        cpu    = srv.get("cpu", 0)
        ram_gb = srv.get("ram_gb", 0)
        action = srv.get("action", "")

        if not isinstance(cpu, int) or cpu < 1 or cpu > MAX_VCPU:
            erreurs.append(f"Serveur '{nom}' : cpu={cpu} invalide (max {MAX_VCPU}).")

        if not isinstance(ram_gb, (int, float)) or ram_gb < 1 or ram_gb > MAX_RAM_GB:
            erreurs.append(f"Serveur '{nom}' : ram_gb={ram_gb} invalide (max {MAX_RAM_GB}).")

        if action not in ACTIONS_VALIDES:
            erreurs.append(f"Serveur '{nom}' : action='{action}' invalide.")

    return servers, erreurs


def afficher_resume(servers: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("  [RÉSULTAT] Serveurs extraits du document :")
    print("=" * 60)
    for srv in servers:
        print(
            f"\n  - {srv.get('name', '?')}"
            f"\n    action   : {srv.get('action', '?')}"
            f"\n    CPU      : {srv.get('cpu', '?')} vCPU"
            f"\n    RAM      : {srv.get('ram_gb', '?')} Go"
            f"\n    Disque   : {srv.get('disk_gb', '?')} Go"
            f"\n    Template : {srv.get('template', '?')}"
        )
    print()


# ---------------------------------------------------------------------
# Boucle conversationnelle principale
# ---------------------------------------------------------------------

def lancer_agent(texte_pdf: str) -> str | None:
    """
    Mène la conversation avec l'agent en plusieurs tours.
    Retourne le YAML final validé, ou None si annulé.
    """

    # Historique de la conversation — on l'enrichit à chaque tour
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # --- Tour 1 : Analyse initiale du document ---
    print("\n[AGENT] Analyse du document en cours...\n")

    messages.append({
        "role": "user",
        "content": (
            f"Voici le contenu du document à analyser :\n\n{texte_pdf}\n\n"
            f"Analyse ce document et dis-moi :\n"
            f"1. Quels serveurs tu identifies\n"
            f"2. Quelles informations sont claires\n"
            f"3. Quelles informations sont manquantes ou ambiguës\n"
            f"4. Tes questions à poser à l'opérateur si nécessaire\n\n"
            f"Ne génère pas encore le YAML — analyse d'abord."
        )
    })

    analyse = appeler_llm(messages)
    messages.append({"role": "assistant", "content": analyse})

    print("=" * 60)
    print("  [AGENT PDF] Analyse initiale :")
    print("=" * 60)
    print(f"\n{analyse}\n")

    # --- Boucle de questions/réponses ---
    # L'agent pose des questions, l'opérateur répond
    # On continue jusqu'à ce que l'agent soit prêt à générer le YAML

    tour = 0
    max_tours = 5  # Sécurité : pas plus de 5 échanges

    while tour < max_tours:
        tour += 1

        # Demander à l'opérateur s'il veut répondre ou passer
        print("=" * 60)
        print("  Répondez aux questions de l'agent (ou appuyez")
        print("  sur Entrée sans rien taper pour passer à la")
        print("  génération du YAML avec les infos disponibles).")
        print("=" * 60)

        try:
            reponse_operateur = input("  Votre réponse : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Opération annulée.")
            return None

        if not reponse_operateur:
            # L'opérateur n'a rien à ajouter — on génère le YAML
            messages.append({
                "role": "user",
                "content": (
                    "Je n'ai pas d'informations supplémentaires à fournir. "
                    "Utilise des valeurs par défaut raisonnables pour les "
                    "informations manquantes et génère maintenant le YAML final. "
                    "Réponds UNIQUEMENT avec le YAML brut."
                )
            })
            break

        # L'opérateur a répondu — on continue la conversation
        messages.append({
            "role": "user",
            "content": (
                f"{reponse_operateur}\n\n"
                f"As-tu encore des questions, ou es-tu prêt à générer "
                f"le YAML final ? Si tu es prêt, génère le YAML maintenant "
                f"(UNIQUEMENT le YAML brut, sans explication)."
            )
        })

        reponse_agent = appeler_llm(messages)
        messages.append({"role": "assistant", "content": reponse_agent})

        print("\n" + "=" * 60)
        print("  [AGENT PDF] :")
        print("=" * 60)
        print(f"\n{reponse_agent}\n")

        # Détecter si l'agent a généré le YAML (commence par "servers:")
        yaml_brut = nettoyer_yaml(reponse_agent)
        if yaml_brut.strip().startswith("servers:"):
            return yaml_brut

    # --- Tour final : génération du YAML ---
    print("\n[AGENT] Génération du YAML final...\n")

    reponse_finale = appeler_llm(messages)
    messages.append({"role": "assistant", "content": reponse_finale})

    return nettoyer_yaml(reponse_finale)


# ---------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------

def importer_pdf_agent(pdf_path: str) -> bool:
    """
    Flux complet avec l'agent conversationnel.
    Retourne True si servers.yaml a été sauvegardé.
    """
    print("\n" + "=" * 60)
    print("  ai-infra-agent — Agent PDF")
    print("=" * 60)

    # Extraction du texte
    try:
        texte = extraire_texte_pdf(pdf_path)
        print(f"[OK] Texte extrait ({len(texte)} caractères).")
    except (FileNotFoundError, ValueError) as e:
        print(f"\n[ERREUR] {e}")
        return False

    # Conversation avec l'agent
    yaml_brut = lancer_agent(texte)

    if not yaml_brut:
        return False

    # Validation de gouvernance
    servers, erreurs = valider_yaml(yaml_brut)

    if erreurs:
        print("\n[ERREUR] Le YAML généré viole des règles de gouvernance :")
        for e in erreurs:
            print(f"  - {e}")
        print("\n[INFO] Relance l'agent et fournis des corrections.")
        return False

    # Affichage et confirmation finale
    afficher_resume(servers)

    print("=" * 60)
    print(f"  {len(servers)} serveur(s) validé(s).")
    print("  Écrire dans input/servers.yaml et déployer ?")
    print("  Tapez 'yes' pour confirmer.")
    print("=" * 60)

    try:
        reponse = input("  Votre décision : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    if reponse != "yes":
        print("\n[INFO] Opération annulée.")
        return False

    # Sauvegarde
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        f.write(yaml_brut)

    print(f"\n[OK] servers.yaml mis à jour avec {len(servers)} serveur(s).")
    print("[INFO] Lance maintenant : python agent/tf_runner.py")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pdf_path = sys.argv[1]
    succes   = importer_pdf_agent(pdf_path)
    sys.exit(0 if succes else 1)


if __name__ == "__main__":
    main()
