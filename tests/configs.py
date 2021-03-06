################################################################################
#
# Copyright (c) 2016, EURECOM (www.eurecom.fr)
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the FreeBSD Project.
#
################################################################################
# file config.py
# brief templates for testing juju service orchestrations
# author  navid.nikaein@eurecom.fr

"""
Service topology, descriptor, configurations, relationships, and machine templates
-----------

"""

"""
Minimum and maximum number of allowed service unit during the scaling
"""
MIN_UNIT = 1
MAX_UNIT = 2

"""
Service topology template defining the service paramters, which might be overloaded during the init_service
"""

test=['juju-gui','mysql']
sim1=['mysql', 'oai-hss', 'oai-epc','oaisim-enb-ue','juju-gui']
sim2=['mysql', 'oai-hss', 'oai-mme','oai-spgw','oaisim-enb-ue','juju-gui']
dran1=['mysql', 'oai-hss', 'oai-epc', 'oai-enb', 'juju-gui']
dran2=['mysql', 'oai-hss', 'oai-mme', 'oai-spgw','oai-enb', 'juju-gui']
cran1=['mysql', 'oai-hss', 'oai-epc', 'oai-enb', 'oai-rrh','juju-gui']
cran2=['mysql', 'oai-hss', 'oai-mme', 'oai-spgw','oai-enb', 'oai-rrh','juju-gui']

"""
Service descriptor template, which might be overloaded during the init_service
"""
service_descriptor = [{'service': 'juju-gui','series': 'trusty', 'charm': 'cs:trusty/juju-gui-130',              'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 1, 'mem': 1}, 'machine_spec': 'kvm:0', 'parent_id': '','container_type': 'kvm'},
                      {'service': 'mysql',   'series': 'trusty', 'charm': 'cs:trusty/mysql-55',                  'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 1, 'mem': 1}, 'machine_spec': 'kvm:0', 'parent_id': '','container_type': 'lxc'},
                      {'service': 'oai-hss', 'series': 'trusty', 'charm': 'cs:~navid-nikaein/trusty/oai-hss-13', 'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 1, 'mem': 1}, 'machine_spec': 'kvm:0', 'parent_id': '','container_type': 'kvm'},
                      {'service': 'oai-epc', 'series': 'trusty', 'charm': 'cs:~navid-nikaein/trusty/oai-epc-25', 'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 1, 'mem': 2}, 'machine_spec': 'kvm:0', 'parent_id': '','container_type': 'kvm'},
                          {'service': 'oai-enb', 'series': 'trusty', 'charm': 'cs:~navid-nikaein/trusty/oai-enb-18', 'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 4, 'mem': 8}, 'machine_spec': '0', 'parent_id': '','container_type': ''},
                      {'service': 'oai-rrh', 'series': 'trusty', 'charm': 'cs:~navid-nikaein/trusty/oai-rrh-10',  'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 2, 'mem': 8}, 'machine_spec': '0', 'parent_id': '','container_type': ''},
                      {'service': 'oai-mme', 'series': 'trusty', 'charm': 'cs:~navid-nikaein/trusty/oai-mme-1',  'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 1, 'mem': 2}, 'machine_spec': 'kvm:0', 'parent_id': '','container_type': ''},
                      {'service': 'oai-spgw', 'series': 'trusty', 'charm': 'cs:~navid-nikaein/trusty/oai-spgw-1',  'num_units': 1, 'max_unit': 2, 'constraints': {'cpu-cores': 1, 'mem': 2}, 'machine_spec': 'kvm:0', 'parent_id': '','container_type': ''}

]


"""
Service configuration template for any service topology
"""
service_config = {
    'oai-epc' : {'eth': 'eth0', 'gummei_tai_mnc':'95','DEFAULT_DNS_SEC_IPV4_ADDRESS': '192.168.12.100', 'DEFAULT_DNS_IPV4_ADDRESS':'192.168.12.100'},
    'oai-enb' : { 'eth': 'eth1', 'rrh_active': 'no', 'rrh_if_name': 'eth0', 'downlink_frequency': '2680000000L', 'uplink_frequency_offset': '-120000000', 'eutra_band': '7', 'remote_monitoring': 'no' },
    'oai-rrh' : { 'fronthaul_if': 'eth0'},
    'oai-mme' : { 'eth': 'eth0', 'gummei_tai_mcc': '208', 'gummei_tai_mnc':'95'},
    'oai-spgw' : { 'sgw-eth': 'eth0', 'pgw-eth':'eth0','DEFAULT_DNS_SEC_IPV4_ADDRESS': '192.168.12.100', 'DEFAULT_DNS_IPV4_ADDRESS':'192.168.12.100'}
}

"""
Service relationship template
"""
service_relation = [{'service_p': 'mysql',   'service_r': 'oai-hss'},
                    {'service_p': 'oai-hss', 'service_r': 'oai-epc'},
                    {'service_p': 'oai-epc', 'service_r': 'oai-enb'},
                    {'service_p': 'oai-rrh', 'service_r': 'oai-enb'}, 
                    {'service_p': 'oai-mme', 'service_r': 'oai-enb'},
                    {'service_p': 'oai-spgw', 'service_r': 'oai-mme'}
                ]

"""
machine specification template in terms of num cpu-cpres, memory, rootfs, architecture
"""
machine_spec = [{},{}]
