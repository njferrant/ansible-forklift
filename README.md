# Ansible Forklift: Lift and Shift Production Into Testbed
Use NetApp, VMware, and Ansible to forklift a production virtual machine environment into a test environment. Used at Hughes Network Systems, and demoed at NetApp Insight 2019.

## Demo
[![Ansible Forklift Demo](http://img.youtube.com/vi/sEPM_Mq4G7o/0.jpg)](https://youtu.be/sEPM_Mq4G7o)

## TODO
(11-1-2019) I will be adding the following in the coming week:
* a list and description of all custom modules
* updated documentation for custom module
* diagram/overview of setup
* (maybe) workflow diagram of the automation

## Using Forklift

### Application Requirements

* NetApp ONTAP 
* Ansible - 2.8+
* vCenter - 6.5+

### Environment Requirements

* NetApp
  - Established SnapMirror for all datastore volumes in your inventory
  - All volumes only contain one lun, named `lun1`
* vCenter/VMware
  - Folder structure for VM's, datastores, and networks
  - Pre-created vmware networks that represent their production counterparts. Should be done for each UAT.
* Networking
  - The assumption is that each testbed contins networks that overlap with their production counterpart. Therefore you must make sure that each UAT is isolated.
* Bastion node
  - Linux server acting as an ssh proxy to each testbed you create.

### Quickstart

1. Customize the `inventory/hosts.yml` inventory file, which will use your NetApp volume names as inventory hosts.
2. Export VMware environment variables to be consumed by the VMware modules.
```
export VMWARE_HOST=vcenter.example.com
export VMWARE_USER=jdoe
export VMWARE_PASSWORD=supersecret
export VMWARE_PORT=443
export VMWARE_VALIDATE_CERTS=false
```
3. VMWare inventory scripts (as well as Ansible Tower/AWX vCenter credential) use slightly diffirent environment variables. I'm guessing there was a lack of communication. You can just paste the below to re-use the env vars from step 2:
```
export VMWARE_SERVER=$VMWARE_HOST
export VMWARE_USERNAME=$VMWARE_USER
```
4. Export the `vmfolder_groups` environment variable used by the `vmware_folder_inventory.py` inventory script. Documentation can be found in the dynamic inventory script. Also supports vaulted variables.
```
export vmfolder_groups='{"datacenter1":{"/path/to/folder1":{"var1":"foo","var2":"bar"},"/path/to/folder2":{"var1":"baz"}}}'
```
5. Run either the SAN or NAS "all in one" playbook, replacing `UAT1` in the example below with your UAT instance (e.g. UAT1, UAT2, etc.)
```
ansible-playbook playbooks/san_all_in_one.yml -e uat_instance=UAT1
```
6. To tear down a UAT, run one of the teardown playbooks, again specifying your UAT in a `uat_instance` extra variable: 
```
ansible-playbook playbooks/san_teardown.yml -e uat_instance=UAT1
```
