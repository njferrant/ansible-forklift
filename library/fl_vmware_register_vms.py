#!usr/bin/env python


import random
import re
import time
from pyVim.connect import SmartConnect
import ssl
from pyVmomi import vim, vmodl
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native
from ansible.module_utils.vmware import vmware_argument_spec, PyVmomi, find_datastore_by_name, wait_for_task, find_object_by_name
from ansible.module_utils.urls import open_url
from ansible.module_utils.six.moves.urllib.parse import urlencode, quote

class PyVmomiHelper(PyVmomi):
    def __init__(self, module):
        super(PyVmomiHelper, self).__init__(module)

        self.hostname = self.params['hostname']
        self.username = self.params['username']
        self.password = self.params['password']
        self.validate_certs = self.params['validate_certs']
        self.datacenter = self.params['datacenter']
        self.datastore = self.params['datastore']
        self.cluster = self.params['cluster']
        self.vm_name_prefix = self.params['vm_name_prefix']
        self.vm_folder = self.params['vm_folder'].rstrip('/')

    def vmware_path(self, path):
        # Nick: Is this necissary? use urlencode to do this & collapse into vmx function
        ''' Constructs a URL path that VSphere accepts reliably '''
        path = "/folder/%s" % quote(path.lstrip("/"))
        # Due to a software bug in vSphere, it fails to handle ampersand in datacenter names
        # The solution is to do what vSphere does (when browsing) and double-encode ampersands, maybe others ?
        datacenter = self.datacenter.replace('&', '%26')
        if not path.startswith("/"):
            path = "/" + path
        params = dict(dsName=self.datastore)
        if datacenter:
            params["dcPath"] = datacenter
        params = urlencode(params)
        return "%s?%s" % (path, params)

    def examine_vmx(self, path):
        ''' downloads and examines a vmx file to extract vm display name '''
        remote_path = self.vmware_path(path)
        url = 'https://%s%s' % (self.hostname, remote_path)
        headers = {"Content-Type": "application/octet-stream"}
        resp = open_url(url, headers=headers, method='GET', timeout=30, url_username=self.username,
                        url_password=self.password, validate_certs=self.validate_certs, force_basic_auth=True)

        resp = resp.readlines()

        displayName = None
        for line in resp:
            if 'displayName' in line:
                line = re.sub(r'\n|"', '', line)
                displayName = line.split(' = ')[1]
                break

        if not displayName:
            self.module.fail_json(msg="File '[ %s ] %s' is missing 'displayName' key" % (self.datastore, path))

        return displayName

    def get_registered_vms(self, datastore):
        # holds a list of vmx files for registered vms
        registered_vmx_files = []

        # iterate over each vm in the datastore to find their vmx file name
        for vm in datastore.vm:
            # get vmx file name of registered vm and append file basename to list
            # TODO: use full path for comparison in case of duplicate file basename
            fileName = vm.config.files.vmPathName.split("/")[1]
            registered_vmx_files.append(fileName)

        return registered_vmx_files

    def get_unreg_vms(self, datastore):
        # Get a list of registered systems vmx files to diff against all vmx files
        registered_vmx_files = self.get_registered_vms(datastore)

        # Build search spec for finding all vmx files on datastore
        fileBrowser = datastore.browser
        searchSpec = vim.HostDatastoreBrowserSearchSpec()
        searchSpec.matchPattern = "*vmx"

        # search datastore using searchSpec
        task = fileBrowser.SearchDatastoreSubFolders_Task("[" + datastore.summary.name + "]", searchSpec)
        changed, results = wait_for_task(task)

        # diff list of all found vmx files against list of registered vmx files.
        # this will create our list of vmx files of unregistered vms.
        unreg_vmx_results = {}
        for result in results:
          # this shouldn't be defined here. should pass in "[ datastore ] folder/file.vmx" to examine vmx
          file = result.file[0].path
          folder = result.folderPath.split("] ")[1]
          path = folder + file
          if (file not in registered_vmx_files and ".snapshot" not in folder):
            # fetch the displayName from the vmx file. using the vmx file name is
            # not reliable if the vm was renamed and not storage vmotioned.
            #
            # examine_vmx should return a json blob. should we return more besides
            # displayName and path in the json blob? all vmx info?
            displayName = self.examine_vmx(path)
            unreg_vmx_results[displayName] = { "path": path,
                                               "datastore": self.datastore }

        return unreg_vmx_results

    def apply(self):
        # Find folder obj to place VM. Search for this first to fail fast.
        folder = self.content.searchIndex.FindByInventoryPath(self.vm_folder)
        if folder is None:
            self.module.fail_json(msg="Folder path '%s' does not exist" % self.vm_folder)

        # Find datacenter. Required for finding cluster and for examine VMX task.
        datacenter = self.find_datacenter_by_name(self.datacenter)
        if datacenter is None:
            self.module.fail_json(msg="Datacenter '%s' not found." % self.datacenter)

        # Find cluster object to get default resource pool (needed by RegisterVM_Task())
        cluster = self.find_cluster_by_name(self.cluster, datacenter)
        if cluster is None:
            self.module.fail_json(msg="Cluster '%s' not found for datacenter '%s'." % (self.datacenter, self.datacenter))

        resource_pool = cluster.resourcePool

        datastore = self.find_datastore_by_name(self.datastore)
        if datastore is None:
            self.module.fail_json(msg="Datastore '%s' not found." % self.datastore)

        # browse datastore to find unregistered vms
        unreg_vmx_results = self.get_unreg_vms(datastore)

        # Rather than keep track of changed result of all VMs getting registered,
        # set changed status if there is at least 1 VM that needs registered.
        if unreg_vmx_results:
            changed = True
        else:
            changed = False

        for displayName in unreg_vmx_results:
            name = self.vm_name_prefix + displayName
            path = str("[" + self.datastore + "] " + unreg_vmx_results[displayName]["path"])
            # pick a random esxi host to use for vm registrations
            esxi = random.choice(self.get_all_hosts_by_cluster(self.cluster))

            task = folder.RegisterVM_Task(path=path, asTemplate=False, name=name, pool=resource_pool, host=esxi)
            try:
                result, info = wait_for_task(task)
            except Exception as task_e:
                self.module.fail_json(msg=to_native(task_e))

        return changed, unreg_vmx_results

def main():

    #This holds the result that holds values that the script exits with.
    result = { "changed": False }

    argument_spec = vmware_argument_spec()
    argument_spec.update(
        datacenter=dict(type='str', required=True),
        cluster=dict(type='str', required=True),
        datastore=dict(type='str', required=True),
        vm_name_prefix=dict(type='str', required=True),
        vm_folder=dict(type='str', required=True,)
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    #this call instantiates an instance of the helper method class which
    #inherits the methods of its parent, which is PyVmomi. That way,
    #you can write your own methods for your PyVmomi objects or you can
    #use the preexisting methods.
    pyv = PyVmomiHelper(module)
    changed, results = pyv.apply()

    module.exit_json(changed=changed, result=results)

if __name__ == '__main__':
    main()


