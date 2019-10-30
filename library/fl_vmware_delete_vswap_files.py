#!/usr/bin/env python


try:
    from pyVmomi import vim, vmodl
except ImportError:
    pass

import time
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vmware import vmware_argument_spec, PyVmomi, find_datacenter_by_name, find_datastore_by_name, TaskError


class VMwareHostDatastore(PyVmomi):
    def __init__(self, module):
        super(VMwareHostDatastore, self).__init__(module)

        self.vswp_files = []
        self.vcenter = module.params['hostname']
        self.datacenter = module.params['datacenter']
        self.datastore = module.params['datastore']

        self.dc = find_datacenter_by_name(self.content, self.datacenter)
        if self.dc is None:
            self.module.fail_json(msg="Failed to find Datacenter %s " % self.datacenter)

        self.ds = find_datastore_by_name(self.content, self.datastore)
        if self.ds is None:
            self.module.fail_json(msg="Failed to find Datastore %s " % self.datastore)

        self.find_vswp_files()

        if len(self.vswp_files) > 0:
            self.delete_vswp_files()
        else:
            self.module.exit_json(changed=False)

    def find_vswp_files(self):
        dsbrowser = self.ds.browser

        search = vim.HostDatastoreBrowserSearchSpec()
        search.matchPattern = "*.vswp"
        search_ds = dsbrowser.SearchDatastoreSubFolders_Task("[%s]" % self.datastore, search)
        self.wait_for_task(search_ds)

        for result in search_ds.info.result:
            dsfolder = result.folderPath
            for file in result.file:
                try:
                    dsfile = file.path
                    vmfold = dsfolder.split("]")
                    vmfold = vmfold[1]
                    vmfold = vmfold[1:]
                    if ".snapshot" not in vmfold:
                        vswpurl = "https://%s/folder/%s%s?dcPath=%s&dsName=%s" % \
                                  (self.vcenter, vmfold, dsfile, self.datacenter, self.datastore)
                        self.vswp_files.append(vswpurl)
                except Exception, e:
                    print "Caught exception : " + str(e)
                    return -1

    def delete_vswp_files(self):
        # add check if self.vswp_files empty, return ok
        for file in self.vswp_files:
            self.wait_for_task(self.content.fileManager.DeleteFile(file, self.dc))

        self.module.exit_json(changed=True)

    def wait_for_task(self, task):
        while True:
            if task.info.state == vim.TaskInfo.State.success:
                return True, task.info.result
            if task.info.state == vim.TaskInfo.State.error:
                try:
                    raise TaskError(task.info.error)
                except AttributeError:
                    raise TaskError("An unknown error has occurred")
            if task.info.state == vim.TaskInfo.State.running:
                time.sleep(1)
            if task.info.state == vim.TaskInfo.State.queued:
                time.sleep(5)

def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        datacenter=dict(type='str', required=True),
        datastore=dict(type='str', required=True),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    VMwareHostDatastore(module)


if __name__ == '__main__':
    main()
