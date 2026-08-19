"""
memory.py — Mémoire persistante de l'agent via SQLite.

Stocke :
  - L'historique complet des conversations (instructions + réponses)
  - L'historique des actions exécutées (tool calls + résultats)
  - Un résumé contextuel injecté dans chaque nouvelle session

Usage :
    from memory import AgentMemory
    mem = AgentMemory()
    mem.sauvegarder_action("create_vm", {"vm_name": "srv-dev-web-01"}, "OK")
    mem.sauvegarder_conversation("Crée une VM", "VM créée avec succès")
    contexte = mem.get_contexte_prompt()
"""

import os
import sqlite3
import json
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "agent", "state", "memory.db")


class AgentMemory:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._initialiser_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialiser_db(self) -> None:
        """Crée les tables si elles n'existent pas."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    reponse     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS actions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    tool_name   TEXT NOT NULL,
                    arguments   TEXT NOT NULL,
                    resultat    TEXT NOT NULL,
                    succes      INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    resume      TEXT NOT NULL
                );
            """)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Sauvegarde
    # ------------------------------------------------------------------

    def sauvegarder_conversation(self, instruction: str, reponse: str) -> None:
        """Sauvegarde une paire instruction/réponse."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (timestamp, instruction, reponse) VALUES (?, ?, ?)",
                (self._now(), instruction, reponse)
            )

    def sauvegarder_action(self, tool_name: str, arguments: dict, resultat: str, succes: bool = True) -> None:
        """Sauvegarde un appel de tool avec son résultat."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO actions (timestamp, tool_name, arguments, resultat, succes) VALUES (?, ?, ?, ?, ?)",
                (self._now(), tool_name, json.dumps(arguments, ensure_ascii=False), resultat, int(succes))
            )

    def sauvegarder_session(self, resume: str) -> None:
        """Sauvegarde un résumé de session."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (timestamp, resume) VALUES (?, ?)",
                (self._now(), resume)
            )

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def get_actions_recentes(self, limit: int = 20) -> list[dict]:
        """Retourne les N dernières actions exécutées."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actions ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversations_recentes(self, limit: int = 10) -> list[dict]:
        """Retourne les N dernières conversations."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_vms_creees(self) -> list[dict]:
        """Retourne toutes les VMs créées avec succès et pas encore supprimées."""
        with self._connect() as conn:
            # VMs créées
            creees = conn.execute(
                """SELECT arguments, timestamp FROM actions
                   WHERE tool_name = 'create_vm' AND succes = 1
                   ORDER BY timestamp DESC""",
            ).fetchall()

            # VMs supprimées
            supprimees = conn.execute(
                """SELECT arguments FROM actions
                   WHERE tool_name = 'delete_vm' AND succes = 1""",
            ).fetchall()

        noms_supprimes = set()
        for s in supprimees:
            try:
                args = json.loads(s["arguments"])
                noms_supprimes.add(args.get("vm_name", ""))
            except Exception:
                pass

        vms_actives = []
        for c in creees:
            try:
                args = json.loads(c["arguments"])
                nom  = args.get("vm_name", "")
                if nom and nom not in noms_supprimes:
                    vms_actives.append({
                        "vm_name":    nom,
                        "template":   args.get("template_id", "?"),
                        "created_at": c["timestamp"][:19].replace("T", " "),
                    })
            except Exception:
                pass

        return vms_actives

    def get_contexte_prompt(self, max_actions: int = 15) -> str:
        """
        Génère un bloc de contexte à injecter dans le prompt système
        au début de chaque nouvelle session.
        """
        actions  = self.get_actions_recentes(max_actions)
        vms      = self.get_vms_creees()

        if not actions and not vms:
            return "No previous session history."

        lignes = ["=== MEMORY FROM PREVIOUS SESSIONS ===\n"]

        # VMs actuellement actives selon la mémoire
        if vms:
            lignes.append("VMs created and not yet deleted :")
            for vm in vms:
                lignes.append(
                    f"  - {vm['vm_name']} (template: {vm['template']}, created: {vm['created_at']})"
                )
            lignes.append("")

        # Historique des actions récentes
        if actions:
            lignes.append("Recent actions (most recent first) :")
            for a in actions:
                try:
                    args = json.loads(a["arguments"])
                except Exception:
                    args = {}
                statut = "OK" if a["succes"] else "FAILED"
                date   = a["timestamp"][:19].replace("T", " ")
                lignes.append(
                    f"  [{date}] [{statut}] {a['tool_name']}({args})"
                )
            lignes.append("")

        lignes.append("=== END OF MEMORY ===")
        return "\n".join(lignes)

    def get_statistiques(self) -> dict:
        """Retourne des statistiques globales sur l'utilisation de l'agent."""
        with self._connect() as conn:
            nb_conversations = conn.execute(
                "SELECT COUNT(*) as n FROM conversations"
            ).fetchone()["n"]

            nb_actions = conn.execute(
                "SELECT COUNT(*) as n FROM actions"
            ).fetchone()["n"]

            nb_succes = conn.execute(
                "SELECT COUNT(*) as n FROM actions WHERE succes = 1"
            ).fetchone()["n"]

            tools_frequents = conn.execute(
                """SELECT tool_name, COUNT(*) as n
                   FROM actions GROUP BY tool_name
                   ORDER BY n DESC LIMIT 5"""
            ).fetchall()

        return {
            "conversations":  nb_conversations,
            "actions_totales": nb_actions,
            "actions_reussies": nb_succes,
            "tools_frequents": [dict(r) for r in tools_frequents],
            "vms_actives": len(self.get_vms_creees()),
        }

    def afficher_historique(self, limit: int = 20) -> None:
        """Affiche l'historique des actions dans le terminal."""
        actions = self.get_actions_recentes(limit)

        print("\n" + "=" * 60)
        print("  Historique des actions")
        print("=" * 60)

        if not actions:
            print("  Aucune action enregistrée.")
        else:
            for a in reversed(actions):
                try:
                    args = json.loads(a["arguments"])
                except Exception:
                    args = {}
                statut = "[OK]    " if a["succes"] else "[FAILED]"
                date   = a["timestamp"][:19].replace("T", " ")
                print(f"  {statut} {date} | {a['tool_name']}({args})")

        stats = self.get_statistiques()
        print("\n" + "-" * 60)
        print(f"  Total actions    : {stats['actions_totales']}")
        print(f"  Actions réussies : {stats['actions_reussies']}")
        print(f"  Conversations    : {stats['conversations']}")
        print(f"  VMs actives      : {stats['vms_actives']}")
        print("=" * 60 + "\n")
