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
 """
__author__ = 'Eurecom'
__date__ = "11-January-2019"
__version__ = '1.0'
__version_date__ = "01-March-2019"
__copyright__ = 'Copyright 2016-2019, Eurecom'
__license__ = 'Apache License, Version 2.0'
__maintainer__ = 'Osama Arouk, Navid Nikaein, Kostas Kastalis, and Rohan Kharade'
__email__ = 'contact@mosaic5g.io'
__status__ = 'Development'
__description__ = "The descripton goes here"


import os, sys
dir_path = os.path.dirname(os.path.realpath(__file__))
dir_parent_path = os.path.dirname(os.path.abspath(__file__ + "/../"))
dir_JOX_path = os.path.dirname(os.path.abspath(__file__ + "/"))

sys.path.append(dir_parent_path)
sys.path.append(dir_path)

import atexit
from os.path import expanduser
from termcolor import colored
import asyncio
from src.core.ro.resource_controller import ResourcesController
import traceback
import logging
import jsonschema
from src.core.nso.nsi import nsi_controller
from src.core.nso.nssi import nssi_controller
from src.core.ro.plugins import es

from src.common.config import gv
import time
import yaml, json
import pika
import pika.exceptions as pika_exceptions
from juju import loop
from src.core.ro.monitor import get_juju_status as jmonitor_get_juju_status
import tarfile, io

__author__ = "Eurecom"
jox_version = '1.0'
jox_version_date = '2019-02-01'

class NFVO_JOX(object):
	def __init__(self, loop):
		# TODO
		atexit.register(self.goodbye)# register a message to print out when exit
		self.loop = loop
		
		
		self.dir_slice = dir_path + '/common/template_slice/' # directory where the slice template should exist
		self.dir_subslice = dir_path + '/common/template_slice/'
		
		
		self.dir_config = dir_path + '/common/config/' # directory for the configurations needed by different modules
		self.dir_home = expanduser("~")
		
		self.start_time = time.time()  # start_time and end_time to calculate the time needed to start jox
		self.end_time = 0
		self.jox_config = "" # jox configuration, it exists in the file jox_config.json  in com/config
		self.jesearch = None # to interact with Elasticsearch
		self.gv = gv # the global variables of JOX
		# related to log
		self.logger = logging.getLogger("jox")
		self.file_handler = None
		self.console = None
		self.formatter = None
		self.log_format = None
		
		self.resourceController = None
		self.slices_controller = None
		self.subslices_controller = None
		########## STEP 1.1: Load JOX Configuration file ##########
		try:
			with open(''.join([self.dir_config, gv.CONFIG_FILE])) as data_file:
				data = json.load(data_file)
				data_file.close()
			
			self.jox_config = data
		except IOError as ex:
			message = "Could not load JOX Configuration file.I/O error({0}): {1}".format(ex.errno, ex.strerror)
			self.logger.error(message)
			self.cleanup_and_exit(str(ex))
		except Exception as ex:
			message = "Error while trying to load JOX configuration"
			self.logger.error(message)
			self.cleanup_and_exit(str(ex))
		else:
			message = "JOX Configuration file Loaded"
			self.logger.info(message)
			self.logger.debug(message)
		
		########## STEP 2.1: Load global variables ##########
		try:
			# rabbit-MQ config
			self.gv.RBMQ_SERVER_IP = self.jox_config['rabbit-mq-config']["rabbit-mq-server-ip"]
			self.gv.RBMQ_SERVER_PORT = self.jox_config['rabbit-mq-config']["rabbit-mq-server-port"]
			self.gv.RBMQ_QUEUE = self.jox_config['rabbit-mq-config']["rabbit-mq-queue"]
			# Elasticsearch configuration
			self.gv.ELASTICSEARCH_HOSt                  = self.jox_config['elasticsearch-config']["elasticsearch-host"]
			self.gv.ELASTICSEARCH_PORT                  = self.jox_config['elasticsearch-config']["elasticsearch-port"]
			self.gv.ELASTICSEARCH_LOG_LEVEL = self.jox_config['elasticsearch-config']["elasticsearch-log-level"]
			self.gv.ELASTICSEARCH_RETRY_ON_CONFLICT = self.jox_config['elasticsearch-config']["elasticsearch-retry-on-conflict"]
			# log config
			self.gv.LOGFILE                             = self.jox_config['log-config']["log-file"]
			self.gv.LOG_LEVEL                           = self.jox_config['log-config']["log-level"]
			# juju config
			self.gv.JUJU_MAX_RETRY_CONNECTION_MODEL_AVAILABLE= self.jox_config['juju-config']["connect-model-available-max-retry"]
			self.gv.JUJU_INTERVAL_CONNECTION_MODEL_AVAILABLE= self.jox_config['juju-config']["connect-model-available-interval"]
			self.gv.JUJU_MAX_RETRY_CONNECTION_MODEL_ACCESSIBLE= self.jox_config['juju-config']["connect-model-accessible-max-retry"]
			self.gv.JUJU_INTERVAL_CONNECTION_MODEL_ACCESSIBLE = self.jox_config['juju-config']["connect-model-accessible-interval"]
			
			# ssh config
			self.gv.SSH_KEY_DIRECTORY = self.jox_config['ssh-config']["ssh-key-directory"]
			self.gv.SSH_KEY_NAME = self.jox_config['ssh-config']["ssh-key-name"]
			self.gv.SSH_USER = self.jox_config['ssh-config']["ssh-user"]
			self.gv.SSH_PASSWORD = self.jox_config['ssh-config']["ssh-password"]
			
			self.gv.STORE_DIR = self.jox_config['store-config']["store-directrory"]
			self.gv.ENCODING_TYPE = self.jox_config['encoding-type']
			
			self.gv.STATS_TIMER                         = self.jox_config["stats-timer"]
			

		except jsonschema.ValidationError as ex:
			self.logger.error("Error happened while validating the jox config: {}".format(ex.message))
			self.cleanup_and_exit(str(ex))
		except Exception as ex:
			self.logger.error("Error happened while loading the global variable jox: {}".format(ex))
			self.cleanup_and_exit(str(ex))
		else:
			message = "Global variables are successfully loaded"
			self.logger.info(message)
			
		##########  STEP 2.2: Logging Configuration ##########
		if gv.LOG_LEVEL == 'debug':
			self.logger.setLevel(logging.DEBUG)
		elif gv.LOG_LEVEL == 'info':
			self.logger.setLevel(logging.INFO)
		elif gv.LOG_LEVEL == 'warn':
			self.logger.setLevel(logging.WARNING)
		elif gv.LOG_LEVEL == 'error':
			self.logger.setLevel(logging.ERROR)
		elif gv.LOG_LEVEL == 'critic':
			self.logger.setLevel(logging.CRITICAL)
		else:
			self.logger.setLevel(logging.INFO)
		# create file handler which logs even debug messages
		self.file_handler = logging.FileHandler(self.gv.LOGFILE)
		self.file_handler.setLevel(logging.DEBUG)
		
		# create console handler with a higher log level
		self.console = logging.StreamHandler()
		self.console.setLevel(logging.DEBUG)
		
		# create formatter and add it to the handlers
		self.log_format = "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)s %(message)s"
		self.formatter = logging.Formatter(self.log_format, datefmt='%Y-%m-%dT%H:%M:%S')
		# self.formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
		self.file_handler.setFormatter(self.formatter)
		self.console.setFormatter(self.formatter)
		
		# add the handlers to the logger
		self.logger.addHandler(self.file_handler)
		self.logger.addHandler(self.console)


		########## STEP 3.1: Configure elastcisearch ##########
		self.logger.info("Configure elastcisearch if enabled")
		if self.gv.ELASTICSEARCH_ENABLE:
			self.jesearch = es.JESearch(self.gv.ELASTICSEARCH_HOSt, self.gv.ELASTICSEARCH_PORT, self.gv.ELASTICSEARCH_LOG_LEVEL)
			
			if not self.jesearch.ping():
				message = "Elasticsearch is not working while it is enabled. Either disable elasticsearch or run it"
				self.logger.error(message)
				self.cleanup_and_exit(str(0))
			else:
				message = "elasticsearch is now running"
				self.logger.info(message)

				
		
		######### STEP 4: Load JOX Configuration to ES ########
		if self.gv.ELASTICSEARCH_ENABLE:
			self.logger.info("Save JOX configuration to elasticsearch")
			try:
				self.logger.info("Delete the index of jox config from elasticsearch if exist")
				self.jesearch.del_index_from_es(self.gv.JOX_CONFIG_KEY)
				
				self.logger.info("Sending JOX configuration file to elasticsearch")
				set_indx_es = self.jesearch.set_json_to_es(self.gv.JOX_CONFIG_KEY, self.jox_config)
				if set_indx_es:
					message = "The data of the index {} is addedd to elasticsearch".format(self.gv.JOX_CONFIG_KEY)
					self.logger.info(message)
				else:
					message = "The index of jox config can not be saved to elasticsearch"
					self.logger.info(message)
			except Exception as ex:
				self.logger.error((str(ex)))
				self.logger.error(traceback.format_exc())
		
		######### STEP 5: Create Resource Controller ########
		self.logger.info("Create resource Controller")
		try:
			self.resourceController = ResourcesController(self.gv)
			self.resourceController.build(self.jox_config, self.jesearch)
			for pop_type in self.jox_config['vim-pop']:
				for pop_name in self.jox_config['vim-pop'][pop_type]:
					self.logger.info(
						"registering the POP {} of type {} as specified in jox_config".format(pop_name, pop_type))
					self.register_pop(pop_name, pop_type)
		except Exception as ex:
			self.logger.error(str(ex))
			self.logger.error(traceback.format_exc())
			self.cleanup_and_exit(str(ex))
		else:
			self.logger.info("Clouds Controller is successfully loaded!")
		
		######### STEP 6: Add clouds to CloudsController #########
		try:
			clouds_config = self.jox_config["clouds-list"]
			for config in clouds_config:
				self.add_cloud(config)
		except Exception as ex:
			self.logger.error(str(ex))
			self.logger.error(traceback.format_exc())
			self.cleanup_and_exit(ex)
		else:
			self.logger.info("All clouds were successfully added!")
		
		######### STEP 7: Create Slices and Subslices Controller #########
		try:
			self.logger.info("Creating slice controller")
			self.slices_controller = nsi_controller.NetworkSliceController(self.gv)
			self.slices_controller.build(self.resourceController, self.jox_config)
			
			self.logger.info("Creating sub-slice controller")
			self.subslices_controller = nssi_controller.SubSlicesController(self.gv)
			self.subslices_controller.build(self.resourceController, self.jox_config)
		except Exception as ex:
			self.logger.error(str(ex))
			self.logger.error(traceback.format_exc())
			self.cleanup_and_exit(str(ex))
		else:
			self.logger.info("Slices Controller was successfully loaded!")
		
		########## STEP 9: Start WebAPI (Flask)##########
		try:
			self.end_time = time.time()
			self.logger.info("JOX loading time: %s ", self.end_time - self.start_time)
		
		except RuntimeError as ex:
			self.logger.error(ex)
			self.cleanup_and_exit(str(ex))
		except Exception as ex:
			self.logger.error(ex)
			self.cleanup_and_exit(str(ex))
		else:
			message = "JOX Web API loaded!"
			self.logger.info(message)
	def register_pop(self, pop_name, pop_type):
		try:
			self.resourceController.pop_register(pop_name, pop_type)
		except Exception as ex:
			self.logger.debug("The following error raised while registering the pop {} of type {}: \n {}".format(pop_name, pop_type, ex))
		else:
			self.logger.debug("The pop {} of type {} is successfully regiestered".format(pop_name, pop_type))
	def get_list_pop(self):
		return self.resourceController.get_list_all_pop()
	def add_cloud(self, cloud_config):
		try:
			self.resourceController.add_cloud(cloud_config)
		except Exception as ex:
			message = "The following error raised while trying to add the following cloud. " \
			          "\n cloud-configuration: {} " \
			          "\n Error: {}".format(cloud_config, ex)
			self.logger.debug(message)
		else:
			self.logger.debug("The following cloud is successfully  added".format(cloud_config))
	
	
	def add_slice(self, slice_name_yml, nsi_dir=None, nssi_dir=None):
		self.logger.info("Adding the slice {}".format(slice_name_yml))
		nsi_dir = self.dir_slice if nsi_dir == None else nsi_dir
		nssi_dir = self.dir_subslice if nssi_dir == None else nssi_dir

		nsi_deploy = self.slices_controller.add_network_slice(slice_name_yml, self.subslices_controller, nsi_dir,
		                                                      nssi_dir)
		return nsi_deploy
	def delete_slice(self, slice_name):
		res = self.slices_controller.remove_network_slice(slice_name, self.subslices_controller)
		return res
	def add_sub_slice(self):
		raise NotImplementedError
	
	def get_slice_context(self, slice_name=None, sub_slice_name=None, entity=None, slice_info=True):
		if slice_name is None:
			nssi_data = self.slices_controller.get_slices_data()
			return [True, nssi_data]
		else:
			
			nssi_data = self.slices_controller.get_slice_data(slice_name)
			if nssi_data[0]:
				nssi_data = nssi_data[1]
				if sub_slice_name is not None:
					# get the context of the sub slice
					for key in nssi_data.keys():
						if nssi_data[key] == slice_name:
							list_subslices = nssi_data["sub_slices"]
							if sub_slice_name in list_subslices:
								subslice_data = self.get_subslice_context(sub_slice_name)
								if entity is not None:
									try:
										return [True, subslice_data[entity]]
									except:
										message = "The key {} does not exist in the subslice {} attached to the slice {}".format(entity, sub_slice_name, slice_name)
										return [False, message]
								else:
									return [True, subslice_data]
					message = "The subslice {} is not attached to the slice {}".format(sub_slice_name, slice_name)
					return [False, message]
				else:
					if slice_info:
						return [True, nssi_data]
					else:
						list_subslices = nssi_data["sub_slices"]
						nssi_data = list()
						for nsi_item in list_subslices:
							subslice_data = self.get_subslice_context(nsi_item)
							nssi_data.append(subslice_data)
						return [True, nssi_data]
			else:
				return [False, nssi_data[1]]
				
	def get_subslices_context(self):
		list_subslice_context = list()
		nsi_data = self.slices_controller.get_slices_data()
		for nsi_item in nsi_data:
			slice_name  = nsi_data[nsi_item]["slice_name"]
			list_subslices = nsi_data[nsi_item]["sub_slices"]
			subslice_data = {}
			subslice_data[slice_name] = {}
			for item_nssi in list_subslices:
				nssi_context = self.get_subslice_context(item_nssi)
				subslice_data[slice_name][item_nssi] = nssi_context
			list_subslice_context.append(subslice_data)
		return list_subslice_context
		
	def get_subslice_context(self, sub_slice=None):
		nssi_data = self.subslices_controller.get_subslice_runtime_data(sub_slice)
		return nssi_data[1]
	def get_machines_status(self, pop_name, pop_type):
		if pop_type == self.gv.LXC:
			for pop_lxc in self.resourceController.pop_lxc_list:
				if pop_lxc.driver_name == pop_name:
					machine_status = pop_lxc.get_machines_status()
					return machine_status
		elif pop_type == self.gv.KVM:
			for pop_kvm in self.resourceController.pop_kvm_list:
				if pop_kvm.driver_name == pop_name:
					machine_status = pop_kvm.get_machines_status()
					return machine_status
		else:
			return "Error; it is not supported type"
	def goodbye(self):
		print("\n You are now leaving JOX ...")
	
	
	def cleanup_and_exit(self, ex=None):
		if ex:
			sys.exit(str(ex))
		else:
			sys.exit(0)

class server_RBMQ(object):
	def __init__(self):
		loop = asyncio.get_event_loop()
		self.nfvo_jox = NFVO_JOX(loop)
		
		self.host=self.nfvo_jox.gv.RBMQ_SERVER_IP
		self.port=self.nfvo_jox.gv.RBMQ_SERVER_PORT
		self.connection = None
		self.channel = None
		self.queue_name = self.nfvo_jox.gv.RBMQ_QUEUE
		self.logger = logging.getLogger("server_RBMQ")
	def run(self):
		while True:
			try:
				self.connection = pika.BlockingConnection(pika.ConnectionParameters(
					host=self.host, port=self.port))
				self.channel = self.connection.channel()
				self.channel.queue_declare(queue=self.queue_name)
				
				self.channel.basic_qos(prefetch_count=1)
				self.channel.basic_consume(self.on_request, queue=self.queue_name)
				
				print(colored(' [*] Waiting for messages. To exit press CTRL+C', 'green'))
				self.channel.start_consuming()
			except pika_exceptions.ConnectionClosed or \
			       pika_exceptions.ChannelAlreadyClosing or \
			       pika_exceptions.ChannelClosed or \
			       pika_exceptions.ChannelError:
				
				self.connection.close()
				time.sleep(0.5)
			except KeyboardInterrupt:
				exit()
	def on_request(self, ch, method, props, body):
		enquiry = body.decode(self.nfvo_jox.gv.ENCODING_TYPE)
		enquiry = json.loads(enquiry)
		if "/jox/" in enquiry["request-uri"]:
			jox_config = self.nfvo_jox.gv.JOX_CONFIG_KEY
			res = self.nfvo_jox.jesearch.get_source_index(jox_config)
			res = {
				"ACK": True,
				"data": res[1],
				"status_code": self.nfvo_jox.gv.HTTP_200_OK
			}
			response = res
		elif (enquiry["request-uri"] == '/list') \
				or (enquiry["request-uri"] == '/ls') \
				or (enquiry["request-uri"] == '/show/<string:nsi_name>'):
			# request_type = enquiry["request-type"]
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			template_directory = parameters["template_directory"]
			full_path = self.check_existence_path(template_directory, nsi_name)
			
			if full_path[0]:
				full_path = full_path[1]
				if os.path.isdir(full_path):
					if not full_path.startswith('/'):
						full_path = ''.join(['/', full_path])
					if not full_path.endswith('/'):
						full_path = ''.join([full_path, '/'])
					message = "get list of all the nsi in the directory {}".format(full_path)
					self.logger.info(message)
					self.logger.debug(message)
					list_files = list()
					for f in os.listdir(full_path):
						# if os.path.isfile(''.join([full_path, f])) and \
						# 		(f.endswith('.yaml') or f.endswith('.yml') or f.endswith('.json')):
						# 	list_files.append(f)
						list_files.append(f)
					res = list_files
					response = {
						"ACK": True,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_200_OK,
						"full_path": full_path
					}
				elif os.path.isfile(full_path):
					message = "Getting template of the nsi {}".format(full_path)
					self.logger.info(message)
					self.logger.debug(message)
					
					data_nsi = self.read_yaml_json(full_path)
					if data_nsi[0]:
						res = data_nsi[1]
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK,
							"full_path": full_path
						}
					else:
						res = data_nsi[1]
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
						}
				else:
					res = "The following path is not valid or the file does not exist: {}".format(full_path[1])
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				message = full_path[1]
				response = {
					"ACK": False,
					"data": message,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif (enquiry["request-uri"] == "/nsi/all") or (enquiry["request-uri"] == "/nsi"):
			request_type = enquiry["request-type"]
			if request_type == "get":
				res = self.nfvo_jox.get_slice_context()
				if res[0]:
					status_code = self.nfvo_jox.gv.HTTP_200_OK
				else:
					status_code = self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				response = {
					"ACK": res[0],
					"data": res[1],
					"status_code": status_code
				}
			elif request_type == "delete":
				res = "The method {} for the request {} is not supported".format(request_type, enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = "The method {} for the request {} is not supported".format(request_type, enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
				}
		elif enquiry["request-uri"] == "/nsi/<string:nsi_name>":
			parameters = enquiry["parameters"]
			
			package_name = parameters["package_name"]
			nsi_name = parameters["nsi_name"]
			template_directory = parameters["template_directory"]
			nsi_directory_temp = parameters["nsi_directory"]
			nssi_directory_temp = parameters["nssi_directory"]
			request_type = enquiry["request-type"]
			if request_type == "get":
				if nsi_name is None:
					res = "Please specify the name of the slice"
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
					}
				else:
					res = self.nfvo_jox.get_slice_context(nsi_name)
					
					if res[0]:
						res = res[1]
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = res[1]
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
						}
			elif (request_type == "post"):
				package_path = ''.join([self.nfvo_jox.gv.STORE_DIR, package_name, '/'])
				nsi_found = False
				nssi_found = False
				if os.path.exists(package_path):
					nsi_dir = ''.join([package_path, 'nsi', '/'])
					if os.path.exists(nsi_dir):
						for f in os.listdir(nsi_dir):
							if os.path.isfile(''.join([nsi_dir, f])) and \
									(f.endswith('.yaml') or f.endswith('.yml')):
								nsi_found = True
								nsi_name = f
					nssi_dir = ''.join([package_path, 'nssi', '/'])
					if os.path.exists(nssi_dir):
						for f in os.listdir(nssi_dir):
							if os.path.isfile(''.join([nssi_dir, f])) and \
									(f.endswith('.yaml') or f.endswith('.yml')):
								nssi_found = True
					if nsi_found and nssi_found:
						nsi_deploy = self.nfvo_jox.add_slice(nsi_name, nsi_dir, nssi_dir)
						if nsi_deploy[0]:
							message = "Ceating/updating the slice {}".format(nsi_name)
							response = {
								"ACK": True,
								"data": message,
								"status_code": self.nfvo_jox.gv.HTTP_200_OK
							}
						else:
							res = nsi_deploy[1]
							response = {
								"ACK": False,
								"data": res,
								"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
							}
					
				else:
					message = "package {} does not exists in {}".format(package_name, self.nfvo_jox.gv.STORE_DIR)
					response = {
						"ACK": False,
						"data": message,
						"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
					}

			elif request_type == "delete":
				res = self.nfvo_jox.delete_slice(nsi_name)
				if res[0]:
					response = {
						"ACK": True,
						"data": res[1],
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					response = {
						"ACK": True,
						"data": res[1],
						"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
					}
					
			else:
				res = "The method {} for the request is not supported".format(request_type.upper(), enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
				}
		elif (enquiry["request-uri"] == "/onboard"):
			files = bytes(enquiry["parameters"]["package_onboard_data"])
			onboard_files = self.onboard_jox_package(files)
			if onboard_files[0]:
				tar_file = self.open_save_tar_gz(files)
				if tar_file[0]:
					response = {
						"ACK": True,
						"data": tar_file[1],
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					response = {
						"ACK": False,
						"data": tar_file[1],
						"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
					}
			else:
				response = {
					"ACK": False,
					"data": onboard_files[1],
					"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
				}
		elif (enquiry["request-uri"] == "/nssi/all") or (enquiry["request-uri"] == "/nssi"):
			res = self.nfvo_jox.get_subslices_context()
			response = {
				"ACK": True,
				"data": res,
				"status_code": self.nfvo_jox.gv.HTTP_200_OK
			}
		elif (enquiry["request-uri"] == "/nssi/<string:nsi_name>") or \
			(enquiry["request-uri"] == "/nssi/<string:nsi_name>/<string:nssi_name>/<string:nssi_key>"):
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			nssi_key = parameters["nssi_key"]
			res = self.nfvo_jox.get_slice_context(nsi_name, nssi_name, nssi_key, slice_info=False)
			if res[0]:
				response = {
					"ACK": True,
					"data": res[1],
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				response = {
					"ACK": False,
					"data": res[1],
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif (enquiry["request-uri"] == "/nssi/<string:nsi_name>/<string:nssi_name>"):
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			request_type = enquiry["request-type"]
			if request_type == "get":
				res = self.nfvo_jox.get_slice_context(nsi_name, nssi_name)
				if res[0]:
					response = {
						"ACK": True,
						"data": res[1],
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					response = {
						"ACK": False,
						"data": res[1],
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			elif request_type == "post":
				res = "The method {} of the request {} is not supported".format(request_type, enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
				}
			elif request_type == "delete":
				res = "The method {} of the request {} is not supported".format(request_type, enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
				}
			else:
				res = "The method {} of the request {} is not supported".format(request_type, enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
				}
		elif (enquiry["request-uri"] == "/es") \
				or (enquiry["request-uri"] == "/es/<string:es_index_page>") \
				or (enquiry["request-uri"] == "/es/<string:es_index_page>/<string:es_key>"):
			
			# request_url = enquiry["request-uri"]
			request_type = enquiry["request-type"]
			parameters = enquiry["parameters"]
			template_directory = parameters["template_directory"]
			es_index_page = parameters["es_index_page"]
			es_key = parameters["es_key"]
			if request_type == "get":
				if (es_index_page is None):
					res = self.nfvo_jox.jesearch.get_all_indices_from_es()
					if res[0]:
						response = {
							"ACK": True,
							"data": res[1],
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						response = {
							"ACK": False,
							"data": res[1],
							"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
						}
				else:
					if (es_index_page == "_all") or (es_index_page == "all") or (es_index_page == "*"):
						res = self.nfvo_jox.jesearch.get_all_indices_from_es()
						if res[0]:
							response = {
								"ACK": True,
								"data": res[1],
								"status_code": self.nfvo_jox.gv.HTTP_200_OK
							}
						else:
							response = {
								"ACK": False,
								"data": res[1],
								"status_code": self.nfvo_jox.gv.HTTP_420_METHOD_FAILURE
							}
					else:
						if es_key is None:
							message = "get the index-page {} ".format(es_index_page)
							self.logger.info(message)
							self.logger.debug(message)
							res = self.nfvo_jox.jesearch.get_source_index(es_index_page)
							
							
							if res[0]:
								res = res[1]
								response = {
									"ACK": True,
									"data": res,
									"status_code": self.nfvo_jox.gv.HTTP_200_OK
								}
							else:
								res = res[1]
								response = {
									"ACK": False,
									"data": res,
									"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
								}
								
							
						else:
							message = "get the key {} from the index-page {} ".format(es_key, es_index_page)
							self.logger.info(message)
							self.logger.debug(message)
							res = self.nfvo_jox.jesearch.get_json_from_es(es_index_page, es_key)
							if res[0]:
								res = res[1]
								response = {
									"ACK": True,
									"data": res,
									"status_code": self.nfvo_jox.gv.HTTP_200_OK
								}
							else:
								res = res[1]
								response = {
									"ACK": False,
									"data": res,
									"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
								}
			elif request_type == "post":
				full_path = self.check_existence_path(template_directory, es_index_page)
				if full_path[0]:
					full_path = full_path[1]
					file_content = self.read_yaml_json(full_path)
					file_content = file_content[1]
					es_index_page = es_index_page.split('.')
					es_index_page = (es_index_page[0]).lower()
					res = self.nfvo_jox.jesearch.set_json_to_es(es_index_page, file_content)
					if res:
						res = "The file {} is successfully saved to es".format(full_path)
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = "The file {} can not be saved to es".format(full_path)
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_424_FAILED_DEPENDENCY
						}
				else:
					res = full_path[1]
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			elif request_type == "delete":
				if (es_index_page is None) or (es_index_page == "_all") or (es_index_page == "all") or (es_index_page == "*"):
					res = self.nfvo_jox.jesearch.delete_all_indices_from_es()
					if res[0]:
						res = res[1]
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = res[1]
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_424_FAILED_DEPENDENCY
						}
				else:
					res = self.nfvo_jox.jesearch.del_index_from_es(es_index_page)
					if res[0]:
						res = res[1]
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = res[1]
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_424_FAILED_DEPENDENCY
						}
			else:
				res = "The method {} for the request {} is not supported".format(request_type, enquiry["request-uri"])
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_400_BAD_REQUEST
				}
		elif (enquiry["request-uri"] == '/monitor/nsi'):
			res = {}
			slcies_context = self.nfvo_jox.get_slice_context()
			if slcies_context[0]:
				slcies_context = slcies_context[1]
				for slice_data in slcies_context:
					slice_name = slcies_context[slice_data]['slice_name']
					res[slice_name] = {}
					
					set_subslices = slcies_context[slice_data]["sub_slices"]
					for subslcie_name in set_subslices:
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[slice_name][data_subslcie_monitor] = data[1]
				response = {
					"ACK": True,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = slcies_context[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif (enquiry["request-uri"] == '/monitor/nsi/<string:nsi_name>'):
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				for subslcie_name in set_subslices:
					data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
					data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
					res[nsi_name][data_subslcie_monitor] = data[1]
				response = {
					"ACK": True,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif (enquiry["request-uri"] == '/monitor/nsi/<string:nsi_name>/<string:nssi_name>'):
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				subslice_exist = False
				for subslcie_name in set_subslices:
					if nssi_name == subslcie_name:
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[nsi_name][data_subslcie_monitor] = data[1]
						subslice_exist = True
				if subslice_exist:
					response = {
						"ACK": True,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					res = "The subslice {} does not exist or it is not attached to the slice {}".format(subslcie_name, nssi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif (enquiry["request-uri"] == '/monitor/nsi/<string:nsi_name>/<string:nssi_name>/<string:nssi_key>'):
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			nssi_key = parameters["nssi_key"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				subslice_exist = False
				nssi_key_exist = False
				for subslcie_name in set_subslices:
					if nssi_name == subslcie_name:
						subslice_exist = True
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						res[nsi_name][data_subslcie_monitor] = {}
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						for subslice_key in data[1]:
							if subslice_key == nssi_key:
								res[nsi_name][data_subslcie_monitor][subslice_key] = data[1][subslice_key]
								nssi_key_exist = True
				
				if subslice_exist:
					if nssi_key_exist:
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = "The key entity {} of the subslice {} attached to slice {} does not exist".format(nssi_key, nssi_name, nsi_name)
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
						}
				else:
					res = "The subslice {} attached to slice {} does not exist".format(nssi_name, nsi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif enquiry["request-uri"] == '/monitor/service/<string:nsi_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				for subslcie_name in set_subslices:
					data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
					data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
					
					res[nsi_name][data_subslcie_monitor] = {}
					res[nsi_name][data_subslcie_monitor]["service_status"] = data[1]["service_status"]
				response = {
					"ACK": True,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif enquiry["request-uri"] == '/monitor/service/<string:nsi_name>/<string:nssi_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			nssi_key = parameters["nssi_key"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				subslice_exist = False
				for subslcie_name in set_subslices:
					if nssi_name == subslcie_name:
						subslice_exist = True
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[nsi_name][data_subslcie_monitor] = {}
						res[nsi_name][data_subslcie_monitor]["service_status"] = data[1]["service_status"]
				if subslice_exist:
					response = {
						"ACK": True,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					res = "The subslice {} attached to slice {} does not exist".format(nssi_name, nsi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif enquiry["request-uri"] == '/monitor/service/<string:nsi_name>/<string:nssi_name>/<string:service_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			service_name = parameters["service_name"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				required_entity_exist = False
				subslice_exist = False
				for subslcie_name in set_subslices:
					if nssi_name == subslcie_name:
						subslice_exist = True
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[nsi_name][data_subslcie_monitor] = {}
						list_services = data[1]["service_status"]
						for service_tmp in list_services:
							if [*service_tmp][0] == service_name:
								res[nsi_name][data_subslcie_monitor]["service_status"] = service_tmp
								required_entity_exist = True
				if subslice_exist:
					if required_entity_exist:
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = "The entity {} of the subslcie {} attached to the slice {} does not exist".format(service_name, subslcie_name, nsi_name)
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
						}
				else:
					res = "The subslcie {} attached to the slice {} does not exist".format(subslcie_name, nsi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
					
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif enquiry["request-uri"] == '/monitor/machine/<string:nsi_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				for subslcie_name in set_subslices:
					data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
					data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
					
					res[nsi_name][data_subslcie_monitor] = {}
					res[nsi_name][data_subslcie_monitor]["machine_status"] = data[1]["machine_status"]
				response = {
					"ACK": True,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif enquiry["request-uri"] == '/monitor/machine/<string:nsi_name>/<string:nssi_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				subslice_exist = False
				for subslcie_name in set_subslices:
					if nssi_name == subslcie_name:
						subslice_exist = True
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[nsi_name][data_subslcie_monitor] = {}
						res[nsi_name][data_subslcie_monitor]["machine_status"] = data[1]["machine_status"]
				if subslice_exist:
					response = {
						"ACK": True,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					res = "The subslcie {} attached to the slice {} does not exist".format(subslcie_name, nsi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif enquiry["request-uri"] == '/monitor/machine/<string:nsi_name>/<string:nssi_name>/<string:machine_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name = parameters["nssi_name"]
			machine_name = parameters["machine_name"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				subslice_exist = False
				entity_key_exist = False
				for subslcie_name in set_subslices:
					if nssi_name == subslcie_name:
						subslice_exist = True
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[nsi_name][data_subslcie_monitor] = {}
						list_machines = data[1]["machine_status"]
						for machine_tmp in list_machines:
							if [*machine_tmp][0] == machine_name:
								res[nsi_name][data_subslcie_monitor]["machine_status"] = machine_tmp
								entity_key_exist = True
				
				if subslice_exist:
					if entity_key_exist:
						response = {
							"ACK": True,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_200_OK
						}
					else:
						res = "The entity {} of the subslcie {} attached to the slice {} does not exist".format(machine_name, subslcie_name, nsi_name)
						response = {
							"ACK": False,
							"data": res,
							"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
						}
				else:
					res = "The subslcie {} attached to the slice {} does not exist".format(subslcie_name, nsi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		
		elif enquiry["request-uri"] == '/monitor/relation/<string:nsi_name>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				for subslcie_name in set_subslices:
					data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
					data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
					
					res[nsi_name][data_subslcie_monitor] = {}
					res[nsi_name][data_subslcie_monitor]["relation_status"] = data[1]["relation_status"]
				response = {
					"ACK": True,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		
		elif enquiry["request-uri"] == '/monitor/relation/<string:nsi_name>/<string:nssi_name_source>':
			parameters = enquiry["parameters"]
			nsi_name = parameters["nsi_name"]
			nssi_name_source = parameters["nssi_name_source"]
			
			slice_data = self.nfvo_jox.get_slice_context(nsi_name)
			if slice_data[0]:
				slice_data = slice_data[1]
				set_subslices = slice_data["sub_slices"]
				res = {}
				res[nsi_name] = {}
				subslice_exist = False
				for subslcie_name in set_subslices:
					if nssi_name_source == subslcie_name:
						subslice_exist = True
						data_subslcie_monitor = ''.join(['slice_monitor_', str(subslcie_name).lower()])
						data = self.nfvo_jox.jesearch.get_source_index(data_subslcie_monitor)
						res[nsi_name][data_subslcie_monitor] = {}
						res[nsi_name][data_subslcie_monitor]["relation_status"] = data[1]["relation_status"]
				if subslice_exist:
					response = {
						"ACK": True,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_200_OK
					}
				else:
					res = "The subslcie {} attached to the slice {} does not exist".format(subslcie_name, nsi_name)
					response = {
						"ACK": False,
						"data": res,
						"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
					}
			else:
				res = slice_data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		elif (enquiry["request-uri"] == '/monitor/juju') or (enquiry["request-uri"] == '/monitor/juju/<string:juju_key_val>'):
			parameters = enquiry["parameters"]
			juju_key_val = parameters["juju_key_val"]
			data = loop.run(jmonitor_get_juju_status(juju_key_val))
			if  data[0]:
				res = data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_200_OK
				}
			else:
				res = data[1]
				response = {
					"ACK": False,
					"data": res,
					"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
				}
		else:
			response = "Reqquest not supported"
			response = {
				"ACK": False,
				"data": response,
				"status_code": self.nfvo_jox.gv.HTTP_404_NOT_FOUND
			}
		print(" [*] enquiry(%s)" % enquiry)
		print(colored(' [*] Waiting for messages. To exit press CTRL+C', 'green'))
		response = json.dumps(response)
		try:
			ch.basic_publish(exchange='',
			                 routing_key=props.reply_to,
			                 properties=pika.BasicProperties(correlation_id= \
				                                                 props.correlation_id),
			                 body=str(response))
			ch.basic_ack(delivery_tag=method.delivery_tag)
		except pika_exceptions.ConnectionClosed:
			pass
		except Exception as ex:
			logger.critical("Error while sending response: {}".format(ex))
	
	def check_existence_path(self, file_directory, nsi_name):
		if file_directory is None:
			# file_directory = self.nfvo_jox.dir_slice
			file_directory = self.nfvo_jox.gv.STORE_DIR
		if not os.path.exists(file_directory):
			message = self.path_not_found(file_directory)
			return [False, message]
		else:
			if os.path.isfile(file_directory):
				message = "You should specify directory not file path"
				return [False, message]
			else:
				if nsi_name is None:
					return [True, file_directory]
				else:
					if not file_directory.startswith("/"):
						file_directory = str(''.join(['/', file_directory]))
					if not file_directory.endswith("/"):
						file_directory = str(''.join([file_directory, '/']))
					full_path = str(''.join([file_directory, nsi_name]))
					if os.path.exists(full_path):
						if os.path.isfile(full_path):
							if full_path.endswith(".yaml") or full_path.endswith(
									".yml") or full_path.endswith(
									".json"):
								return [True, full_path]
							else:
								message = self.format_file_not_supported(full_path)
								return [False, message]
						else:
							message = self.path_not_found(nsi_name)
							return [False, message]
					else:
						message = self.path_not_found(full_path)
						return [False, message]
	def request_not_supported(self, request_url, requesr_method):
		message = "The method {} for the request {} is not supported".format(requesr_method, request_url)
		self.logger.debug(message)
		self.logger.info(message)
		return message
	
	def format_file_not_supported(self, file_name):
		message = "the format of the following template is not supported: {}".format(file_name)
		self.logger.debug(message)
		self.logger.info(message)
		return message
	
	def path_not_found(self, path):
		message = "The following {} does not exist: {}".format("file" if "." in path else "path", path)
		self.logger.debug(message)
		self.logger.info(message)
		return message
	def read_yaml_json(self, nsi_name):
		temp_name = nsi_name.split('/')
		temp_name = temp_name[len(temp_name) - 1]
		temp_name = temp_name.split('.')
		temp_name = temp_name[len(temp_name) - 1]
		if temp_name == "json":
			try:
				with open(nsi_name) as f:
					slice_data_file = json.load(f)
					return [True, slice_data_file]
			except:
				message = "Error while trying to open the file {}".format(nsi_name)
				return [False, message]
		elif (temp_name == "yaml") or (temp_name == "yml"):
			try:
				with open(nsi_name) as stream:
					slice_data_file = yaml.safe_load(stream)
				try:
					slice_data_file['metadata']['date'] = str(slice_data_file['metadata']['date'])
					slice_data_file = json.loads(json.dumps(slice_data_file))
				except:
					pass
				return [True, slice_data_file]
			except:
				message = "Error while trying to open the file {}".format(nsi_name)
				return [False, message]
		else:
			message = "The format of the file is not supported"
			return [False, message]
	def onboard_jox_package(self, files):
		try:
			with open('/proc/mounts', 'r') as f:
				mounts = [line.split()[1] for line in f.readlines()]
			
			dir_temp = self.nfvo_jox.gv.STORE_DIR
			
			
			dir_temp = dir_temp.split('/')
			dir_temp = '/'.join(x for x in dir_temp if x != '')
			dir_temp = ''.join(['/', dir_temp])
			
			if dir_temp not in mounts:
				message = "The directory {} is not mounted, and thus the templates can not be saved. You should firstly mount the directory {} \n\n".format(
					self.nfvo_jox.gv.STORE_DIR, self.nfvo_jox.gv.STORE_DIR)
				logger.error(message)
				return [False, message]
		except:
			message = "The directory {} is not mounted, and thus the templates can not be saved. You should firstly mount the directory {}  \n\n".format(
				self.nfvo_jox.gv.STORE_DIR, self.nfvo_jox.gv.STORE_DIR)
			logger.error(message)
			return [False, message]
		
		message = "The file can be oppened"
		return [True, message]

	def open_save_tar_gz(self, files):
		nsi_found = False
		nssi_found = False
		try:
			with tarfile.open(mode='r', fileobj=io.BytesIO(files)) as tar:
				for tarinfo in tar:
					tarname = tarinfo.name
					if str(tarname).endswith('yaml') or str(tarname).endswith('yaml'):
						if 'nsi' in str(tarname):
							nsi_found = True
						if 'nssi' in str(tarname):
							nssi_found = True
				if nsi_found and nssi_found:
					try:
						tar.extractall(self.nfvo_jox.gv.STORE_DIR)
						message = "The package was successfuly saved to the directory {}".format(self.nfvo_jox.gv.STORE_DIR)
						return [True, message]
					except:
						message = "Error while trying to save the package to the directory {}".format(
							self.nfvo_jox.gv.STORE_DIR)
						return [False, message]
				else:
					if nssi_found:
						message = "Error, there is no nsi in the package".format(
							self.nfvo_jox.gv.STORE_DIR)
					elif nsi_found:
						message = "Error, there is no nsi in the package".format(
							self.nfvo_jox.gv.STORE_DIR)
					else:
						message = "Error, there is no neither nsi nor nssi in the package".format(
							self.nfvo_jox.gv.STORE_DIR)
					return [False, message]
		except Exception as ex:
			message = "Error while opening the zip file: {}".format(str(ex.args[0]))
			return [False, message]

if __name__ == '__main__':
	logger = logging.getLogger('proj.jox')
	rmbq_server = server_RBMQ()
	rmbq_server.run()
