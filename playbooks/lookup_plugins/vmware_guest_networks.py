# python 3 headers, required if submitting to Ansible
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = """
lookup: vmware_guest_networks
author: Nick Ferrant
version_added: "2.9"
short_description: Query VMware Guest Network Info
description:
  - Uses the vCenter REST API to return a list of networks attached to a
    virtual machine. The list can be transformed via a passed in network map,
    and used by the vmware_guest module to change a guests networks.
requirements:
  - requests
  - jmespath
  - vCenter >= 6.5
options:
  _terms:
    description: The name of the vmware guest to query.
    required: True
  network_map:
    description:
    - A list of dicts used to transform the results returned by the query.
      Each dict must have a 'src' key - representing the network name you
      want to match and transform, and a 'dest' key - representing the network
      name you want to change the match to. If there is no 'src' match,
      the network name will be changed to 'quarentine'.
  provider:
    description:
    - A dict containing the vCenter credentials. Standard VMware env variables
      are used as fallback if this option is not used.
"""

EXAMPLES = """
- name: change a guests networks
  vmware_guest:
    hostname: vc01
    username: admin
    password: password
    validate_certs: false
    name: "{{ inventory_hostname }}"
    datacenter: dc01
    cluster: rack01
    networks: "{{ lookup('vmware_guest_networks', inventory_hostname, network_map=network_map, provider=provider) }}"
  vars:
    provider:
      host: vc01
      user: admin
      password: password
      validate_certs: false
    network_map:
      - src: "frontend dmz"
        dest: "backend app"

# all of the examples below use credentials that are set using env variables
# export VMWARE_HOST=vc01
# export VMWARE_USER=admin
# export VMWARE_PASSWORD=password
# export VMWARE_VALIDATE_CERTS=false

- name: set a dev vm's networks based on its prod counterpart
  vmware_guest:
    name: "{{ inventory_hostname }}"
    datacenter: dc01
    cluster: rack01
    networks: "{{ lookup('vmware_guest_networks', inventory_hostname, network_map=network_map, provider=provider) }}"
  vars:
    provider:
      host: vc02
    network_map:
      - src: "prod|app-dmz"
        dest: "dev|app-dmz"
"""

RETURN = """
obj_type:
  description:
    - The object type specified in the terms argument
  returned: always
  type: complex
  contains:
    obj_field:
      - One or more obj_type fields as specified by return_fields argument or
        the default set of fields as per the object type
"""

import os
import json
import jmespath
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display

display = Display()

AUTH_ARG_SPEC = {
    'host': {},
    'user': {},
    'password': {
        'no_log': True,
    },
    'validate_certs': {
        'type': 'bool',
    },
}

class GuestNetworksLookup:

    def run(self, terms, variables=None, **kwargs):
        ret = []

        for term in terms:
            display.debug("File lookup term: %s" % term)

            self.provider = kwargs.pop('provider', {})
            network_map = kwargs.pop('network_map', [])
            if len(network_map) == 0:
                raise AnsibleError("network map issue")

            # create api session with vcenter
            self.connect_to_api()
            # get vm summary info
            vminfo = self.get_vm_by_name(term)
            # get squashed list of network oid's from returned vminfo
            network_ids = jmespath.search("[*].value.backing.network", vminfo['value']['nics'])
            # get json dictionary of all networks that vm is attached to
            networks = self.get_networks_by_id(network_ids)

            output = []
            # loop over each nic to build output
            for nic in vminfo['value']['nics']:
                moid = nic['value']['backing']['network']
                # get network name when moid matches
                network_name = jmespath.search("[?network=='%s'].name" % moid, networks['value'])[0]
                # when name matches a 'src' in our network map, overwrite name
                # with the value of the corresponding 'dest'. if no name matches
                # then network name will be set to 'quarentine'
                name = 'quarantine'
                for item in network_map:
                    if item['src'] == network_name:
                        name = item['dest']
                        break

                info = { "label": nic['value']['label'],
                         "name": name
                       }
                output.append(info)
            ret.append(output)
        return ret

    def connect_to_api(self):
        # If authorization variables aren't defined, look for them in environment variables
        # Credit: ansible k8s module utils
        auth_args = AUTH_ARG_SPEC.keys()
        auth_params = self.provider

        for arg in auth_args:
            if auth_params.get(arg) is None:
                env_value = os.getenv('VMWARE_{0}'.format(arg.upper()), None)
                if not env_value:
                    raise AnsibleError(
                        "Error: '%s' not specified in connection parameters. Specify the parameter in the 'provider' "
                        "argument, or set environment variable 'VMWARE_%s'" % (arg,arg.upper())
                    )
                if AUTH_ARG_SPEC[arg].get('type') == 'bool':
                    env_value = env_value.lower() not in ['0', 'false', 'no']
                auth_params[arg] = env_value

        self.s = requests.Session()
        if not auth_params['validate_certs']:
            self.s.verify = False
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

        resp = self.s.post('https://%s/rest/com/vmware/cis/session' % auth_params['host'],auth=(auth_params['user'],auth_params['password']))
        if resp.status_code == 401:
            raise AnsibleError("Unable to log on to vCenter at %s as %s: Unauthorized" % (auth_params['host'], auth_params['user']))

        sid = resp.json()['value']
        self.s.headers.update({'vmware-api-session-id': sid})

    # Function to get all the VMs from vCenter inventory
    def get_vm_by_name(self, name):
        ''' returns the moid of a vm '''
        # get vm moid from the vm summary
        resp = self.s.get('https://%s/rest/vcenter/vm?filter.names=%s' % (self.provider['host'], name))
        vm_summary = json.loads(resp.text)

        if len(vm_summary['value']) == 0:
            raise AnsibleError("Error: Virtual Machine %s in vCenter %s not found" % (name, self.provider['host']))

        # get all vm details using the vm moid
        # note: currently if someone is not authorized, vm_summary doesnt have a value list, throwing a key error
        moid = vm_summary['value'][0]['vm']
        resp = self.s.get('https://%s/rest/vcenter/vm/%s' % (self.provider['host'], moid))
        return json.loads(resp.text)

    def get_networks_by_id(self, network_ids):
        # build our parameter filter spec of network id's
        params = {}
        for id in network_ids:
            params['filter.networks.%s' % (network_ids.index(id)+1)] = id

        resp = self.s.get('https://%s/rest/vcenter/network' % self.provider['host'], params=params)
        return json.loads(resp.text)

    def __del__(self):
        if self.s.headers['vmware-api-session-id']:
            self.s.delete('https://%s/rest/com/vmware/cis/session' % self.provider['host'])


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        return GuestNetworksLookup().run(terms, variables=variables, **kwargs)
