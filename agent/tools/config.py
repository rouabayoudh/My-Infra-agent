"""
Configuration centralisée pour vmware_bridge.py
Toutes les valeurs sensibles ou propres à la machine doivent être ici,
jamais en dur dans bridge.py.
"""

import os
from pathlib import Path

# --- Chemins VMware (Windows) ---
VMRUN_PATH = os.environ.get(
    "VMRUN_PATH",
    r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
)

# Dossier racine où TOUTES les VMs créées par InfraAgent doivent vivre.
# Sert de garde-fou anti path-traversal : aucune opération ne doit
# pouvoir sortir de ce dossier.
VMS_BASE_DIR = Path(os.environ.get(
    "VMS_BASE_DIR",
    r"C:\InfraAgent\VMs"
)).resolve()

# Dossier où sont rangés les templates (VMs de référence à cloner).
TEMPLATES_BASE_DIR = Path(os.environ.get(
    "TEMPLATES_BASE_DIR",
    r"C:\InfraAgent\Templates\ubuntu-22.04"
)).resolve()

# --- API REST VMware (vmrest) ---
VMREST_HOST = os.environ.get("VMREST_HOST", "127.0.0.1")
VMREST_PORT = os.environ.get("VMREST_PORT", "8697")
VMREST_USER = os.environ.get("VMREST_USER", "")
VMREST_PASSWORD = os.environ.get("VMREST_PASSWORD", "")
VMREST_BASE_URL = f"http://{VMREST_HOST}:{VMREST_PORT}/api"

# --- Fichier d'inventaire (source de vérité locale) ---
INVENTORY_PATH = Path(os.environ.get(
    "INVENTORY_PATH",
    str(Path(__file__).parent.parent / "state" / "inventory.json")
)).resolve()

# --- Gouvernance (doit matcher les règles du prompt système) ---
MAX_VCPU = 8
MAX_RAM_GB = 16
NAMING_PATTERN = r"^srv-(dev|staging|prod)-[a-z0-9]+-\d{2}$"

# --- Logging ---
LOG_PATH = Path(os.environ.get(
    "LOG_PATH",
    str(Path(__file__).parent.parent / "state" / "bridge.log")
)).resolve()
