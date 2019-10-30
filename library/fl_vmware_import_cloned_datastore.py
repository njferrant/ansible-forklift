#!/usr/bin/env python


try:
    from pyVmomi import vim, vmodl
except ImportError:
    pass

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vmware import vmware_argument_spec, PyVmomi, find_datastore_by_name, wait_for_task, find_obj


class VMwareHostDatastore(PyVmomi):
    def __init__(self, module):
        super(VMwareHostDatastore, self).__init__(module)

        self.datacenter_name = module.params['datacenter_name']
        self.datastore_name = module.params['datastore_name']
        self.esxi_hostname = module.params['esxi_hostname']
        self.esxi_hostname = module.params['esxi_hostname']
        self.vmfs_device_name = module.params['vmfs_device_name']
        self.folder_name = module.params['folder_name']

        self.esxi = self.find_hostsystem_by_name(self.esxi_hostname)
        if self.esxi is None:
            self.module.fail_json(msg="Failed to find ESXi hostname %s." % self.esxi_hostname)

        if self.folder_name:
            self.folder = find_obj(self.content, [vim.Folder], self.folder_name, first=True)
            if self.folder is None:
                self.module.fail_json(msg="Failed to find storage folder '%s'. Make sure the folder exists, "
                                          "or remove module parameter folder_name." % self.folder_name)

        self.check_datastore_host_state()

    def check_datastore_host_state(self):
        storage_system = self.esxi.configManager.storageSystem
        host_file_sys_vol_mount_info = storage_system.fileSystemVolumeInfo.mountInfo
        for host_mount_info in host_file_sys_vol_mount_info:
            # if datastore already mounted, exit module with 'ok' status
            if host_mount_info.volume.name == self.datastore_name:
                self.module.exit_json(changed=False)

    def mount_vmfs_datastore_host(self):
        host_ds_system = self.esxi.configManager.datastoreSystem

        # create list of available disks that the esxi host can see
        available_vmfs_disks = []
        for disk in host_ds_system.QueryAvailableDisksForVmfs():
            available_vmfs_disks.append(disk.canonicalName)

        if self.vmfs_device_name not in available_vmfs_disks:
            self.module.fail_json(msg="VMFS device specified is not available on host %s" % self.esxi_hostname,
                                  available_vmfs_disks=available_vmfs_disks)

        spec = vim.host.UnresolvedVmfsResignatureSpec()
        spec.extentDevicePath = '/vmfs/devices/disks/%s:1' % self.vmfs_device_name

        # probably don't need to assign return values of 'wait_for_task'
        changed, result = wait_for_task(host_ds_system.ResignatureUnresolvedVmfsVolume(spec))
        # the result of 'result' is the datastore object.
        # TODO: error handling for below tasks. Can't use wait_for_task as these tasks
        # don't have a task.info.result, leading to the error: AttributeError: 'NoneType' object has no attribute 'info'
        ds = result.result
        ds.RenameDatastore(self.datastore_name)
        if self.folder:
            self.folder.MoveInto([ds])

        self.module.exit_json(changed=changed)

def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        datacenter_name=dict(type='str', required=True),
        datastore_name=dict(type='str', required=True),
        vmfs_device_name=dict(type='str'),
        esxi_hostname=dict(type='str', required=True),
        folder_name=dict(type='str', required=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    pyv = VMwareHostDatastore(module)
    pyv.mount_vmfs_datastore_host()


if __name__ == '__main__':
    main()
