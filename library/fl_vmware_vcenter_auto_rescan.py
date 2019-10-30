#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

try:
    from pyVmomi import vim, vmodl
except ImportError:
    pass

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vmware import PyVmomi, vmware_argument_spec
from ansible.module_utils._text import to_native


class VmwareVcenterSettings(PyVmomi):
    """Manage settings for a vCenter server"""

    def __init__(self, module):
        super(VmwareVcenterSettings, self).__init__(module)

        if not self.is_vcenter():
            self.module.fail_json(msg="You have to connect to a vCenter server!")

    def ensure(self):
        """Manage settings for a vCenter server"""
        result = dict(changed=False, msg='')

        if self.params['state'] in ['enabled','present']:
            host_rescan_filter = 'true'
        else:
            host_rescan_filter = 'false'

        # its possible that the hostRescanFilter setting doesn't exist in vCenter
        setting_exists = False
        change_option_list = []
        option_manager = self.content.setting
        for setting in option_manager.setting:
            if setting.key == 'config.vpxd.filter.hostRescanFilter':
                setting_exists = True
                if setting.value != host_rescan_filter:
                    result['changed'] = True
                    result['host_rescan_filter_previous'] = setting.value
                    change_option_list.append(
                        vim.option.OptionValue(key='config.vpxd.filter.hostRescanFilter', value=host_rescan_filter)
                    )

        # if the setting doesn't exist, lets create it
        if not setting_exists:
             result['changed'] = True
             result['host_rescan_filter_previous'] = None
             change_option_list.append(
                 vim.option.OptionValue(key='config.vpxd.filter.hostRescanFilter', value=host_rescan_filter)
             )

        if result['changed']:
            try:
                option_manager.UpdateOptions(changedValue=change_option_list)
            except (vmodl.fault.SystemError, vmodl.fault.InvalidArgument) as invalid_argument:
                self.module.fail_json(
                    msg="Failed to update option(s) as one or more OptionValue contains an invalid value: %s" %
                    to_native(invalid_argument.msg)
                )
            except vim.fault.InvalidName as invalid_name:
                self.module.fail_json(
                    msg="Failed to update option(s) as one or more OptionValue objects refers to a "
                    "non-existent option : %s" % to_native(invalid_name.msg)
                )
        else:
            result['msg'] = "vCenter settings already configured properly"

        self.module.exit_json(**result)

def main():
    """Main"""
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        state=dict(type='str', default='disabled', choices=['enabled','disabled','present','absent']),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False
    )

    setting = VmwareVcenterSettings(module)
    setting.ensure()

if __name__ == '__main__':
    main()
