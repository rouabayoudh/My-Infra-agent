"""
llm_agent.py
Envoie le contenu du servers.yaml a l'API Groq (LLaMA 3.3 70B)
et recupere un fichier Terraform (main.tf) genere par le modele.
"""

import os
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """Tu es un expert Terraform specialise dans l'automatisation
d'infrastructure VMware Workstation Pro.

CONTEXTE TECHNIQUE OBLIGATOIRE :
Terraform n'a pas de provider officiel pour VMware Workstation.
La solution retenue est d'utiliser la ressource native "terraform_data"
avec un provisioner "local-exec" qui appelle un script Python local
nomme "vmware_bridge.py" situe dans "../agent/tools/vmware_bridge.py".

Ce script accepte exactement ces commandes :
  python ../agent/tools/vmware_bridge.py create <template_id> <vm_name>
  python ../agent/tools/vmware_bridge.py delete <vm_name>

REGLES ABSOLUES :
1. N'utilise JAMAIS de provider Terraform externe (pas de vmworkstation,
   pas de vsphere, pas de null provider).
2. Utilise UNIQUEMENT la ressource "terraform_data" (native Terraform, 
   aucun provider requis).
3. Le champ "triggers_replace" doit contenir vm_name et template_id.
4. Le provisioner de creation appelle : create <template_id> <vm_name>
5. Le provisioner de destruction (when = destroy) appelle : delete <vm_name>
6. Utilise TOUJOURS self.triggers_replace.vm_name et 
   self.triggers_replace.template_id dans les commandes.
7. Le template_id correspond au champ "template" du YAML, sans extension.
8. Reponds UNIQUEMENT avec le code Terraform brut.
   Pas d'explication, pas de markdown, pas de backticks.

EXEMPLE DE SORTIE ATTENDUE pour un serveur nomme "srv-dev-web-01"
avec template "ubuntu-22-base" :

resource "terraform_data" "srv_dev_web_01" {
  triggers_replace = {
    vm_name     = "srv-dev-web-01"
    template_id = "ubuntu-22-base"
  }

  provisioner "local-exec" {
    command = "python ../agent/tools/vmware_bridge.py create ${self.triggers_replace.template_id} ${self.triggers_replace.vm_name}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "python ../agent/tools/vmware_bridge.py delete ${self.triggers_replace.vm_name}"
  }
}

Genere exactement ce format pour chaque serveur du YAML fourni.
"""


def _sanitize_resource_name(vm_name: str) -> str:
    """
    Terraform n'accepte pas les tirets dans les noms de ressources.
    srv-dev-web-01 -> srv_dev_web_01
    """
    return re.sub(r"[^a-zA-Z0-9_]", "_", vm_name)


def generate_terraform(yaml_path: str, output_path: str) -> str:
    """
    Lit le fichier YAML brut, l'envoie a Groq/LLaMA, et ecrit le
    fichier main.tf genere dans output_path.
    Retourne le contenu genere.
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_content = f.read()

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": yaml_content},
        ],
        temperature=0,  # Deterministe — critique pour du HCL
    )

    generated_tf = response.choices[0].message.content.strip()

    # Filet de securite : retirer les balises markdown si le modele
    # les a quand meme ajoutees malgre la consigne
    generated_tf = (
        generated_tf
        .replace("```hcl", "")
        .replace("```terraform", "")
        .replace("```", "")
        .strip()
    )
    # Correction du bug LLaMA : accolade fermante en doublon en fin de fichier
    # On compte les ouvrantes et fermantes — si fermantes > ouvrantes, on supprime
    # la derniere ligne tant que le desequilibre persiste
    lines = generated_tf.splitlines()
    while lines:
        opens = generated_tf.count("{")
        closes = generated_tf.count("}")
        if closes > opens and lines[-1].strip() == "}":
            lines.pop()
            generated_tf = "\n".join(lines)
        else:
            break
    generated_tf = "\n".join(lines)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(generated_tf)

    return generated_tf


if __name__ == "__main__":
    tf_code = generate_terraform("input/servers.yaml", "terraform/main.tf")
    print("Fichier terraform/main.tf genere avec succes.")
    print("--- Apercu ---")
    print(tf_code[:800])
