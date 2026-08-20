"""
function_agent.py — Agent IA autonome avec function calling.

Un seul point d'entrée pour toutes les opérations :
- Gérer des VMs (create, delete, start, stop, status, list)
- Snapshots (create, list, revert)
- Importer un PDF et déployer l'infrastructure
- Voir l'historique des actions

Usage :
    python agent/function_agent.py

Exemples :
    "Create VM srv-dev-web-01 from ubuntu-22.04"
    "Import PDF input/demande_infrastructure.pdf and deploy"
    "Create 3 web servers in dev from ubuntu-22.04"
    "Delete srv-dev-web-01"
    "history"
    "exit"
"""

import os
import sys
import json
import subprocess
import yaml as yaml_module
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

try:
    import pdfplumber
except ImportError:
    print("[ERREUR] pdfplumber non installe. Lance : pip install pdfplumber")
    sys.exit(1)

load_dotenv()

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE_PATH   = os.path.join(BASE_DIR, "agent", "tools", "vmware_bridge.py")
TFRUNNER_PATH = os.path.join(BASE_DIR, "agent", "tf_runner.py")
YAML_PATH     = os.path.join(BASE_DIR, "input", "servers.yaml")
MODEL         = "openai/gpt-oss-120b"

# Memoire persistante SQLite
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))
from memory import AgentMemory
memory = AgentMemory()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------------------------------------------------------
# Prompt système
# ---------------------------------------------------------------------

SYSTEM_PROMPT = """You are InfraAgent, an AI DevOps agent specialized in
VMware Workstation Pro infrastructure automation.

You have tools to manage virtual machines and analyze infrastructure documents.
Use them autonomously to accomplish tasks requested by the operator.

LANGUAGE RULES:
- Always respond in English
- Be tolerant of typos (e.g. 'cms' = 'vms', 'lsie' = 'list')
- When in doubt about a typo, execute the most logical interpretation directly

GOVERNANCE RULES:
- Mandatory naming : srv-{dev|staging|prod}-{role}-{index}
  Examples : srv-dev-web-01, srv-prod-db-02, srv-staging-api-01
- Maximum CPU : 8 vCPU (if document requests more, flag it and ask operator)
- Maximum RAM : 16 GB (same rule)
- Valid actions : create, destroy
- Index always 2 digits : 01, 02, 03...

MULTI-VM RULES:
- If operator asks for multiple VMs (e.g. '3 web servers'),
  generate sequential names : srv-dev-web-01, srv-dev-web-02, srv-dev-web-03
- Call create_vm once per VM, in sequence

SNAPSHOT RULES:
- ALWAYS take an automatic snapshot before any delete operation
- Call snapshot_vm BEFORE delete_vm, every time, no exception
- Snapshot name format : before-delete-YYYYMMDD-HHMMSS

PDF WORKFLOW:
When the operator provides a PDF or asks to import/analyze a document :
  Step 1 : Call read_pdf to extract text
  Step 2 : Call analyze_and_extract with the extracted text
  Step 3 : Show the operator what was found (servers + violations)
  Step 4 : Ask operator to confirm corrections if any governance violations
  Step 5 : Call save_yaml with the validated servers JSON
  Step 6 : Ask operator if they want to deploy now
  Step 7 : If yes, call deploy_infrastructure

EXPECTED BEHAVIOR:
- Use tools in the correct logical order
- Never skip the governance validation step for PDFs
- Ask for confirmation before destructive actions (delete/destroy)
- After PDF analysis, always show a summary before deploying
- Be concise and professional
"""

# ---------------------------------------------------------------------
# Définition des tools pour le LLM
# ---------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_vm",
            "description": "Creates a new VMware VM by cloning an existing template and starts it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "VM name (convention srv-env-role-index, e.g. srv-dev-web-01)"
                    },
                    "template_id": {
                        "type": "string",
                        "description": "Template name to clone (e.g. ubuntu-22.04)"
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
            "description": "Shuts down and permanently deletes a VMware VM. Always snapshot first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {
                        "type": "string",
                        "description": "Name of the VM to delete"
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
            "description": "Starts an existing VMware VM that is powered off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {"type": "string", "description": "VM name to start"}
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_vm",
            "description": "Gracefully shuts down a running VMware VM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {"type": "string", "description": "VM name to stop"}
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_vm_status",
            "description": "Returns the real state of a VM: PoweredOn, PoweredOff, or NotFound.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {"type": "string", "description": "VM name to check"}
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_vms",
            "description": "Lists all VMs in the local inventory with their current state.",
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
            "name": "snapshot_vm",
            "description": "Creates a snapshot (restore point) of an existing VM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {"type": "string", "description": "VM name"},
                    "snapshot_name": {
                        "type": "string",
                        "description": "Snapshot name (optional, auto-generated if empty)"
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
            "description": "Lists all available snapshots for a VM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {"type": "string", "description": "VM name"}
                },
                "required": ["vm_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "revert_snapshot",
            "description": "Reverts a VM to a previous snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vm_name": {"type": "string", "description": "VM name"},
                    "snapshot_name": {"type": "string", "description": "Snapshot name to revert to"}
                },
                "required": ["vm_name", "snapshot_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_templates",
            "description": "Lists all available VM templates in the Templates directory.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "Extracts raw text from a PDF file. Returns the document content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Path to the PDF file (e.g. input/demande_infrastructure.pdf)"
                    }
                },
                "required": ["pdf_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_extract",
            "description": (
                "Analyzes raw PDF text to extract server requirements, "
                "validates governance rules (naming, CPU/RAM limits), "
                "flags violations and returns a structured summary with server data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_text": {
                        "type": "string",
                        "description": "Raw text extracted from the PDF document"
                    }
                },
                "required": ["pdf_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_yaml",
            "description": (
                "Saves the validated server list as input/servers.yaml. "
                "servers_json must be a JSON array string of server objects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "servers_json": {
                        "type": "string",
                        "description": "JSON array string of server objects to save"
                    }
                },
                "required": ["servers_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_monitoring",
            "description": "Starts the infrastructure monitoring in the background. Checks VM states every 60 seconds and alerts on anomalies.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_monitoring",
            "description": "Stops the infrastructure monitoring.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "monitoring_status",
            "description": "Returns whether the monitoring is currently running or stopped.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_infrastructure",
            "description": "Generates Terraform from servers.yaml via LLM and runs terraform apply.",
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
            "description": "Asks the human operator for explicit confirmation before a destructive action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_description": {
                        "type": "string",
                        "description": "Clear description of the action that needs confirmation"
                    }
                },
                "required": ["action_description"]
            }
        }
    }
]

# ---------------------------------------------------------------------
# Implémentation des tools
# ---------------------------------------------------------------------

def _appeler_bridge(args: list) -> str:
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


def tool_delete_vm(vm_name: str) -> str:
    print(f"\n  [TOOL] delete_vm({vm_name})")
    snapshot_name = "before-delete-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"  [SAFETY] Auto-snapshot before delete : {snapshot_name}")
    snap = _appeler_bridge(["snapshot", vm_name, snapshot_name])
    print(f"  [SAFETY] {snap[:100]}")
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


def tool_snapshot_vm(vm_name: str, snapshot_name: str = "") -> str:
    print(f"\n  [TOOL] snapshot_vm({vm_name}, {snapshot_name})")
    if not snapshot_name:
        snapshot_name = "auto-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    return _appeler_bridge(["snapshot", vm_name, snapshot_name])


def tool_list_snapshots(vm_name: str) -> str:
    print(f"\n  [TOOL] list_snapshots({vm_name})")
    return _appeler_bridge(["list_snapshots", vm_name])


def tool_revert_snapshot(vm_name: str, snapshot_name: str) -> str:
    print(f"\n  [TOOL] revert_snapshot({vm_name}, {snapshot_name})")
    return _appeler_bridge(["revert_snapshot", vm_name, snapshot_name])


def tool_list_templates() -> str:
    print(f"\n  [TOOL] list_templates()")
    templates_dir = os.path.join("C:\\\\InfraAgent", "Templates")
    if not os.path.exists(templates_dir):
        return "[ERREUR] Templates directory not found : " + templates_dir
    templates = []
    for item in os.listdir(templates_dir):
        vmx = os.path.join(templates_dir, item, item + ".vmx")
        if os.path.exists(vmx):
            templates.append(item)
    if not templates:
        return "No templates found in " + templates_dir
    return "Available templates :\n" + "\n".join(f"  - {t}" for t in templates)


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


def tool_analyze_and_extract(pdf_text: str) -> str:
    print(f"\n  [TOOL] analyze_and_extract({len(pdf_text)} chars)")

    prompt = """You are an infrastructure analyst.
Analyze this document and extract all server requirements.

GOVERNANCE RULES to enforce:
- Name format: srv-{dev|staging|prod}-{role}-{index} (e.g. srv-dev-web-01)
- Max CPU: 8 vCPU
- Max RAM: 16 GB
- Valid actions: create or destroy
- Index always 2 digits

Return ONLY a JSON object with this exact structure, no explanation, no markdown:
{
  "servers": [
    {
      "name": "srv-dev-web-01",
      "action": "create",
      "cpu": 2,
      "ram_gb": 4,
      "disk_gb": 40,
      "template": "ubuntu-22.04",
      "network": "NAT",
      "datastore": "local-ssd"
    }
  ],
  "violations": ["list of governance violations found"],
  "corrections": ["list of corrections applied"]
}"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user",   "content": "Document text:\n\n" + pdf_text[:8000]},
        ],
        temperature=0,
    )

    result = response.choices[0].message.content.strip()
    result = result.replace("```json", "").replace("```", "").strip()

    try:
        data       = json.loads(result)
        servers    = data.get("servers", [])
        violations = data.get("violations", [])
        corrections = data.get("corrections", [])

        summary = f"Found {len(servers)} server(s).\n"
        if violations:
            summary += "Violations: " + "; ".join(violations) + "\n"
        if corrections:
            summary += "Corrections: " + "; ".join(corrections) + "\n"
        summary += "\nExtracted servers:\n"
        for s in servers:
            summary += (
                f"  - {s.get('name','?')} | {s.get('cpu','?')} vCPU | "
                f"{s.get('ram_gb','?')} GB | template: {s.get('template','?')}\n"
            )
        summary += "\nRAW_JSON:" + json.dumps(servers)
        return summary
    except Exception as e:
        return f"[ERREUR] Could not parse analysis: {e}\nRaw: {result[:300]}"


def tool_save_yaml(servers_json: str) -> str:
    print(f"\n  [TOOL] save_yaml()")
    try:
        # Extraire le JSON brut si l'agent passe le résumé complet
        if "RAW_JSON:" in servers_json:
            servers_json = servers_json.split("RAW_JSON:")[-1].strip()

        servers = json.loads(servers_json)

        for srv in servers:
            srv.setdefault("action",    "create")
            srv.setdefault("network",   "NAT")
            srv.setdefault("datastore", "local-ssd")
            srv.setdefault("disk_gb",   40)

        data = {"servers": servers}
        yaml_content = yaml_module.dump(data, default_flow_style=False, allow_unicode=True)

        os.makedirs(os.path.dirname(YAML_PATH), exist_ok=True)
        with open(YAML_PATH, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        return f"[OK] servers.yaml saved with {len(servers)} server(s)."
    except Exception as e:
        return f"[ERREUR] Could not save YAML: {e}"


# Variable globale pour le process de monitoring
_monitoring_process = None


def tool_start_monitoring() -> str:
    print(f"\n  [TOOL] start_monitoring()")
    global _monitoring_process
    if _monitoring_process and _monitoring_process.poll() is None:
        return "Monitoring is already running."
    monitor_path = os.path.join(BASE_DIR, "agent", "monitor.py")
    if not os.path.exists(monitor_path):
        return "[ERREUR] monitor.py not found."
    _monitoring_process = subprocess.Popen(
        [sys.executable, monitor_path],
        cwd=BASE_DIR,
        encoding="utf-8",
    )
    return f"[OK] Monitoring started (PID {_monitoring_process.pid}). Checking every 60 seconds."


def tool_stop_monitoring() -> str:
    print(f"\n  [TOOL] stop_monitoring()")
    global _monitoring_process
    if not _monitoring_process or _monitoring_process.poll() is not None:
        return "Monitoring is not running."
    _monitoring_process.terminate()
    _monitoring_process = None
    return "[OK] Monitoring stopped."


def tool_monitoring_status() -> str:
    print(f"\n  [TOOL] monitoring_status()")
    global _monitoring_process
    if _monitoring_process and _monitoring_process.poll() is None:
        return f"Monitoring is RUNNING (PID {_monitoring_process.pid})."
    return "Monitoring is STOPPED."


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
    print("  [CONFIRMATION REQUIRED]")
    print(f"  {action_description}")
    print("  Type 'yes' to confirm, anything else to cancel.")
    print("=" * 60)
    try:
        reponse = input("  Your decision : ").strip().lower()
        return "confirmed" if reponse == "yes" else "cancelled"
    except (EOFError, KeyboardInterrupt):
        return "cancelled"


# Dispatch table
TOOL_DISPATCH = {
    "create_vm":            lambda args: tool_create_vm(**args),
    "delete_vm":            lambda args: tool_delete_vm(**args),
    "start_vm":             lambda args: tool_start_vm(**args),
    "stop_vm":              lambda args: tool_stop_vm(**args),
    "get_vm_status":        lambda args: tool_get_vm_status(**args),
    "list_vms":             lambda args: tool_list_vms(),
    "snapshot_vm":          lambda args: tool_snapshot_vm(**args),
    "list_snapshots":       lambda args: tool_list_snapshots(**args),
    "revert_snapshot":      lambda args: tool_revert_snapshot(**args),
    "list_templates":       lambda args: tool_list_templates(),
    "read_pdf":             lambda args: tool_read_pdf(**args),
    "analyze_and_extract":  lambda args: tool_analyze_and_extract(**args),
    "save_yaml":            lambda args: tool_save_yaml(**args),
    "start_monitoring":      lambda args: tool_start_monitoring(),
    "stop_monitoring":       lambda args: tool_stop_monitoring(),
    "monitoring_status":     lambda args: tool_monitoring_status(),
    "deploy_infrastructure": lambda args: tool_deploy_infrastructure(),
    "confirm_action":       lambda args: tool_confirm_action(**args),
}

# ---------------------------------------------------------------------
# Boucle agentique
# ---------------------------------------------------------------------

def executer_agent(instruction: str) -> None:
    contexte = memory.get_contexte_prompt()
    prompt_enrichi = SYSTEM_PROMPT + "\n\n" + contexte

    messages = [
        {"role": "system", "content": prompt_enrichi},
        {"role": "user",   "content": instruction},
    ]

    print(f"\n[AGENT] Processing : {instruction}\n")

    max_iterations = 15
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        message      = response.choices[0].message
        raison_arret = response.choices[0].finish_reason

        tool_calls_data = None
        if message.tool_calls:
            tool_calls_data = [
                {
                    "id":   tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in message.tool_calls
            ]

        messages.append({
            "role":       "assistant",
            "content":    message.content or "",
            "tool_calls": tool_calls_data,
        })

        # Réponse finale — pas de tool call
        if raison_arret == "stop" or not message.tool_calls:
            if message.content:
                print("\n" + "=" * 60)
                print("  [AGENT] Final response :")
                print("=" * 60)
                print(f"\n{message.content}\n")
                memory.sauvegarder_conversation(instruction, message.content)
            break

        # Exécution des tool calls
        for tool_call in message.tool_calls:
            nom_tool  = tool_call.function.name
            args_json = tool_call.function.arguments

            try:
                args = json.loads(args_json)
            except json.JSONDecodeError:
                args = {}

            print(f"  -> LLM calls : {nom_tool}({args})")

            if nom_tool in TOOL_DISPATCH:
                resultat = TOOL_DISPATCH[nom_tool](args)
                succes   = not resultat.startswith("[ERREUR]")
                memory.sauvegarder_action(nom_tool, args, resultat[:500], succes)
            else:
                resultat = f"[ERREUR] Unknown tool : {nom_tool}"

            affichage = resultat[:200] + "..." if len(resultat) > 200 else resultat
            print(f"  <- Result : {affichage}")

            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      resultat,
            })

    if iteration >= max_iterations:
        print("\n[WARN] Max iterations reached.")


# ---------------------------------------------------------------------
# Interface conversationnelle
# ---------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  InfraAgent — Autonomous Agent with Function Calling")
    print(f"  Model : {MODEL}")
    print("  Type 'exit' to quit, 'history' to see past actions")
    print("=" * 60)
    print()
    print("Example commands :")
    print("  - Create VM srv-dev-web-01 from ubuntu-22.04")
    print("  - Create 3 web servers in dev from ubuntu-22.04")
    print("  - What is the status of srv-dev-web-01 ?")
    print("  - List all VMs")
    print("  - Take a snapshot of srv-dev-web-01")
    print("  - Delete srv-dev-web-01")
    print("  - Import PDF input/demande_infrastructure.pdf and deploy")
    print("  - history")
    print()

    while True:
        try:
            instruction = input("You : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Goodbye.")
            break

        if not instruction:
            continue

        if instruction.lower() in ("exit", "quit", "q"):
            print("[INFO] Goodbye.")
            break

        if instruction.lower() in ("history", "historique"):
            memory.afficher_historique()
            continue

        executer_agent(instruction)


if __name__ == "__main__":
    main()






