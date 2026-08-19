resource "terraform_data" "srv_dev_web_01" {
  triggers_replace = {
    vm_name     = "srv-dev-web-01"
    template_id = "ubuntu-22.04"
  }

  provisioner "local-exec" {
    command = "python ../agent/tools/vmware_bridge.py create ${self.triggers_replace.template_id} ${self.triggers_replace.vm_name}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "python ../agent/tools/vmware_bridge.py delete ${self.triggers_replace.vm_name}"
  }
}