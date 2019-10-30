#!/usr/bin/env python
# coding=utf-8

# 1. Overview
#
# Produces an ansible VMware dynmaic inventory with the following features:
#   - OS family groupings (e.g. linuxGuest, windowsGuest)
#   - Parent folder groupings based on folder paths supplied by the user. Group
#     variables can also be defined by the user.
#   - Speeds up inventory gather time by only fetching VM's under the folder
#     path(s) provided by the user.
#
# Note: This script was designed specifically for Hughes UAT Automation,
# although it can be ported elsewhere.
#
#
# 2. Requirements
#
# User inputs are passed in through environment variables. This decision was made
# with Ansible Tower inventory sources in mind (it generally only accepts env
# vars). Apart from the standard VMWARE login variables, The following environment
# vars are required:
#   - vmfolder_groups: a JSON (as a string) Data structure containing:
#         datacenter:
#           "/path/to/folder1":
#             var1: foo
#             var2: bar
#           "/path/to/folder2":
#             var1: baz
#
#
# 3. Examples
#
# This example uses the below env vars written in YAML, for use in Ansible Tower.
# If you are using this inventory via a CLI, export any env vars  as one line
# strings. This example also assumes that there is a linux vm in folder1, and a
# windows vm in folder 2.
#
#   vmfolder_groups: >-
#    {
#        "datacenter1": {
#            "/path/to/folder1": {
#                "var1": "foo",
#                "var2": "bar"
#            },
#            "/path/to/folder2": {
#                "var1": "baz"
#            }
#        }
#    }
#
# This would create the following inventory (example in ini format):
#
#   [all:children]
#   datacenter1-path-to-folder1
#   datacenter1-path-to-folder2
#   linuxGuest
#   windowsGuest
#
#   [datacenter1-path-to-folder1:vars]
#   var1=foo
#   var2=bar
#
#   [datacenter1-path-to-folder1]
#   some-linux-vm1
#
#   [datacenter1-path-to-folder2:vars]
#   var1=baz
#
#   [datacenter1-path-to-folder2]
#   some-windows-vm2
#
#   [linuxGuest]
#   some-linux-vm1
#
#   [windowsGuest]
#   some-windows-vm2
#
#
# 4. Vault Variables
#
# Ansible vault variables can be expressed as json and used with this inventory
# script. For example, lets take the following YAML vaulted variable:
#
#   my_password: !vault |
#     $ANSIBLE_VAULT;1.1;AES256
#     38303437373938646135323133616565303165633834366461386332333430363633653066376531
#     3437346431343639656462396464646564303966636462610a666235633038303036646363326265
#     66343231653037343561633033663861623939306339616132316335313466376539343738633664
#     6436336136373965630a326133393839656239353533356333316136313731636264643333626335
#     3961
#
# We can write the same variable as JSON like so:
#
#   {
#     "my_password": {
#         "__ansible_vault": "$ANSIBLE_VAULT;1.1;AES256\n383034373739386461353231336165653031656338343664613863323334303636336530663765313437346431343639656462396464646564303966636462610a666235633038303036646363326265663432316530373435616330336638616239393063396161323163353134663765393437386336646436336136373965630a3261333938396562393535333563333161363137316362646433336263353961"
#     }
#   }
#
# Note: to print human readable json stored as an environment variable:
# env |awk -F '=' '/vmfolder_groups/ {print $2}' |jq .

import atexit
import ssl
import os
import re
import sys
import json

try:
    from pyVmomi import vim, vmodl
    from pyVim.connect import SmartConnect, Disconnect
except ImportError:
    sys.exit("ERROR: This inventory script required 'pyVmomi' Python module, it was not able to load it")


class VMWareInventory(object):
    __name__ = 'VMWareInventory'

    @staticmethod
    def _empty_inventory():
        # the 'vmguests' group exsists to allow this inventory to be used as one of many
        # tower invnetory sources, and be called outside the 'all' group namespace.
        return {"all": {"children": ["vmguests"]}, "vmguests": {"children": []}, "_meta": {"hostvars": {}}}

    def __init__(self):
        self.inventory = VMWareInventory._empty_inventory()

        self.server = os.environ['VMWARE_SERVER']
        self.port = os.environ['VMWARE_PORT']
        self.username = os.environ['VMWARE_USERNAME']
        self.password = os.environ['VMWARE_PASSWORD']
        self.validate_certs = os.environ['VMWARE_VALIDATE_CERTS']
        if self.validate_certs in ['no', 'false', 'False', False]:
            self.validate_certs = False

        # need error catch for invalid json
        # will raise KeyError(key) if not set
        self.vmfolder_groups = json.loads(os.environ['vmfolder_groups'])

        self.content = self._get_content()

    def _get_content(self):
        kwargs = {'host': self.server,
          'user': self.username,
          'pwd': self.password,
          'port': int(self.port)}

        if hasattr(ssl, 'SSLContext') and not self.validate_certs:
            context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            context.verify_mode = ssl.CERT_NONE
            kwargs['sslContext'] = context

        try:
            si = SmartConnect(**kwargs)
        except ssl.SSLError as connection_error:
            if '[SSL: CERTIFICATE_VERIFY_FAILED]' in str(connection_error) and self.validate_certs:
                sys.exit("Unable to connect to ESXi server due to %s, "
                         "please specify validate_certs=False and try again" % connection_error)

        except Exception as exc:
            sys.exit("Unable to connect to ESXi server due to %s" % exc)

        if not si:
            sys.exit("Could not connect to the specified host using specified "
                     "username and password")
        atexit.register(Disconnect, si)
        content = si.RetrieveContent()

        return content

    def _get_all_objs(self, vimtype, folder=None, recurse=True):
        if not folder:
            folder = self.content.rootFolder

        obj = {}
        container = self.content.viewManager.CreateContainerView(folder, vimtype, recurse)
        for managed_object_ref in container.view:
            obj.update({managed_object_ref: managed_object_ref.name})
        return obj

    def _group_to_safe(self, word):
        ''' Converts 'bad' characters in a string to dashes so they can be used
         as Ansible groups '''
        return re.sub(r'[^A-Za-z0-9\-\.]', '-', word)

    def _hostname_to_safe(self, word):
        ''' Converts 'bad' characters in a string to underscores so they can be used
         as Ansible groups '''
        match = re.search(r"[^_]*", word)
        if match:
            return match.group(0)
        return word

    def _get_os_families(self):
        # get first compute resource of first datacenter
        computeResource = self.content.rootFolder.childEntity[0].hostFolder.childEntity[0]
        browser = computeResource.environmentBrowser

        self.os_families = {}
        for item in browser.QueryConfigOption().guestOSDescriptor:
            self.os_families[item.id] = item.family

    def get_vm_path(self, vm_name):
        """
        Function to find the path of virtual machine.
        Args:
            content: VMware content object
            vm_name: virtual machine managed object

        Returns: Folder of virtual machine if exists, else None

        """
        folder_name = None
        folder = vm_name.parent
        if folder:
            folder_name = folder.name
            fp = folder.parent
            # climb back up the tree to find our path, stop before the root folder
            while fp is not None and fp.name is not None and fp != self.content.rootFolder:
                folder_name = fp.name + '/' + folder_name
                try:
                    fp = fp.parent
                except Exception:
                    break
            folder_name = '/' + folder_name
        return folder_name

    def show(self):
        self._get_os_families()

        # iterate over all datacenters, then folder paths in user provided vmfolder_groups
        for datacenter in self.vmfolder_groups:
            for folderPath in self.vmfolder_groups[datacenter]:
                path = '%s/vm/%s' % (datacenter, folderPath.strip('/'))

                folder = self.content.searchIndex.FindByInventoryPath(path)

                try:
                    unsafeGroup = '%s/%s' % (datacenter, folderPath.strip('/'))
                    groupName = self._group_to_safe(unsafeGroup).lower()
                    #groupName = self._group_to_safe(folder.name).lower()
                except AttributeError:
                    sys.exit("Error: VMware folder does not exist at path '%s'" % folderPath)

                # create inv group if it doesn't exist and add group_vars
                if groupName not in self.inventory:
                    self.inventory[groupName] = {"hosts": [], "vars": {}}
                    self.inventory[groupName]["vars"] = self.vmfolder_groups[datacenter][folderPath]
                    self.inventory["vmguests"]["children"].append(groupName)

                vms = self._get_all_objs([vim.VirtualMachine], folder)
                for vm in vms:
                    try:
                        if vm.config.template:
                            continue
                    except Exception as e:
                        print(vm.name, e)

                    hostVars = {
                        "guest_display_name": vm.config.name,
                        "guest_os_id": vm.config.guestId,
                        "guest_os_family": self.os_families[vm.config.guestId],
                        "guest_folder": self.get_vm_path(vm),
                        "guest_instance_uuid": vm.config.instanceUuid,
                        "guest_power_state": vm.runtime.powerState,
                        "guest_tools_status": vm.guest.toolsStatus,
                        "guest_ip_address": vm.guest.ipAddress,
                        "guest_hostname": vm.guest.hostName
                    }

                    # Checks if vm has a UAT name (e.g. U1,U2,etc) and normalizes
                    # the inventory hostname
                    if re.search(r'^[Uu][0-9]', hostVars["guest_display_name"]):
                        name = self._hostname_to_safe(hostVars["guest_display_name"][2:].lower())
                    else:
                        name = hostVars["guest_display_name"].lower()

                    # add to inventory groups
                    self.inventory[groupName]["hosts"].append(name)
                    self.inventory["_meta"]["hostvars"][name] = hostVars

                    # create os family ansible group if it doesn't already exist
                    guestFamily = hostVars["guest_os_family"]
                    if guestFamily not in self.inventory:
                      self.inventory[guestFamily] = {"hosts": []}
                      self.inventory["vmguests"]["children"].append(guestFamily)
                    # add host to os family group
                    self.inventory[guestFamily]["hosts"].append(name)

        return json.dumps(self.inventory, indent=4, sort_keys=True)

if __name__ == "__main__":
    # Run the script
    print(VMWareInventory().show())
