#!/usr/bin/env python3
"""
 * Copyright 2016-2019 Eurecom and Mosaic5G Platforms Authors
 * Licensed to the Mosaic5G under one or more contributor license
 * agreements. See the NOTICE file distributed with this
 * work for additional information regarding copyright ownership.
 * The Mosaic5G licenses this file to You under the
 * Apache License, Version 2.0  (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *-------------------------------------------------------------------------------
 * For more information about the Mosaic5G:
 *      contact@mosaic5g.io
 * \file jox.py
 * \brief description:
 * \authors:
 * \company: Eurecom
 * \email:contact@mosaic5g.io

__author__ = 'Eurecom'
__date__ = "11-January-2019"
__version__ = '1.0'
__version_date__ = "01-March-2019"
__copyright__ = 'Copyright 2016-2019, Eurecom'
__license__ = 'Apache License, Version 2.0'
__maintainer__ = 'Osama Arouk, Navid Nikaein, Kostas Kastalis, and Rohan Kharade'
__email__ = 'contact@mosaic5g.io'
__status__ = 'Development'
__description__ = "Plugin to interact with FlexRAN (Flexible and Programmable Platform for SD-RAN) controller"
"""
import pika
import os, time
import json
import logging
import requests
import datetime
from threading import Thread
from termcolor import colored
from src.common.config import gv
from src.core.ro.plugins import es
import pika.exceptions as pika_exceptions
import argparse

dir_path = os.path.dirname(os.path.realpath(__file__))
dir_parent_path = os.path.dirname(os.path.abspath(__file__ + "/../"))
dir_JOX_path = os.path.dirname(os.path.abspath(__file__ + "/../../../"))

class FlexRAN_plugin(object):
    def __init__(self, flex_log_level=None,):
        ## Loading global variables ##
        self.dir_config = dir_JOX_path + '/common/config/'
        self.logger = logging.getLogger("jox-plugin.flexran")
        self.jox_config = ""
        self.gv = gv

        if flex_log_level:
            if flex_log_level == 'debug':
                self.logger.setLevel(logging.DEBUG)
            elif flex_log_level == 'info':
                self.logger.setLevel(logging.INFO)
            elif flex_log_level == 'warn':
                self.logger.setLevel(logging.WARNING)
            elif flex_log_level == 'error':
                self.logger.setLevel(logging.ERROR)
            elif flex_log_level == 'critic':
                self.logger.setLeverbmq_server_ipl(logging.CRITICAL)
            else:
                self.logger.setLevel(logging.INFO)
        try:
            with open(''.join([self.dir_config, gv.CONFIG_FILE])) as data_file:
                data = json.load(data_file)
                data_file.close()
            self.jox_config = data
        except IOError as ex:
            message = "Could not load JOX Configuration file.I/O error({0}): {1}".format(ex.errno, ex.strerror)
            self.logger.error(message)
        except ValueError as error:
            message = "invalid json"
            self.logger.error(message)
        except Exception as ex:
            message = "Error while trying to load JOX configuration"
            self.logger.error(message)
        else:
            message = "JOX Configuration file Loaded"
            self.logger.info(message)
            self.logger.debug(message)

        # Elasticsearch configuration
        self.gv.ELASTICSEARCH_HOST = self.jox_config['elasticsearch-config']["elasticsearch-host"]
        self.gv.ELASTICSEARCH_PORT = self.jox_config['elasticsearch-config']["elasticsearch-port"]
        self.gv.ELASTICSEARCH_LOG_LEVEL = self.jox_config['elasticsearch-config']["elasticsearch-log-level"]
        # FlexRAN and RBMQ configuration
        self.gv.FLEXRAN_HOST = self.jox_config["flexran-config"]["host"]
        self.gv.FLEXRAN_PORT = self.jox_config["flexran-config"]["port"]
        self.gv.RBMQ_QUEUE_FlexRAN = self.jox_config["flexran-plugin-config"]["rabbit-mq-queue"]
        self.gv.FLEXRAN_PLUGIN_STATUS = self.jox_config["flexran-plugin-config"]["plugin-status"]
        self.gv.FLEXRAN_TIMEOUT_REQUEST = self.jox_config["flexran-plugin-config"]['timeout-request']
        self.gv.FLEXRAN_ES_INDEX_NAME = self.jox_config["flexran-plugin-config"]['es-index-name']
        self.gv.RBMQ_SERVER_IP = self.jox_config['rabbit-mq-config']["rabbit-mq-server-ip"]
        self.gv.RBMQ_SERVER_PORT = self.jox_config['rabbit-mq-config']["rabbit-mq-server-port"]
        self.jesearch = None
        self.credentials=None
        self.parameters=None
        self.connection=None
        self.channel=None
        self.es_flexran_index = self.gv.FLEXRAN_ES_INDEX_NAME
        self.rbmq_server_ip = self.gv.RBMQ_SERVER_IP
        self.rbmq_server_port = self.gv.RBMQ_SERVER_PORT
        self.rbmq_queue_name = self.gv.RBMQ_QUEUE_FlexRAN
        self.flexran_host= self.gv.FLEXRAN_HOST
        self.flexran_port= self.gv.FLEXRAN_PORT
        self.flexran_plugin_status=self.gv.FLEXRAN_PLUGIN_STATUS
        self.flexran_endpoint = ''.join(['http://', str(self.flexran_host), ':', str(self.flexran_port), '/'])

    def build(self):
        try:
            self.logger.info(" FlexRAN default endpoint is {}".format(self.flexran_endpoint))
            if self.gv.ELASTICSEARCH_ENABLE:
                self.jesearch = es.JESearch(self.gv.ELASTICSEARCH_HOST, self.gv.ELASTICSEARCH_PORT,
                                            self.gv.ELASTICSEARCH_LOG_LEVEL)
            self.parameters = pika.ConnectionParameters(self.rbmq_server_ip, self.rbmq_server_port)
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(self.rbmq_queue_name)
            self.channel.basic_qos(prefetch_count=1)

            # Create es index to maintain statistics for flexRAN plugin viz. enb_stats, ue_stats
            if self.jesearch.ping():
                message = "Deleting the index {} from elasticsearch if alredy exist".format((self.es_flexran_index))
                self.logger.info(message)
                self.logger.debug(message)
                self.jesearch.del_index_from_es((self.es_flexran_index))  # Adding slice data to elasticsearch
                message = "Saving the index {} to elasticsearch".format((self.es_flexran_index))
                self.logger.info(message)
                self.logger.debug(message)
                date = (datetime.datetime.now()).isoformat()
                index_data = {"date": date,
                            "enb_stats": [],
                            "ue_stats": [] }
                self.jesearch.set_json_to_es(self.es_flexran_index, index_data)
                self.logger.info("Elasticsearch: connection Success")
            else:
                message = " Elasticsearch is disabled !! Enable elasticsearch to get FlexRAN notifications"
                self.logger.info(message)
                self.gv.FLEXRAN_ES_INDEX_STATUS="disabled"

        except pika_exceptions.ConnectionClosed or \
               pika_exceptions.ChannelAlreadyClosing or \
               pika_exceptions.ChannelClosed or \
               pika_exceptions.ChannelError:
            self.connection.close()

    def start_consuming(self):
        while True:
            try:
                self.channel.basic_consume(self.on_request, queue=self.rbmq_queue_name)
                print(colored('[*] FlexRAN plugin message thread -- > Waiting for messages. To exit press CTRL+C', 'yellow'))
                self.channel.start_consuming()
            except pika_exceptions.ConnectionClosed or \
                   pika_exceptions.ChannelAlreadyClosing or \
                   pika_exceptions.ChannelClosed or \
                   pika_exceptions.ChannelError:
                self.connection.close()

    def start_notifications(self):
        print(colored('[*] FlexRAN plugin notifications thread -- > Waiting for messages. To exit press CTRL+C', 'blue'))
        while True:
            try:
                #self.update_flexRAN_endpoint()
                enb_agent_id, enb_data = self.get_eNB_list()
                # check this if changed i.e. if this is new eNB
                container_name = "enb_agent_"+str(enb_agent_id)
                message = "Notify - New eNB with id {} and info {}".format(enb_agent_id, enb_data)
                self.logger.info(message)
                if self.gv.FLEXRAN_ES_INDEX_STATUS == "disabled":
                    message = " Elasticsearch is disabled !! No more notifications are maintained"
                    self.logger.info(message)
                else:
                    self.update_flexran_plugin_index(self.es_flexran_index, "enb_stats", container_name, enb_data)
                time.sleep(3600)
            except pika_exceptions.ConnectionClosed or \
                   pika_exceptions.ChannelAlreadyClosing or \
                   pika_exceptions.ChannelClosed or \
                   pika_exceptions.ChannelError:
                self.connection.close()

    def on_request(self, ch, method, props, body):
        enquiry = body.decode(self.gv.ENCODING_TYPE)
        enquiry = json.loads(enquiry)
        param = enquiry["parameters"]
        elapsed_time_on_request = datetime.datetime.now() - datetime.datetime.strptime(enquiry["datetime"],
                                                                                       '%Y-%m-%d %H:%M:%S.%f')
        if elapsed_time_on_request.total_seconds() < self.gv.FLEXRAN_TIMEOUT_REQUEST:
            send_reply = True
            if "get_ran_record" in enquiry["plugin_message"]:
                self.get_ran_record(param)
            if "get_ran_stats" in enquiry["plugin_message"]:
                self.get_ran_stats(param)
            if "get_ue_stats" in enquiry["plugin_message"]:
                self.get_ue_stats(param)
            if "create_slice" in enquiry["plugin_message"]:
                self.prepare_slice(param)
            if "remove_slice" in enquiry["plugin_message"]:
                self.remove_slice(param)
            if "add_ue_to_slice" in enquiry["plugin_message"]:
                self.add_ues_to_slice(param)
            if "remove_ue_from_slice" in enquiry["plugin_message"]:
                self.remove_ues_from_slice(param)
            if "get_num_slice" in enquiry["plugin_message"]:
                self.get_num_slices(param)
            if "set_num_slice" in enquiry["plugin_message"]:
                self.set_num_slices(param)
            if "set_slice_rb" in enquiry["plugin_message"]:
                self.set_slice_rb(param)
            if "get_slice_rb" in enquiry["plugin_message"]:
                self.get_slice_rb(param)
            if "set_slice_max_mcs" in enquiry["plugin_message"]:
                self.set_slice_max_mcs(param)
            if "get_slice_max_mcs" in enquiry["plugin_message"]:
                self.get_slice_max_mcs(param)
            if "update_flexRAN_endpoint" in enquiry["plugin_message"]:
                raise NotImplementedError()
                # self.update_flexRAN_endpoint()
            if "update_flexRAN_endpoint" in enquiry["plugin_message"]:
                # self.get_status_flexRAN_endpoint()
                raise NotImplementedError

    ##### Consume callbacks ######
    def get_ran_record(self):
        try:
            response = requests.get(self.flexran_endpoint+"record/:id")
            json_data = json.loads(response.text)
            response.close()
            requests.session().close()
            return json_data
        except Exception as ex:
            print(ex)
    """
    *
    *@param 
    """
    def get_ran_stats(self):
        try:
            response = requests.get(self.flexran_endpoint+"stats/")
            print(response)
        except Exception as ex:
            print(ex)

    def get_ue_stats(self,id):
        try:
            response = requests.get(self.flexran_endpoint+"stats/ue"+id)
            print(response)
        except Exception as ex:
            print(ex)

    def prepare_slice(self,enb_id, slice_id):
        try:
            response = requests.get(self.flexran_endpoint+"slice/enb/"+enb_id+"slice"+slice_id)
            print(response)
        except Exception as ex:
            print(ex)

    def create_slice(self,enb_id, slice_id):
        try:
            response = requests.get(self.flexran_endpoint+"slice/enb/"+enb_id+"slice"+slice_id)
            print(response)
        except Exception as ex:
            print(ex)

        """!@brief Delet a slice and its associated policy . 
        @param enb_id: eNB ID 
        @param nssi_id: slice id 
        @param policy_data: content of the policy file of type str
        @return: The status of the request as str
        """
    def remove_slice(self,enb_id, nssi_id, policy=""):
        try:
            if policy == '':
                response = requests.get(self.flexran_endpoint+'/enb/'+str(enb_id)+'/slice/'+str(nssi_id))
            else:
                requests.pay
            print(response)
        except Exception as ex:
            print(ex)

    def add_ues_to_slice(self, param):
        raise NotImplementedError()

    def remove_ues_from_slice(self, param):
        raise NotImplementedError()

    def get_num_slices(self, param):
        raise NotImplementedError()

    def set_num_slices(self, param):
        raise NotImplementedError()

    def set_slice_rb(self, param):
        raise NotImplementedError()

    def get_slice_rb(self, param):
        raise NotImplementedError()

    def set_slice_max_mcs(self, param):
        raise NotImplementedError()

    def get_slice_max_mcs(self, param):
        raise NotImplementedError()
    
    def update_flexRAN_endpoint(self, param):
        raise NotImplementedError()

    def get_status_flexRAN_endpoint(self, param):
        raise NotImplementedError()

    ###### Notification callbacks ######
    def get_eNB_list(self):
        try:
            pass
            # response = requests.get(self.flexran_endpoint+"stats/")
            response =  {"eNB_config":[{"agent_id": 0, "eNBId": 234881024,"eNB": {"header": {"version": 0,"type": 8,"xid": 0}}}]}
            agent_id = response["eNB_config"][0]['agent_id']
            time.sleep(1)
            agent_info = {'eNBId' : response["eNB_config"][0]['eNBId'],'ipv4_address' : 'None' }
            return agent_id, agent_info
        except Exception as ex:
            print(ex)

    # method to update es index with container unlike single keys
    def update_flexran_plugin_index(self, index_page, container_type, container_name, container_data):
        slice_data = self.jesearch.get_json_from_es(index_page, container_type)
        container_data.items()
        leaf_keys = list(container_data.keys())
        leaf_values = list(container_data.values())
        if slice_data[0]:
            slice_data = slice_data[1]
            for machines in range(len(slice_data)):  # Update the container
                machines_list = slice_data[machines]
                machine = list(machines_list.keys())
                for num in range(len(machine)):
                    if machine[num] == container_name:
                        for number in range(len(container_data)):
                            leaf_key = leaf_keys[number - 1]
                            leaf_value = leaf_values[number - 1]
                            slice_data[machines][container_name][0][leaf_key] = leaf_value
            if bool(slice_data) == False:
                slice_data = [{container_name : [container_data]}]
            self.jesearch.update_index_with_content(index_page, container_type, slice_data)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process commandline arguments and override configurations in jox_config.json')
    parser.add_argument('--log', metavar='[level]', action='store', type=str,
                        required=False, default='debug',
                        help='set the log level: debug, info (default), warning, error, critical')

    args = parser.parse_args()
    fs = FlexRAN_plugin(args.log)
    fs.build()
    t1 = Thread(target=fs.start_consuming).start()
    t2 = Thread(target=fs.start_notifications).start()






