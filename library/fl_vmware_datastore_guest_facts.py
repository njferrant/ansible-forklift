#!/usr/bin/env python

try:
    import pyVmomi
    from pyVmomi import vim
except ImportError:
    pass

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_text
from ansible.module_utils.vmware import PyVmomi, vmware_argument_spec, find_datastore_by_name


class PyVmomiHelper(PyVmomi):
    def __init__(self, module):
        super(PyVmomiHelper, self).__init__(module)

        self.datastore_name = module.params['datastore_name']
        self.ds = self.find_datastore_by_name(self.datastore_name)
        if self.ds is None:
            self.module.fail_json(msg="Failed to find datastore %s." % self.datastore_name)

    def get_vms(self):
        '''returns a list of registered VMs on datastore '''
        return self.ds.vm


def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        datastore_name=dict(type='str', required=True),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
    )

    pyv = PyVmomiHelper(module)

    # get list of registered vms
    vms = pyv.get_vms()

    facts = []
    for vm in vms:
        try:
            facts.append(pyv.gather_facts(vm))
        except Exception as exc:
            module.fail_json(msg="Fact gather failed with exception %s" % to_text(exc))

    module.exit_json(instance=facts)

if __name__ == '__main__':
    main()
