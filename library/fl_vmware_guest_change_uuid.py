#!/usr/bin/env python


try:
    import pyVmomi
    from pyVmomi import vim, vmodl
except ImportError:
    pass

from uuid import uuid4 as uuid
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_text
from ansible.module_utils.vmware import PyVmomi, vmware_argument_spec, wait_for_task


def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
        name_match=dict(type='str', choices=['first', 'last'], default='first'),
        uuid=dict(type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=False,
                           mutually_exclusive=[
                               ['name', 'uuid'],
                           ],
                           )

    result = dict(changed=False,)

    pyv = PyVmomi(module)

    # Check if the VM exists before continuing
    vm = pyv.get_vm()

    if vm:
        facts = pyv.gather_facts(vm)
        power_state = facts['hw_power_status'].lower()

        # VMware will fail the ReconfigVM_Task if the VM is powered on. For idempotency
        # in our UAT automation, we need to exit 'OK' and not change the VM if it is powered on.
        if power_state == 'poweredoff':
            result['uuid'] = str(uuid())
            config_spec = vim.vm.ConfigSpec()
            config_spec.uuid = result['uuid']
            try:
                task = vm.ReconfigVM_Task(config_spec)
                result['changed'], info = wait_for_task(task)
            except vmodl.fault.InvalidRequest as e:
                self.module.fail_json(msg="Failed to modify bios.uuid of virtual machine due to invalid configuration "
                                          "parameter %s" % to_native(e.msg))

    else:
        module.fail_json(msg="Unable to set bios uuid for non-existing virtual machine : '%s'" % (module.params.get('uuid') or module.params.get('name')))

    module.exit_json(**result)


if __name__ == '__main__':
    main()
