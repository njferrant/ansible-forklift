# Ansible Forklift: Lift and Shift Production Into Testbed
Use NetApp, VMware, and Ansible to forklift a production virtual machine environment into a test environment. Used at Hughes Network Systems, and demoed at NetApp Insight 2019.

## Using Forklift

### Application Requirements

* NetApp ONTAP 
* Ansible - 2.8+
* vCenter - 6.5+

### Environment Requirements

* NetApp
  - Established SnapMirror for all datastore volumes in your inventory
  - All volumes only contain one lun, named `lun1`
* vCenter
  - Folder structure for VM's, datastores, and networks
  - Testbed Networks
* Networking
  - The assumption is that each testbed contins networks that overlap with their production counterpart.
* Bastion node
  - Linux server acting as an ssh proxy to each testbed you create.

### Quickstart

1. Customize the `inventory/hosts.yml` inventory file, which will use your NetApp volume names as inventory hosts.
2. Export VMware environment variables to be consumed by the VMware modules.
3. Export the `vmware_folder` environment variable used by the `vmware_folder_inventory.py` inventory script. Documentation can be found in the dynamic inventory script.
4. Run either the SAN or NAS playbook, replacing `INSTANCE_NAME` with your UAT instance. The assumption is that will be UAT1, UAT2, etc.
`ansible-playbook playbooks/san_all_in_one.yml -e uat_instance=<INSTANCE_NAME>`
