"""
function_agent.py — Agent IA autonome avec function calling.

L'agent reçoit une instruction en langage naturel et décide
lui-même quels outils appeler, dans quel ordre, pour accomplir
la tâche.

Usage :
    python agent/function_agent.py

Exemple d'instructions :
    "Crée une VM srv-dev-web-01 depuis le template ubuntu-22.04"
    "Quel est le statut de srv-dev-web-01 ?"
    "Liste toutes les VMs"
    "Supprime srv-dev-web-01"
    "Analyse le PDF input/demande_infrastructure.pdf et déploie"
"""

import os
import sys
import json
import subprocess
from dotenv import load_dotenv
from groq import Groq

try:
    import pdfplumber
except ImportError:
    print("[ERREUR] pdfplumber non installé. Lance : pip install pdfplumber")
    sys.exit(1)

load_dotenv()

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Memoire persistante SQLite
sys.path.insert(0, os.path.join(BASE_DIR, 'agent'))
from memory import AgentMemory
memory = AgentMemory()
BRIDGE_PATH   = os.path.join(BASE_DIR, "agent", "tools", "vmware_bridge.py")
TFRUNNER_PATH = os.path.join(BASE_DIR, "agent", "tf_runner.py")
YAML_PATH     = os.path.join(BASE_DIR, "input", "servers.yaml")
MODEL         = "openai/gpt-oss-120b"

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------------------------------------------------------
# Prompt système de l'agent
# ---------------------------------------------------------------------

SYSTEM_PROMPT = """You are InfraAgent, an AI DevOps agent specialized in
VMware Workstation Pro infrastructure automation.

You have tools to manage virtual machines. Use them autonomously
to accomplish tasks requested by the operator.

IMPORTANT LANGUAGE RULES:
- Always respond in English
- Be tolerant of typos and abbreviations from the operator
- When in doubt about a typo, pick the most logical interpretation
  and execute it directly without asking

GOVERNANCE RULES:
- Mandatory naming : srv-{dev|staging|prod}-{role}-{index}
  Examples : srv-dev-web-01, srv-prod-db-02
- Maximum CPU : 8 vCPU
- Maximum RAM : 16 GB
- Valid actions : create, destroy

SNAPSHOT RULES:
- ALWAYS take an automatic snapshot before any delete operation
- Use snapshot_vm tool before delete_vm
- Name the snapshot with format: before-delete-YYYYMMDD-HHMMSS

EXPECTED BEHAVIOR:
- Use tools in the correct logical order
- If a step fails, explain why and suggest a fix
- Ask for confirmation ONLY before destructive actions (delete/destroy)
- Be concise and professional
- If a governance rule is violated, refuse and explain why
"""

# ---------------------------------------------------------------------
# Définition des outils (tools) pour le function calling
# ---------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_vm",
            "description": (
                "Crée une nouvelle VM VMware en clonant un template existant "
                "et la démarre automatiquement."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM (convention srv-env-role-index, ex: srv-dev-web-01)"
                    },
                    "template_id": {
                        "type": "string",
                        "description": "Nom du template à cloner (ex: ubuntu-22.04)"
                    }
                },
                "required": ["vm_name", "template_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_vm",
            "description": "Éteint et supprime définitivement une VM VMware.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM à supprimer"
                    }
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_vm",
            "description": "Démarre une VM VMware existante qui est éteinte.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM à démarrer"
                    }
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_vm",
            "description": "Éteint proprement une VM VMware en cours d'exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM à éteindre"
                    }
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_vm_status",
            "description": "Retourne l'état réel d'une VM (PoweredOn, PoweredOff, NotFound).",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM dont on veut connaître le statut"
                    }
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "snapshot_vm",
            "description": "Crée un snapshot (point de restauration) d'une VM existante.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM"
                    },
                    "snapshot_name": {
                        "type": "string",
                        "description": "Nom du snapshot (optionnel, généré automatiquement si vide)"
                    }
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_snapshots",
            "description": "Liste tous les snapshots disponibles pour une VM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM"
                    }
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "revert_snapshot",
            "description": "Restaure une VM à un snapshot précédent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Nom de la VM"
                    },
                    "snapshot_name": {
                        "type": "string",
                        "description": "Nom du snapshot à restaurer"
                    }
                },
                "required": ["vm_name", "snapshot_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_vms",
            "description": "Liste toutes les VMs connues dans l'inventaire local avec leur état.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": (
                "Extrait le texte brut d'un fichier PDF de demande de serveurs. "
                "Retourne le contenu textuel du document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Chemin vers le fichier PDF à lire"
                    }
                },
                "required": ["pdf_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_infrastructure",
            "description": (
                "Génère le code Terraform depuis servers.yaml via le LLM "
                "et exécute terraform apply pour créer les VMs."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_action",
            "description": (
                "Demande une confirmation explicite à l'opérateur humain "
                "avant d'exécuter une action destructive ou irréversible."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_description": {
                        "type": "string",
                        "description": "Description claire de l'action qui nécessite confirmation"
                    }
                },
                "required": ["action_description"]
            }
        }
    }
]

# ---------------------------------------------------------------------
# Implémentation des outils (ce qui s'exécute vraiment)
# ---------------------------------------------------------------------

def _appeler_bridge(args: list[str]) -> str:
    """Appelle vmware_bridge.py et retourne la sortie."""
    result = subprocess.run(
        [sys.executable, BRIDGE_PATH] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=BASE_DIR,
    )
    return (result.stdout + result.stderr).strip()


def tool_create_vm(vm_name: str, template_id: str) -> str:
    print(f"\n  [TOOL] create_vm({vm_name}, {template_id})")
    return _appeler_bridge(["create", template_id, vm_name])

def tool_snapshot_vm(vm_name: str, snapshot_name: str = "") -> str:
    print(f"\n  [TOOL] snapshot_vm({vm_name}, {snapshot_name})")
    if not snapshot_name:
        from datetime import datetime
        snapshot_name = "auto-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    return _appeler_bridge(["snapshot", vm_name, snapshot_name])


def tool_list_snapshots(vm_name: str) -> str:
    print(f"\n  [TOOL] list_snapshots({vm_name})")
    return _appeler_bridge(["list_snapshots", vm_name])


def tool_revert_snapshot(vm_name: str, snapshot_name: str) -> str:
    print(f"\n  [TOOL] revert_snapshot({vm_name}, {snapshot_name})")
    return _appeler_bridge(["revert_snapshot", vm_name, snapshot_name])

def tool_delete_vm(vm_name: str) -> str:
    print(f"\n  [TOOL] delete_vm({vm_name})")
    return _appeler_bridge(["delete", vm_name])


def tool_start_vm(vm_name: str) -> str:
    print(f"\n  [TOOL] start_vm({vm_name})")
    return _appeler_bridge(["start", vm_name])


def tool_stop_vm(vm_name: str) -> str:
    print(f"\n  [TOOL] stop_vm({vm_name})")
    return _appeler_bridge(["stop", vm_name])


def tool_get_vm_status(vm_name: str) -> str:
    print(f"\n  [TOOL] get_vm_status({vm_name})")
    return _appeler_bridge(["status", vm_name])


def tool_list_vms() -> str:
    print(f"\n  [TOOL] list_vms()")
    return _appeler_bridge(["list"])


def tool_read_pdf(pdf_path: str) -> str:
    print(f"\n  [TOOL] read_pdf({pdf_path})")
    chemin = os.path.join(BASE_DIR, pdf_path) if not os.path.isabs(pdf_path) else pdf_path
    if not os.path.exists(chemin):
        return f"[ERREUR] PDF introuvable : {chemin}"
    try:
        texte = []
        with pdfplumber.open(chemin) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text()
                if t:
                    texte.append(f"--- Page {i} ---\n{t}")
        return "\n\n".join(texte) if texte else "[ERREUR] Aucun texte extractible."
    except Exception as e:
        return f"[ERREUR] Lecture PDF : {e}"


def tool_deploy_infrastructure() -> str:
    print(f"\n  [TOOL] deploy_infrastructure()")
    result = subprocess.run(
        [sys.executable, TFRUNNER_PATH],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=BASE_DIR,
    )
    return (result.stdout + result.stderr).strip()


def tool_confirm_action(action_description: str) -> str:
    print(f"\n  [TOOL] confirm_action()")
    print("\n" + "=" * 60)
    print(f"  [CONFIRMATION REQUISE]")
    print(f"  {action_description}")
    print("  Tapez 'yes' pour confirmer, autre chose pour annuler.")
    print("=" * 60)
    try:
        reponse = input("  Votre décision : ").strip().lower()
        if reponse == "yes":
            return "confirmed"
        return "cancelled"
    except (EOFError, KeyboardInterrupt):
        return "cancelled"


# Dispatch table — associe le nom du tool à sa fonction Python
TOOL_DISPATCH = {
    "create_vm":            lambda args: tool_create_vm(**args),
    "snapshot_vm":          lambda args: tool_snapshot_vm(**args),
    "list_snapshots":       lambda args: tool_list_snapshots(**args),
    "revert_snapshot":      lambda args: tool_revert_snapshot(**args),
    "delete_vm":            lambda args: tool_delete_vm(**args),
    "start_vm":             lambda args: tool_start_vm(**args),
    "stop_vm":              lambda args: tool_stop_vm(**args),
    "get_vm_status":        lambda args: tool_get_vm_status(**args),
    "list_vms":             lambda args: tool_list_vms(),
    "read_pdf":             lambda args: tool_read_pdf(**args),
    "deploy_infrastructure": lambda args: tool_deploy_infrastructure(),
    "confirm_action":       lambda args: tool_confirm_action(**args),
}

# ---------------------------------------------------------------------
# Boucle agentique principale
# ---------------------------------------------------------------------

def executer_agent(instruction: str) -> None:
    """
    Boucle agentique : envoie l'instruction au LLM, exécute les tools
    qu'il demande, retourne les résultats, recommence jusqu'à la fin.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": instruction},
    ]

    print(f"\n[AGENT] Traitement : {instruction}\n")

    max_iterations = 10  # Sécurité : évite les boucles infinies
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Appel au LLM avec les tools disponibles
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",  # Le LLM décide lui-même
            temperature=0,
        )

        message = response.choices[0].message
        raison_arret = response.choices[0].finish_reason

        # Ajouter la réponse du LLM à l'historique
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in (message.tool_calls or [])
            ] or None
        })

        # Cas 1 : Le LLM a terminé, pas de tool call
        if raison_arret == "stop" or not message.tool_calls:
            if message.content:
                print("\n" + "=" * 60)
                print("  [AGENT] Réponse finale :")
                print("=" * 60)
                print(f"\n{message.content}\n")
            break

        # Cas 2 : Le LLM veut appeler un ou plusieurs tools
        for tool_call in message.tool_calls:
            nom_tool  = tool_call.function.name
            args_json = tool_call.function.arguments

            try:
                args = json.loads(args_json)
            except json.JSONDecodeError:
                args = {}

            print(f"  → LLM appelle : {nom_tool}({args})")

            # Exécuter le tool
            if nom_tool in TOOL_DISPATCH:
                resultat = TOOL_DISPATCH[nom_tool](args)
                succes = not resultat.startswith("[ERREUR]")
                memory.sauvegarder_action(nom_tool, args, resultat[:500], succes)
            else:
                resultat = f"[ERREUR] Tool inconnu : {nom_tool}"

            print(f"  ← Résultat : {resultat[:200]}{'...' if len(resultat) > 200 else ''}")

            # Retourner le résultat au LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": resultat,
            })

    if iteration >= max_iterations:
        print("\n[WARN] Limite d'itérations atteinte.")


# ---------------------------------------------------------------------
# Interface conversationnelle
# ---------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  InfraAgent — Agent autonome avec Function Calling")
    print("  Modèle : " + MODEL)
    print("  Tape 'exit' pour quitter")
    print("=" * 60)
    print()
    print("Exemples de commandes :")
    print("  - Crée une VM srv-dev-web-01 depuis ubuntu-22.04")
    print("  - Quel est le statut de srv-dev-web-01 ?")
    print("  - Liste toutes les VMs")
    print("  - Supprime srv-dev-web-01")
    print("  - Analyse le PDF input/demande_infrastructure.pdf")
    print()

    while True:
        try:
            instruction = input("Toi : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Au revoir.")
            break

        if not instruction:
            continue

        if instruction.lower() in ("exit", "quit", "q"):
            print("[INFO] Au revoir.")
            break

        if instruction.lower() in ("history", "historique"):
            memory.afficher_historique()
            continue

        executer_agent(instruction)


if __name__ == "__main__":
    main()
