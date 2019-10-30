#!/usr/bin/python

# (c) 2018 Piotr Olczak <piotr.olczak@redhat.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: na_ontap_gather_facts
author: Piotr Olczak (polczak@redhat.com)
extends_documentation_fragment:
    - netapp.na_ontap
short_description: NetApp information gatherer
description:
    - This module allows you to gather various information about ONTAP configuration
version_added: "2.7"
requirements:
    - netapp_lib
options:
    state:
        description:
            - Returns "info"
        default: "info"
        required: false
        choices: ['info']
'''

EXAMPLES = '''
- name: Get NetApp info (Password Authentication)
  na_ontap_gather_facts:
    state: info
    hostname: "na-vsim"
    username: "admin"
    password: "admins_password"

- debug:
    var: ontap_facts
'''

RETURN = '''
ontap_facts:
    description: Returns various information about NetApp cluster configuration
    returned: always
    type: dict
    sample: '{
        "ontap_facts": {
            "aggregate_info": {...},
            "cluster_node_info": {...},
            "net_ifgrp_info": {...},
            "net_interface_info": {...},
            "net_port_info": {...},
            "security_key_manager_key_info": {...},
            "security_login_account_info": {...},
            "volume_info": {...},
            "lun_info": {...},
            "storage_failover_info": {...},
            "vserver_login_banner_info": {...},
            "vserver_motd_info": {...},
            "vserver_info": {...}
    }'
'''

import traceback
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native
import ansible.module_utils.netapp as netapp_utils

try:
    import xmltodict
    HAS_XMLTODICT = True
except ImportError:
    HAS_XMLTODICT = False

try:
    import json
    HAS_JSON = True
except ImportError:
    HAS_JSON = False

HAS_NETAPP_LIB = netapp_utils.has_netapp_lib()


class NetAppGatherFacts(object):

    def __init__(self, module):
        self.module = module
        self.netapp_info = dict()

        if HAS_NETAPP_LIB is False:
            self.module.fail_json(msg="the python NetApp-Lib module is required")
        else:
            self.server = netapp_utils.setup_na_ontap_zapi(module=self.module)

    def call_api(self, call, query=None):
        api_call = netapp_utils.zapi.NaElement(call)
        result = None

        if query:
            for k, v in query.items():
                # Can v be nested?
                api_call.add_new_child(k, v)
        try:
            result = self.server.invoke_successfully(api_call, enable_tunneling=False)
            return result
        except netapp_utils.zapi.NaApiError as e:
            self.module.fail_json(msg="Error calling API %s: %s" %
                                  (call, to_native(e)), exception=traceback.format_exc())

    def get_generic_get_iter(self, call, attribute=None, field=None, query=None, children='attributes-list'):
        generic_call = self.call_api(call, query)

        if field is None:
            out = []
        else:
            out = {}

        attributes_list = generic_call.get_child_by_name(children)

        if attributes_list is None:
            return None

        for child in attributes_list.get_children():
            d = xmltodict.parse(child.to_string(), xml_attribs=False)

            if attribute is not None:
                d = d[attribute]

            item = json.loads(json.dumps(d))
           # if 'snapmirror' not in item['name'] and item['volume'] not in item['name']:
           #     if isinstance(field, str):
           #         unique_key = _finditem(d, field)
           #         out = out.copy()
           #         out.update({unique_key: convert_keys(json.loads(json.dumps(d)))})
           #     elif isinstance(field, tuple):
           #         unique_key = ':'.join([_finditem(d, el) for el in field])
           #         out = out.copy()
           #         out.update({unique_key: convert_keys(json.loads(json.dumps(d)))})
           #     else:
           #         out.append(convert_keys(json.loads(json.dumps(d))))
            if isinstance(field, str):
                unique_key = _finditem(d, field)
                out = out.copy()
                out.update({unique_key: convert_keys(json.loads(json.dumps(d)))})
            elif isinstance(field, tuple):
                unique_key = ':'.join([_finditem(d, el) for el in field])
                out = out.copy()
                out.update({unique_key: convert_keys(json.loads(json.dumps(d)))})
            else:
                out.append(convert_keys(json.loads(json.dumps(d))))

        return out

    def get_all(self):
        self.netapp_info['ontap_snapshot_facts'] = self.get_generic_get_iter(
            'snapshot-get-iter',
            attribute='snapshot-info',
						field='volume',
            query={'max-records': '2048'}
        )

        return self.netapp_info


# https://stackoverflow.com/questions/14962485/finding-a-key-recursively-in-a-dictionary
def _finditem(obj, key):

    if key in obj:
        return obj[key]
    for dummy, v in obj.items():
        if isinstance(v, dict):
            item = _finditem(v, key)
            if item is not None:
                return item
    return None


def convert_keys(d):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            v = convert_keys(v)
            out[k.replace('-', '_')] = v
    else:
        return d
    return out


def main():
    argument_spec = netapp_utils.na_ontap_host_argument_spec()
    argument_spec.update(dict(
        state=dict(default='info', choices=['info']),
        #exclude_snapmirror=dict(default='false'),
    ))

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    if not HAS_XMLTODICT:
        module.fail_json(msg="xmltodict missing")

    if not HAS_JSON:
        module.fail_json(msg="json missing")

    state = module.params['state']
    v = NetAppGatherFacts(module)
    g = v.get_all()
    result = {'state': state, 'changed': False}
    module.exit_json(ansible_facts=g, **result)


if __name__ == '__main__':
    main()
