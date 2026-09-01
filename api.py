"""
api.py — API REST FastAPI pour InfraAgent.

Expose toutes les fonctionnalités de l'agent via HTTP
pour être consommées par le frontend (Lovable/React).

Usage :
    uvicorn api:app --reload --port 8000

Endpoints :
    GET  /api/vms              — lister les VMs
    POST /api/vms              — créer une VM
    DELETE /api/vms/{name}     — supprimer une VM
    POST /api/vms/{name}/start — démarrer une VM
    POST /api/vms/{name}/stop  — arrêter une VM
    POST /api/vms/{name}/snapshot — prendre un snapshot
    GET  /api/templates        — lister les templates
    GET  /api/logs             — lire les logs SQLite
    GET  /api/history          — historique des actions
    GET  /api/stats            — statistiques globales
    POST /api/chat             — envoyer une instruction à l'agent
    GET  /api/monitoring       — statut du monitoring
    POST /api/monitoring/start — démarrer le monitoring
    POST /api/monitoring/stop  — arrêter le monitoring
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Chemins
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR     = os.path.join(BASE_DIR, "agent")
BRIDGE_PATH   = os.path.join(BASE_DIR, "agent", "tools", "vmware_bridge.py")
FUNCTION_AGENT_PATH = os.path.join(BASE_DIR, "agent", "function_agent.py")

sys.path.insert(0, AGENT_DIR)
from memory import AgentMemory

memory = AgentMemory()

# Process monitoring global
_monitoring_process = None

# ---------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------

app = FastAPI(
    title="InfraAgent API",
    description="API REST pour l'agent IA DevOps VMware",
    version="1.0.0",
)

# CORS — autoriser le frontend React (Lovable tourne sur un port différent)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod, restreindre au domaine du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Modèles Pydantic (schémas de requête/réponse)
# ---------------------------------------------------------------------

class CreateVMRequest(BaseModel):
    vm_name:     str
    template_id: str

class ChatRequest(BaseModel):
    message: str

class SnapshotRequest(BaseModel):
    snapshot_name: Optional[str] = ""

# ---------------------------------------------------------------------
# Utilitaire — appeler le bridge
# ---------------------------------------------------------------------

def appeler_bridge(args: list) -> dict:
    result = subprocess.run(
        [sys.executable, BRIDGE_PATH] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=BASE_DIR,
    )
    output = (result.stdout + result.stderr).strip()
    succes = result.returncode == 0 and not output.startswith("[ERREUR]")
    return {"success": succes, "output": output}

# ---------------------------------------------------------------------
# Endpoints VMs
# ---------------------------------------------------------------------

@app.get("/api/vms")
def list_vms():
    """Retourne toutes les VMs de l'inventaire avec leur état réel."""
    result = appeler_bridge(["list"])
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["output"])
    try:
        inventory = json.loads(result["output"])
    except json.JSONDecodeError:
        inventory = {}

    vms = []
    for name, info in inventory.items():
        # Récupérer l'état réel
        status_result = appeler_bridge(["status", name])
        real_status = status_result["output"].strip().splitlines()[-1] if status_result["success"] else "Unknown"

        vms.append({
            "name":           name,
            "status":         real_status,
            "template":       info.get("template", "?"),
            "created_at":     info.get("created_at", "?")[:19].replace("T", " "),
            "expected_state": info.get("expected_state", "running"),
            "last_snapshot":  info.get("last_snapshot", None),
        })

    return {"vms": vms, "total": len(vms)}


@app.post("/api/vms")
def create_vm(request: CreateVMRequest):
    """Crée une nouvelle VM depuis un template."""
    result = appeler_bridge(["create", request.template_id, request.vm_name])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    memory.sauvegarder_action(
        "create_vm",
        {"vm_name": request.vm_name, "template_id": request.template_id},
        result["output"],
        True,
    )
    return {"success": True, "message": result["output"]}


@app.delete("/api/vms/{vm_name}")
def delete_vm(vm_name: str):
    """Snapshot automatique puis suppression de la VM."""
    # Snapshot de sécurité
    snapshot_name = "before-delete-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    appeler_bridge(["snapshot", vm_name, snapshot_name])

    result = appeler_bridge(["delete", vm_name])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    memory.sauvegarder_action("delete_vm", {"vm_name": vm_name}, result["output"], True)
    return {"success": True, "message": result["output"]}


@app.post("/api/vms/{vm_name}/start")
def start_vm(vm_name: str):
    """Démarre une VM."""
    result = appeler_bridge(["start", vm_name])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    memory.sauvegarder_action("start_vm", {"vm_name": vm_name}, result["output"], True)
    return {"success": True, "message": result["output"]}


@app.post("/api/vms/{vm_name}/stop")
def stop_vm(vm_name: str):
    """Arrête une VM."""
    result = appeler_bridge(["stop", vm_name])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    memory.sauvegarder_action("stop_vm", {"vm_name": vm_name}, result["output"], True)
    return {"success": True, "message": result["output"]}


@app.post("/api/vms/{vm_name}/snapshot")
def snapshot_vm(vm_name: str, request: SnapshotRequest):
    """Prend un snapshot d'une VM."""
    snapshot_name = request.snapshot_name or "auto-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    result = appeler_bridge(["snapshot", vm_name, snapshot_name])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    memory.sauvegarder_action(
        "snapshot_vm",
        {"vm_name": vm_name, "snapshot_name": snapshot_name},
        result["output"],
        True,
    )
    return {"success": True, "snapshot_name": snapshot_name, "message": result["output"]}


@app.get("/api/vms/{vm_name}/status")
def get_vm_status(vm_name: str):
    """Retourne l'état réel d'une VM."""
    result = appeler_bridge(["status", vm_name])
    lignes = result["output"].strip().splitlines()
    status = lignes[-1] if lignes else "Unknown"
    return {"vm_name": vm_name, "status": status}

# ---------------------------------------------------------------------
# Endpoints Templates
# ---------------------------------------------------------------------

@app.get("/api/templates")
def list_templates():
    """Liste les templates disponibles dans C:/InfraAgent/Templates."""
    templates_dir = r"C:\InfraAgent\Templates"
    if not os.path.exists(templates_dir):
        return {"templates": [], "error": "Templates directory not found"}

    templates = []
    for item in os.listdir(templates_dir):
        vmx = os.path.join(templates_dir, item, item + ".vmx")
        if os.path.exists(vmx):
            templates.append({"name": item, "path": vmx})

    return {"templates": templates, "total": len(templates)}

# ---------------------------------------------------------------------
# Endpoints Logs & Historique
# ---------------------------------------------------------------------

@app.get("/api/logs")
def get_logs(level: Optional[str] = None, source: Optional[str] = None, limit: int = 50):
    """Retourne les logs SQLite filtrés."""
    logs = memory.get_logs(level=level, source=source, limit=limit)
    return {"logs": logs, "total": len(logs)}


@app.get("/api/history")
def get_history(limit: int = 50):
    """Retourne l'historique des actions de l'agent."""
    actions = memory.get_actions_recentes(limit)
    return {"actions": actions, "total": len(actions)}


@app.get("/api/stats")
def get_stats():
    """Retourne les statistiques globales."""
    stats = memory.get_statistiques()
    vms_result = appeler_bridge(["list"])
    try:
        inventory = json.loads(vms_result["output"])
        running = sum(1 for v in inventory.values() if v.get("status") == "PoweredOn")
        stopped = sum(1 for v in inventory.values() if v.get("status") == "PoweredOff")
    except Exception:
        running = stopped = 0

    return {
        **stats,
        "vms_running": running,
        "vms_stopped": stopped,
        "monitoring_active": _monitoring_process is not None and _monitoring_process.poll() is None,
    }

# ---------------------------------------------------------------------
# Endpoint Chat
# ---------------------------------------------------------------------

@app.post("/api/chat")
def chat(request: ChatRequest):
    """
    Envoie une instruction à l'agent et retourne sa réponse.
    L'agent exécute les tool calls nécessaires et retourne le résultat.
    """
    import importlib.util

    # Importer function_agent dynamiquement
    spec = importlib.util.spec_from_file_location("function_agent", FUNCTION_AGENT_PATH)
    fa   = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fa)

    # Capturer la sortie de l'agent
    responses = []
    tool_calls_made = []

    original_dispatch = fa.TOOL_DISPATCH.copy()

    def wrapped_dispatch(nom_tool, args):
        result = original_dispatch[nom_tool](args)
        tool_calls_made.append({"tool": nom_tool, "args": args, "result": result[:200]})
        return result

    # Appel direct au LLM avec les tools
    from groq import Groq
    import os as _os

    groq_client = Groq(api_key=_os.getenv("GROQ_API_KEY"))
    contexte = memory.get_contexte_prompt()
    prompt = fa.SYSTEM_PROMPT + "\n\n" + contexte

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user",   "content": request.message},
    ]

    max_iter = 10
    final_response = ""

    for _ in range(max_iter):
        response = groq_client.chat.completions.create(
            model=fa.MODEL,
            messages=messages,
            tools=fa.TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        message      = response.choices[0].message
        raison_arret = response.choices[0].finish_reason

        tool_calls_data = None
        if message.tool_calls:
            tool_calls_data = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in message.tool_calls
            ]

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": tool_calls_data,
        })

        if raison_arret == "stop" or not message.tool_calls:
            final_response = message.content or ""
            if final_response:
                memory.sauvegarder_conversation(request.message, final_response)
            break

        for tool_call in message.tool_calls:
            nom_tool  = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            if nom_tool in fa.TOOL_DISPATCH:
                resultat = fa.TOOL_DISPATCH[nom_tool](args)
                succes   = not resultat.startswith("[ERREUR]")
                memory.sauvegarder_action(nom_tool, args, resultat[:500], succes)
                tool_calls_made.append({"tool": nom_tool, "args": args, "result": resultat[:200]})
            else:
                resultat = f"[ERREUR] Unknown tool : {nom_tool}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": resultat,
            })

    return {
        "response":   final_response,
        "tool_calls": tool_calls_made,
        "timestamp":  datetime.now().isoformat(),
    }

# ---------------------------------------------------------------------
# Endpoints Monitoring
# ---------------------------------------------------------------------

@app.get("/api/monitoring")
def monitoring_status():
    """Retourne le statut du monitoring."""
    global _monitoring_process
    running = _monitoring_process is not None and _monitoring_process.poll() is None
    return {
        "running": running,
        "pid": _monitoring_process.pid if running else None,
    }


@app.post("/api/monitoring/start")
def start_monitoring():
    """Démarre le monitoring en arrière-plan."""
    global _monitoring_process
    if _monitoring_process and _monitoring_process.poll() is None:
        return {"success": False, "message": "Monitoring already running."}

    monitor_path = os.path.join(BASE_DIR, "agent", "monitor.py")
    _monitoring_process = subprocess.Popen(
        [sys.executable, monitor_path],
        cwd=BASE_DIR,
        encoding="utf-8",
    )
    return {"success": True, "pid": _monitoring_process.pid, "message": "Monitoring started."}


@app.post("/api/monitoring/stop")
def stop_monitoring():
    """Arrête le monitoring."""
    global _monitoring_process
    if not _monitoring_process or _monitoring_process.poll() is not None:
        return {"success": False, "message": "Monitoring is not running."}
    _monitoring_process.terminate()
    _monitoring_process = None
    return {"success": True, "message": "Monitoring stopped."}

# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "InfraAgent API", "version": "1.0.0"}
