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
 """
__author__ = 'Eurecom'
__date__ = "11-January-2019"
__version__ = '1.0'
__maintainer__ = 'Osama Arouk, Navid Nikaein, Kostas Kastalis, and Rohan Kharade'
__email__ = 'contact@mosaic5g.io'
__description__ = "Define the list of driver that are supported by JOX." \
                  "The supported VIM drivers are:" \
                  "- LXC" \
                  "- KVM"

import os
import logging
from juju.model import Model
from juju import loop, utils
import traceback
import jsonpickle, json
from subprocess import check_output
import asyncio
from asyncio import subprocess
import datetime
dir_path = os.path.dirname(os.path.abspath(__file__ + "/../../../"))
from src.core.nso.template_manager import template_manager
from src.common.config import gv as global_varialbles
#
class LxcDriver(object):
	def __init__(self, pop_config, global_variable):
		self.driver_name = pop_config["pop-name"]
		self.zone = pop_config["zone"]
		self.domain = pop_config["domain"]
		self.scope = pop_config["scope"]
		self.driver_ssh_private_key = pop_config["ssh-private-key"]
		self.driver_ssh_username = pop_config["ssh-user"]
		self.driver_ssh_password = pop_config["ssh-password"]
		self.managed_by = pop_config["managed-by"]
		self.gv = global_variable
		
		self.machine_list = list()
		
		self.max_retry = self.gv.JUJU_MAX_RETRY_CONNECTION_MODEL_ACCESSIBLE # number of tentative to connect to juju. every tentative is after one second
		self.interval_access = self.gv.JUJU_INTERVAL_CONNECTION_MODEL_ACCESSIBLE
		self.logger = logging.getLogger('jox.LxcDriver.{}'.format(self.driver_name))
		self.log_config()
		self.template_manager = template_manager.TemplateManager(global_variable)
		
	def log_config(self):
		if self.gv.LOG_LEVEL == 'debug':
			self.logger.setLevel(logging.DEBUG)
		elif self.gv.LOG_LEVEL == 'info':
			self.logger.setLevel(logging.INFO)
		elif self.gv.LOG_LEVEL == 'warn':
			self.logger.setLevel(logging.WARNING)
		elif self.gv.LOG_LEVEL == 'error':
			self.logger.setLevel(logging.ERROR)
		elif self.gv.LOG_LEVEL == 'critic':
			self.logger.setLevel(logging.CRITICAL)
		else:
			self.logger.setLevel(logging.INFO)
	def check_machine_exist(self, cloud_name, model_name, machine_config):
		if "ip_addresses" in machine_config.keys():
			entity = 'ip_addresses'
		else:
			entity = 'ip'
		for machine in self.machine_list:
			if type(machine.ip) is str:
				if (machine.ip == machine_config[entity]) or (machine.ip in machine_config[entity]):
					return True
			else:
				for ip_addr in machine.ip:
					if (ip_addr == machine_config['ip_addresses']) or (ip_addr in machine_config[entity]):
						return True
			# if (machine.ip == machine_config['ip_addresses']):
			# if (machine.juju_cloud_name == cloud_name) \
			# 		and (machine.juju_model_name == model_name)\
			# 		and (machine.ip == machine_config['ip_addresses']):
				return True
		return False
	def get_machines_status(self):
		"""
		:return:
		"""
		data_str = jsonpickle.encode(self.machine_list)  # returns str
		data = json.loads(data_str)
		return data
	
	def get_machine_status(self, model_machine_name):
		for machine in self.machine_list:
			if machine.model_machine_name == model_machine_name:
				data_str = jsonpickle.encode(machine)  # returns str
				data = json.loads(data_str)
				return data
	
	def get_machine_object(self, model_machine_name):
		for machine in self.machine_list:
			if machine.model_machine_name == model_machine_name:
				return machine
	
	def get_mid_juju_from_mid_jmodel(self, mid_user_defined, machine_type):
		for vm in self.machine_list:
			if vm.mid_user_defined == mid_user_defined:
				return vm.mid_vnfm
		return -1
	def machine_exists(self, mid_user_defined):
		try:
			for vm in self.machine_list:
				if vm.mid_user_defined == mid_user_defined:
					return True
			return False
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			# raise ex
			return False
	def remove_machine_object(self, mid_user_defined):
		try:
			for mch in self.machine_list:
				if mch.mid_user_defined == mid_user_defined:
					self.machine_list.remove(mch)
			return False
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			return False
	
	def add_machine(self, machine_config, service_name, mid_ro, slice_name, model_name, cloud_name, nsi_id, machine_id_service=None):
		try:
			new_machine = _VmLxc()
			new_machine.build(slice_name,
			                  cloud_name,
			                  model_name,
			                  mid_ro,
			                  machine_config)
			add_new_context_machine = self.deploy_machine(new_machine, service_name, slice_name, nsi_id, "admin", machine_id_service)
			# add_new_context_machine = loop.run(self.deploy_machine(new_machine, service_name, slice_name, nsi_id, "admin", machine_id_service))

			machine_exist = False
			for machine in self.machine_list:
				if machine.mid_vnfm == new_machine.mid_vnfm:
					machine_exist = True
			if add_new_context_machine or (not machine_exist):
				self.machine_list.append(new_machine)
			self.allocate_machine(new_machine, service_name, mid_ro, machine_config['machine_name'])


		except Exception as ex:
			raise ex

	async def get_deployed_applications(self, machine_id_service, service_name, c_name, m_name, user="admin"):
		model = Model()

		add_new_context_machine = True
		if machine_id_service is not None:
			add_new_context_machine = False

		application_NotExist = None
		try:
			model_name = c_name + ":" + user + "/" + m_name
			retry_connect = True
			number_retry = 0
			while number_retry <= self.max_retry and retry_connect:
				number_retry += 1
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
																							   model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)

			app_keys = model.applications.keys()
			application_NotExist = True
			#

			for app in app_keys:
				if service_name == app and len(model.applications[app].units) > 0:
					application_NotExist = False
					app_values = model.applications.get(app)
					machine_id_service = app_values.units[0].machine.id
					add_new_context_machine = False
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
		return [machine_id_service, application_NotExist, add_new_context_machine]

	async def deploy_machine_2(self, new_machine, juju_cmd, machine_id_service, c_name, m_name, user="admin"):
		model = Model()
		try:
			model_name = c_name + ":" + user + "/" + m_name
			retry_connect = True
			number_retry = 0
			while number_retry <= self.max_retry and retry_connect:
				number_retry += 1
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
																							   model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)
			if machine_id_service is None:
				juju_machine = await model.add_machine(juju_cmd,
													   constraints={
														   'mem': int(new_machine.memory) * self.gv.GB,
														   'tags': [new_machine.mid_user_defined],
													   },
													   disks=[{
														   'pool': 'rootfs',
														   'size': int(new_machine.disc_size) * self.gv.GB,
														   'count': 1,
													   }],
													   )
			else:
				juju_machine = model.machines.get(machine_id_service)
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
		return juju_machine
	def deploy_machine(self, new_machine, service_name, slice_name, nsi_id, user="admin", machine_id_service=None):
		# model = Model()

		app_keys = loop.run(self.get_deployed_applications(
									machine_id_service,
									service_name, new_machine.juju_cloud_name, new_machine.juju_model_name, user))
		machine_id_service = app_keys[0]
		application_NotExist = app_keys[1]
		add_new_context_machine = app_keys[2]
		if True:
		# try:
			# c_name = new_machine.juju_cloud_name
			# m_name = new_machine.juju_model_name
			# model_name = c_name + ":" + user + "/" + m_name
			# retry_connect = True
			# number_retry = 0
			# while number_retry <= self.max_retry and retry_connect:
			# 	number_retry += 1
			# 	try:
			# 		self.logger.debug("{} time trying to connect to juju model:{} to add lxc machine".format(number_retry, model_name))
			# 		await model.connect(model_name)
			# 		retry_connect = False
			# 		self.logger.debug("Successful connection to the model {} ".format(model_name))
			# 	except:
			# 		await model.disconnect()
			# 		await asyncio.sleep(self.interval_access)
			#
			# app_keys = model.applications.keys()
			# application_NotExist = True
			# #
			#
			# for app in app_keys:
			# 	if service_name == app and len(model.applications[app].units) > 0:
			# 		application_NotExist = False
			# 		app_values = model.applications.get(app)
			# 		machine_id_service = app_values.units[0].machine.id
			# 		add_new_context_machine = True
			if application_NotExist and machine_id_service is None:
				cmd_list_lxc = ["lxc", "list", "--format", "json"]
				cmd_list_lxc_out = loop.run(run_command(cmd_list_lxc))
				cmd_list_lxc_out = json.loads(cmd_list_lxc_out)
				machine_name_exist = True

				tmp_counter = 0
				machine_lxd_name = "machine-{}".format(service_name)
				machine_lxd_name_tmp = machine_lxd_name
				while machine_name_exist:
					machine_name_exist_tmp = False
					for lxc_md in cmd_list_lxc_out:
						if lxc_md['name'] == machine_lxd_name_tmp:
							machine_name_exist_tmp = True
					if machine_name_exist_tmp:
						tmp_counter += 1
						machine_lxd_name_tmp = "{}-{}".format(machine_lxd_name, tmp_counter)
					else:
						machine_name_exist = False
						machine_lxd_name = machine_lxd_name_tmp

				container_name = machine_lxd_name
				cmd_lxc_create = ["lxc", "launch", "ubuntu:{}".format(new_machine.os_version), container_name]
				cmd_lxc_create_out = loop.run(run_command(cmd_lxc_create))
				self.logger.info(cmd_lxc_create_out)
				""" Get the ip addresss if the machine"""
				machine_ip_tmp = list()
				while len(machine_ip_tmp) == 0:
					cmd_list_lxc_out = loop.run(run_command(cmd_list_lxc))
					cmd_list_lxc_out = json.loads(cmd_list_lxc_out)
					for lxc_md in cmd_list_lxc_out:
						if lxc_md['name'] == container_name:
							for iface in lxc_md['state']['network']:
								for add_config in lxc_md['state']['network'][iface]['addresses']:
									if (add_config['family'] == 'inet') and (add_config['scope'] == 'global'):
										machine_ip_tmp.append(add_config['address'])
										print("ip addres v4=:{}".format(add_config['family']))
				machine_ip = list()
				for ip_add in machine_ip_tmp:
					packet_transmitted = 0
					packet_received = 0
					cmd_ping = ["ping", "-c", "3", ip_add]
					cmd_ping_out = loop.run(run_command(cmd_ping))
					lst = cmd_ping_out.split('\n')
					for i in range(2, len(lst)):
						if 'received' in str(lst[i]):
							items = (str(lst[i])).split(',')
							for item in items:
								if 'received' in str(item):
									item = [x for x in (str(item)).split(' ') if x]
									packet_received = int(item[0])
								if ('packets' in str(item)) and ('transmitted' in str(item)):
									item = [x for x in (str(item)).split(' ') if x]
									packet_transmitted = int(item[0])
									pass
							print(lst[i])
					if packet_received > 0:
						machine_ip.append(ip_add)
				###########
				SSH_USER_lxd = "root"
				ssh_key_puplic = ''.join([self.gv.SSH_KEY_DIRECTORY, self.gv.SSH_KEY_NAME, '.pub'])
				ssh_key_private = ''.join([self.gv.SSH_KEY_DIRECTORY, self.gv.SSH_KEY_NAME])

				machine_ip = machine_ip[0]



				message = "Injecting the public key in the lxd machine"
				self.logger.info(message)
				cmd_lxc_inject_ssh_key = ["lxc", "file", "push", ssh_key_puplic, "{}/root/.ssh/authorized_keys".format(container_name)]
				cmd_lxc_inject_ssh_key_out = loop.run(run_command(cmd_lxc_inject_ssh_key))

				message = "Injecting the public key in the lxd machine"
				self.logger.info(message)
				cmd_lxc_chmod = ["lxc", "exec", container_name, "--", "sh", "-c",
							 str("chmod 600 /root/.ssh/authorized_keys && sudo chown root: /root/.ssh/authorized_keys")]
				cmd_lxc_chmod_out = loop.run(run_command(cmd_lxc_chmod))

				message = "Ensuring ssh to the machine {}".format(machine_ip)
				self.logger.info(message)
				cmd_lxc_ssh_vm = ["ssh", "-o", "StrictHostKeyChecking={}".format("no"), "-i", ssh_key_private,
								  "{}@{}".format(SSH_USER_lxd, machine_ip), "pwd"]
				cmd_lxc_ssh_vm_out = loop.run(run_command(cmd_lxc_ssh_vm))

				loop.run(machine_configuration_for_jujuCharm(SSH_USER_lxd, machine_ip, ssh_key_private, self.logger))

				cmd_juju_addmachine = ["juju", "add-machine", "ssh:{}@{}".format(SSH_USER_lxd, machine_ip)]

				print("add achine: {}".format(cmd_juju_addmachine))
				cmd_lxc_ssh_vm_out = loop.run(run_command(cmd_juju_addmachine))
				machineId = str(cmd_lxc_ssh_vm_out).split('\n')
				for item in machineId:
					if "created machine" in item:
						val_id = [x for x in str(item).split(' ') if x]
						machine_id_service = val_id[2]

				juju_machine = loop.run(
					self.deploy_machine_2(None, None, machine_id_service, new_machine.juju_cloud_name,
										  new_machine.juju_model_name))


				# juju_cmd = "".join(["ssh:", SSH_USER_lxd, "@", machine_ip, ":", ssh_key_private])
				# juju_machine = loop.run(self.deploy_machine_2(new_machine, juju_cmd, machine_id_service, new_machine.juju_cloud_name, new_machine.juju_model_name))

				# juju_machine = await model.add_machine(juju_cmd,
				# 									   constraints={
				# 										   'mem': int(new_machine.memory) * self.gv.GB,
				# 										   'tags': [new_machine.mid_user_defined],
				# 									   },
				# 									   disks=[{
				# 										   'pool': 'rootfs',
				# 										   'size': int(new_machine.disc_size) * self.gv.GB,
				# 										   'count': 1,
				# 									   }],
				# 									   )
			else:
				juju_machine = loop.run(
					self.deploy_machine_2(None, None, machine_id_service, new_machine.juju_cloud_name,
										  new_machine.juju_model_name))

				# juju_machine = model.machines.get(machine_id_service)
				self.logger.info("The application {} is already deployed, and thus no machine added".format(service_name))
			new_machine.mid_vnfm = juju_machine.data["id"]  # Note here Machine ID

			#############
			cmd_machin_config = ["juju", "show-machine", new_machine.mid_vnfm, "--format", "json"]

			cmd_machin_config_out = loop.run(run_command(cmd_machin_config))
			cmd_machin_config_out = json.loads(cmd_machin_config_out)
			new_machine.ip = cmd_machin_config_out['machines'][new_machine.mid_vnfm]['ip-addresses']





			self.logger.info("The machine {} is added and its juju id is {}".format(new_machine.mid_user_defined, new_machine.mid_vnfm))
			machine_id = new_machine.mid_vnfm

			
			self.template_manager.update_slice_monitor_index("slice_monitor_"+slice_name.lower(),
			                                                 "machine_status",
			                                                 service_name,
			                                                 "juju_mid",
			                                                 str(machine_id),
			                                                 nsi_id)
			self.template_manager.update_slice_monitor_index('slice_keys_'+nsi_id.lower(),
			                                                 "machine_keys",
			                                                 service_name,
			                                                 "juju_mid",
			                                                 str(machine_id),
			                                                 nsi_id)
			self.template_manager.update_slice_monitor_index("slice_monitor_"+slice_name.lower(),
			                                                 "machine_status",
			                                                 service_name,
			                                                 "type",
			                                                 "lxc",
			                                                 nsi_id)


			self.logger.info("Deployed LXC Machine {} {} {}".format(new_machine.mid_vnfm, len(juju_machine.data), juju_machine.data))

		# except Exception as ex:
		# 	self.logger.error(traceback.format_exc())
		# 	raise ex
		# finally:
		# 	await model.disconnect()
		return add_new_context_machine
	async def update_machine(self, machine_config):
		for machine in self.machine_list:
			if machine_config['machine_name'] == machine.mid_user_defined:
				new_machine = machine
		try:
			model = Model()
			c_name = new_machine.juju_cloud_name
			m_name = new_machine.juju_model_name
			m_user = 'admin'
			model_name = c_name + ":" + m_user + '/' + m_name
			await model.connect(model_name)
			
			#######################
			_id = new_machine.mid_vnfm
			machine_ready = False
			while not machine_ready:
				await model.disconnect()
				await asyncio.sleep(1)
				
				await model.connect(model_name)
				
				if model.machines[str(_id)].data["agent-status"]["current"] == "started":
					if model.machines[str(_id)].data["addresses"]:
						new_machine.mid_vim = model.machines[str(_id)].data["instance-id"]
						self.logger.debug("mid_lxc of the new container is %s", new_machine.mid_vim)
						
						addresses = model.machines[str(_id)].data["addresses"]
						for address in addresses:
							if address["type"] == "ipv4": # and address["scope"] == "local-cloud":
								ip = address["value"]
								new_machine.ip = ip
								self.logger.debug("ip of the new container is {}".format(ip))
								machine_ready = True
						if not machine_ready:
							self.logger.critical("No ip address found for the machine {}".format(new_machine.mid_user_defined))
							self.logger.info("No ip address found for the machine {}".format(new_machine.mid_user_defined))
							machine_ready = True
		except Exception as ex:
			raise ex
		
		finally:
			await model.disconnect()
	async def delete_machine(self, service_name, machine_name_vnfm, machine_id_ro, machine_name_userdefined,
	                         jcloud, jmodel,
	                         slice_name, subslice_name=None, user="admin"):
		model = Model()
		try:
			c_name = jcloud
			m_name = jmodel
			model_name = c_name + ":" + user + "/" + m_name
			retry_connect = True
			number_retry = 0
			while number_retry <= self.max_retry and retry_connect:
				number_retry += 1
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
						                                                                       model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)

			
			try:
				await model.machines[str(machine_name_vnfm)].destroy(force=True)
			except:
				self.logger.critical("Either the application does not exist it can not be removed")
			self.logger.info("Remove the machine {} hosting the application {}".format(machine_name_vnfm, service_name))
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
	def register_machine_juju(self, cloud_name,
								model_name,
								mid_ro,
								machine_config):
		try:
			new_machine = _VmLxc()
			new_machine.register(cloud_name,
						          model_name,
						          mid_ro,
						          machine_config)
			self.machine_list.append(new_machine)
		
		except Exception as ex:
			raise ex
	def allocate_machine(self, new_machine, service_name, mid_ro, machine_name):
		for machine_current in self.machine_list:
			if new_machine.mid_vnfm == machine_current.mid_vnfm:
				machine_current.available = False
				machine_current.tmp_service_name = service_name
				machine_current.tmp_mid_ro = mid_ro
				machine_current.mid_user_defined = machine_name
				machine_current.ip = new_machine.ip

				break
	def release_machine(self):
		raise NotImplementedError()
	def get_stats(self):
		raise NotImplementedError()
	def validate(self):
		raise NotImplementedError()

	def gt(self, dt_str):
		try:
			dt, _, us = dt_str.partition(".")
			dt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
			us = int(us.rstrip("Z"), 10) / 1000
			return dt + datetime.timedelta(microseconds=us)
		except Exception as ex:
			raise ex


class KvmDriver(object):
	def __init__(self, pop_config, global_variable):
		self.driver_name = pop_config["pop-name"]
		self.zone = pop_config["zone"]
		self.domain = pop_config["domain"]
		self.scope = pop_config["scope"]
		self.driver_ssh_private_key = pop_config["ssh-private-key"]
		self.driver_ssh_username = pop_config["ssh-user"]
		self.driver_ssh_password = pop_config["ssh-password"]
		self.managed_by = pop_config["managed-by"]

		self.gv = global_variable
		self.machine_list = list()
		self.logger = logging.getLogger('jox.KvmDriver.{}'.format(self.driver_name))
		self.max_retry = self.gv.JUJU_MAX_RETRY_CONNECTION_MODEL_ACCESSIBLE
		self.interval_access = self.gv.JUJU_INTERVAL_CONNECTION_MODEL_ACCESSIBLE
		self.template_manager = template_manager.TemplateManager(global_variable)

	def check_machine_exist(self, cloud_name, model_name, machine_config):
		if "ip_addresses" in machine_config.keys():
			entity = 'ip_addresses'
		else:
			entity = 'ip'
		for machine in self.machine_list:
			if type(machine.ip) is str:
				if (machine.ip == machine_config[entity]) or (machine.ip in machine_config[entity]):
					return True
			else:
				for ip_addr in machine.ip:
					if (ip_addr == machine_config['ip_addresses']) or (ip_addr in machine_config[entity]):
						return True
			# if (machine.ip == machine_config['ip_addresses']) or (machine.ip in machine_config['ip_addresses']):
			# if (machine.juju_cloud_name == cloud_name) \
			# 		and (machine.juju_model_name == model_name)\
			# 		and (machine.ip == machine_config['ip_addresses']):
			# 	return True
		return False
	def get_machines_status(self):
		data_str = jsonpickle.encode(self.machine_list)
		data = json.loads(data_str)
		return data
	def get_machine_status(self, model_machine_name):
		for machine in self.machine_list:
			if machine.model_machine_name == model_machine_name:
				data_str = jsonpickle.encode(machine)
				data = json.loads(data_str)
				return data
	
	def get_machine_object(self, model_machine_name):
		for machine in self.machine_list:
			if machine.model_machine_name == model_machine_name:
				return machine
	
	def get_mid_juju_from_mid_jmodel(self, mid_user_defined, machine_type):
		for vm in self.machine_list:
			if vm.mid_user_defined == mid_user_defined:
				return vm.mid_vnfm
		return -1
	
	def machine_exists(self, mid_user_defined):
		try:
			for vm in self.machine_list:
				if vm.mid_user_defined == mid_user_defined:
					return True
			return False
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
	
	def add_machine(self, machine_config, service_name, mid_ro, subslice_name, model_name, cloud_name, nsi_id, machine_id_service=None):
		try:
			new_machine = _VmKvm()

			new_machine.build(subslice_name,
			                  cloud_name,
			                  model_name,
			                  mid_ro,
			                  machine_config)
			add_new_context_machine = loop.run(self.deploy_kvm(new_machine, service_name, subslice_name, nsi_id, "admin", machine_id_service))

			machine_exist = False
			for machine in self.machine_list:
				if machine.mid_vnfm == new_machine.mid_vnfm:
					machine_exist = True
			if add_new_context_machine or (not machine_exist):
				self.machine_list.append(new_machine)
			self.allocate_machine(new_machine, service_name, mid_ro, machine_config['machine_name'])
		except Exception as ex:
			raise ex

	async def deploy_kvm(self, new_machine, service_name, subslice_name, nsi_id, m_user="admin", machine_id_service=None):
		model = Model()

		add_new_context_machine = True
		if machine_id_service is not None:
			add_new_context_machine = False
		try:
			c_name = new_machine.juju_cloud_name
			m_name = new_machine.juju_model_name
			model_name = c_name + ":" + m_user + '/' + m_name

			number_retry = 0
			retry_connect = True
			while number_retry <= self.max_retry and retry_connect:
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
																							   model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)

			app_keys = model.applications.keys()
			application_NotExist = True
			for app in app_keys:
				if service_name == app and len(model.applications[app].units) > 0:
					application_NotExist = False
					app_values = model.applications.get(app)
					machine_id_service = app_values.units[0].machine.id
					add_new_context_machine = False
			if application_NotExist and machine_id_service is None:
				ssh_key_puplic = ''.join([self.gv.SSH_KEY_DIRECTORY, self.gv.SSH_KEY_NAME, '.pub'])
				ssh_key_private = ''.join([self.gv.SSH_KEY_DIRECTORY, self.gv.SSH_KEY_NAME])
				################
				cmd_list_kvm = "uvt-kvm list"
				list_output_tmp = check_output(cmd_list_kvm, shell=True)
				list_output_tmp = (list_output_tmp.decode("utf-8")).rstrip()
				list_machine = list()
				temp_item = ""
				for item in list_output_tmp:
					if str(item).encode() == b'\n':
						list_machine.append(temp_item)
						temp_item = ""
					else:
						temp_item = "".join([temp_item, item])
				list_machine.append(temp_item)
				machine_ip = ""
				for current_machine in list_machine:
					if new_machine.mid_user_defined == current_machine:
						cmd_ip = "uvt-kvm ip " + new_machine.mid_user_defined
						output = check_output(cmd_ip, shell=True)
						machine_ip = (output.decode("utf-8")).rstrip()
						break
				###################
				if machine_ip == "":
					cmd_create_kvm = ["uvt-kvm", "create",
									  new_machine.mid_user_defined,
									  "release={}".format(new_machine.os_series),
									  "--memory", str(new_machine.memory),
									  "--cpu", str(new_machine.cpu),
									  "--disk", str(new_machine.disc_size),
									  "--ssh-public-key-file", ssh_key_puplic,
									  "--password", self.gv.SSH_PASSWORD
									  ]
					cmd_create_kvm_out = await run_command(cmd_create_kvm)

					cmd_wait_kvm = ["uvt-kvm", "wait", new_machine.mid_user_defined]
					cmd_ip = ["uvt-kvm", "ip", new_machine.mid_user_defined]

					cmd_wait_kvm_out = await run_command(cmd_wait_kvm)
					cmd_ip_out = await run_command(cmd_ip)
					machine_ip = (str(cmd_ip_out).split('\n'))[0]

				self.logger.debug(
					"The ip address of the machine {} is {}".format(new_machine.mid_user_defined, machine_ip))
				self.logger.info(
					'Adding the kvm machine {} whose ip {} to juju'.format(new_machine.mid_user_defined, machine_ip))
				await machine_configuration_for_jujuCharm(self.gv.SSH_USER, machine_ip, ssh_key_private, self.logger)
				await asyncio.sleep(10)
				juju_cmd = "".join(["ssh:", self.gv.SSH_USER, "@", machine_ip, ":", ssh_key_private])
				juju_machine = await model.add_machine(juju_cmd,
													   constraints={
														   'tags': [new_machine.mid_user_defined],
														   'virt_type': 'kvm'
													   }
													   )
			else:
				juju_machine = model.machines.get(machine_id_service)
			new_machine.mid_vnfm = juju_machine.data["id"]
			#############
			cmd_machin_config = ["juju", "show-machine", new_machine.mid_vnfm, "--format", "json"]

			cmd_machin_config_out = await run_command(cmd_machin_config)
			cmd_machin_config_out = json.loads(cmd_machin_config_out)
			new_machine.ip = cmd_machin_config_out['machines'][new_machine.mid_vnfm]['ip-addresses']

			self.template_manager.update_slice_monitor_index("slice_monitor_" + subslice_name.lower(),
															 "machine_status",
															 service_name,
															 "juju_mid",
															 str(new_machine.mid_vnfm),
															 nsi_id)
			self.template_manager.update_slice_monitor_index('slice_keys_' + nsi_id.lower(), "machine_keys",
															 service_name, "juju_mid", str(new_machine.mid_vnfm),
															 nsi_id)
			self.template_manager.update_slice_monitor_index("slice_monitor_" + subslice_name.lower(),
															 "machine_status", service_name, "type", "kvm", nsi_id)

			self.logger.debug(
				"The machine {} with juju id {} is already added to juju model".format(new_machine.mid_user_defined,
																					   juju_machine.data["id"]))
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
		return add_new_context_machine

	async def update_machine(self, machine_config):
		for machine in self.machine_list:
			if machine_config['machine_name'] == machine.mid_user_defined:
				new_machine = machine
		try:
			model = Model()
			c_name = new_machine.juju_cloud_name
			m_name = new_machine.juju_model_name
			m_user = 'admin'
			model_name = c_name + ":" + m_user + '/' + m_name
			await model.connect(model_name)
			
			#######################
			_id = new_machine.mid_vnfm
			machine_ready = False
			while not machine_ready:
				await model.disconnect()
				await asyncio.sleep(1)
				
				await model.connect(model_name)
				
				if model.machines[str(_id)].data["agent-status"]["current"] == "started":
					if model.machines[str(_id)].data["addresses"]:
						new_machine.mid_vim = model.machines[str(_id)].data["instance-id"]
						self.logger.debug("mid_lxc of the new container is %s", new_machine.mid_vim)
						
						addresses = model.machines[str(_id)].data["addresses"]
						for address in addresses:
							if address["type"] == "ipv4": # and address["scope"] == "local-cloud":
								ip = address["value"]
								new_machine.ip = ip
								self.logger.debug("ip of the new container is {}".format(ip))
								machine_ready = True
						if not machine_ready:
							self.logger.info("No ip address found for the machine {}".format(new_machine.mid_user_defined))
							machine_ready = True
		except Exception as ex:
			raise ex
		
		finally:
			await model.disconnect()
	
	async def delete_machine(self, service_name, machine_name_vnfm, machine_id_ro, machine_name_userdefined,
	                         jcloud, jmodel,
	                         slice_name, subslice_name=None, user="admin"):
		model = Model()
		try:
			c_name = jcloud
			m_name = jmodel
			model_name = c_name + ":" + user + "/" + m_name
			retry_connect = True
			number_retry = 0
			while number_retry <= self.max_retry and retry_connect:
				number_retry += 1
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
						                                                                       model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)
			
			try:
				await model.machines[str(machine_name_vnfm)].destroy(force=True)
				cmd_destroy_kvm = ["uvt-kvm", "destroy", machine_name_userdefined]
				output_list = await run_command(*cmd_destroy_kvm)
			except:
				self.logger.critical("Either the application does not exist it can not be removed")
			self.logger.info("Remove the machine {} hosting the application {}".format(machine_name_vnfm, service_name))
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
	def register_machine_juju(self, cloud_name,
								model_name,
								mid_ro,
								machine_config):
		try:
			new_machine = _VmKvm()
			new_machine.register(cloud_name,
								 model_name,
								 mid_ro,
								 machine_config)
			self.machine_list.append(new_machine)
		except Exception as ex:
			raise ex

	def allocate_machine(self, new_machine, service_name, mid_ro, machine_name):
		for machine_current in self.machine_list:
			if new_machine.mid_vnfm == machine_current.mid_vnfm:
				machine_current.available = False
				machine_current.tmp_service_name = service_name
				machine_current.tmp_mid_ro = mid_ro
				machine_current.mid_user_defined = machine_name
				machine_current.ip = new_machine.ip
				break
	def release_machine(self):
		raise NotImplementedError()
	def get_stats(self):
		raise NotImplementedError()
	def validate(self):
		raise NotImplementedError()


class PhyDriver(object):
	def __init__(self, pop_config, global_variable):
		self.driver_name = pop_config["pop-name"]
		self.zone = pop_config["zone"]
		self.domain = pop_config["domain"]
		self.scope = pop_config["scope"]
		self.driver_ssh_private_key = pop_config["ssh-private-key"]
		self.driver_ssh_username = pop_config["ssh-user"]
		self.driver_ssh_password = pop_config["ssh-password"]
		self.managed_by = pop_config["managed-by"]
		
		self.gv = global_variable
		self.machine_list = list()
		self.logger = logging.getLogger('jox.PhyDriver.{}'.format(self.driver_name))
		self.max_retry = self.gv.JUJU_MAX_RETRY_CONNECTION_MODEL_ACCESSIBLE
		self.interval_access = self.gv.JUJU_INTERVAL_CONNECTION_MODEL_ACCESSIBLE
		self.template_manager = template_manager.TemplateManager(global_variable)

	def check_machine_exist(self, cloud_name, model_name, machine_config):
		if "ip_addresses" in machine_config.keys():
			entity = 'ip_addresses'
		else:
			entity = 'ip'
		for machine in self.machine_list:
			if type(machine.ip) is str:
				if (machine.ip == machine_config[entity]) or (machine.ip in machine_config[entity]):
					return True
			else:
				for ip_addr in machine.ip:
					if (ip_addr == machine_config['ip_addresses']) or (ip_addr in machine_config[entity]):
						return True
			# for ip_add in machine.addresses:
			# 	if ip_add in machine_config['ip_addresses']:
			# 		return True
			# if (machine.juju_cloud_name == cloud_name) \
			# 		and (machine.juju_model_name == model_name):
			# 	for ip_add in machine.addresses:
			# 		if ip_add in machine_config['ip_addresses']:
			# 			return True
		return False
	def get_machines_status(self):
		data_str = jsonpickle.encode(self.machine_list)
		data = json.loads(data_str)
		return data
	
	def get_machine_status(self, model_machine_name):
		for machine in self.machine_list:
			if machine.model_machine_name == model_machine_name:
				data_str = jsonpickle.encode(machine)
				data = json.loads(data_str)
				return data
	
	def get_machine_object(self, model_machine_name):
		for machine in self.machine_list:
			if machine.model_machine_name == model_machine_name:
				return machine
	
	def get_mid_juju_from_mid_jmodel(self, mid_user_defined, machine_type):
		for vm in self.machine_list:
			if vm.mid_user_defined == mid_user_defined:
				return vm.mid_vnfm
		return -1

	def machine_exists(self, mid_user_defined):
		try:
			for vm in self.machine_list:
				if vm.mid_user_defined == mid_user_defined:
					return True
			return False
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			# raise ex
			return False
	def add_machine(self, machine_config, service_name, mid_ro, subslice_name, model_name, cloud_name, nsi_id, machine_id_service=None):
		try:
			new_machine = _PhysicalMachine()
			
			new_machine.build(subslice_name,
							  	cloud_name,
								model_name,
								mid_ro,
								machine_config)

			# cloud_name,
			# model_name,
			# mid_ro,
			# machine_config

			add_new_context_machine = loop.run(self.deploy_physical_machine(new_machine, service_name, subslice_name, nsi_id, "admin", machine_id_service))
			machine_exist = False
			for machine in self.machine_list:
				if machine.mid_vnfm == new_machine.mid_vnfm:
					machine_exist = True
			if add_new_context_machine or (not machine_exist):
				self.machine_list.append(new_machine)
			self.allocate_machine(new_machine, service_name, mid_ro, machine_config['machine_name'])

		except Exception as ex:
			raise ex
	
	async def get_machines_jujuModel(self, cloud_name=None, model_name=None, user_name="admin"):
		model = Model()
		if (cloud_name is None) and (model_name is None):
			try:
				await model.connect_current()
			except:
				message = "Error while trying to connect to the current juju model"
				self.logger.error(message)
				return [False, message]
		else:
			try:
				model_name = cloud_name + ":" + user_name + '/' + model_name
				await model.connect(model_name)
			except:
				message = "Error while trying to connect to the juju model {}:{}/{}".format(cloud_name, user_name,
				                                                                            model_name)
				self.logger.error(message)
				return [False, message]
		juju_status = (await utils.run_with_interrupt(model.get_status(), model._watch_stopping, loop=model.loop))
		return [True, juju_status.machines]

	async def deploy_physical_machine(self, new_machine, service_name, subslice_name, nsi_id, m_user="admin",
						 machine_id_service=None):
		model = Model()

		add_new_context_machine = True
		if machine_id_service is not None:
			add_new_context_machine = False
		try:
			c_name = new_machine.juju_cloud_name
			m_name = new_machine.juju_model_name
			model_name = c_name + ":" + m_user + '/' + m_name

			number_retry = 0
			retry_connect = True
			while number_retry <= self.max_retry and retry_connect:
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
																							   model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)

			app_keys = model.applications.keys()
			application_NotExist = True
			for app in app_keys:
				if service_name == app and len(model.applications[app].units) > 0:
					application_NotExist = False
					app_values = model.applications.get(app)
					machine_id_service = app_values.units[0].machine.id
					add_new_context_machine = False
			if application_NotExist and machine_id_service is None:
				ssh_key_puplic = ''.join([self.gv.SSH_KEY_DIRECTORY, self.gv.SSH_KEY_NAME, '.pub'])
				ssh_key_private = ''.join([self.gv.SSH_KEY_DIRECTORY, self.gv.SSH_KEY_NAME])

				machine_ip = "127.0.0.1"
				ssh_user = "arouk"
				cmd_kvm_ssh_vm = ["ssh", "-o", "StrictHostKeyChecking={}".format("no"), "-i", ssh_key_private,
								  "{}@{}".format(ssh_user, machine_ip), "pwd"]
				self.logger.debug(
					"The ip address of the machine {} is {}".format(new_machine.mid_user_defined, machine_ip))
				self.logger.info(
					'Adding the kvm machine {} whose ip {} to juju'.format(new_machine.mid_user_defined, machine_ip))
				await machine_configuration_for_jujuCharm(self.gv.SSH_USER, machine_ip, ssh_key_private, self.logger)
				await asyncio.sleep(5)
				juju_cmd = "".join(["ssh:", self.gv.SSH_USER, "@", machine_ip, ":", ssh_key_private])
				juju_machine = await model.add_machine(juju_cmd)
			else:
				juju_machine = model.machines.get(machine_id_service)
			new_machine.mid_vnfm = juju_machine.data["id"]
			#############
			cmd_machin_config = ["juju", "show-machine", new_machine.mid_vnfm, "--format", "json"]

			cmd_machin_config_out = await  run_command(cmd_machin_config)
			cmd_machin_config_out = json.loads(cmd_machin_config_out)
			new_machine.ip = cmd_machin_config_out['machines'][new_machine.mid_vnfm]['ip-addresses']

			self.template_manager.update_slice_monitor_index("slice_monitor_" + subslice_name.lower(),
															 "machine_status",
															 service_name,
															 "juju_mid",
															 str(new_machine.mid_vnfm),
															 nsi_id)
			self.template_manager.update_slice_monitor_index('slice_keys_' + nsi_id.lower(), "machine_keys",
															 service_name, "juju_mid", str(new_machine.mid_vnfm),
															 nsi_id)
			self.template_manager.update_slice_monitor_index("slice_monitor_" + subslice_name.lower(),
															 "machine_status", service_name, "type", "kvm", nsi_id)

			self.logger.debug(
				"The machine {} with juju id {} is already added to juju model".format(new_machine.mid_user_defined,
																					   juju_machine.data["id"]))
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
		return add_new_context_machine

	async def update_machine(self, machine_config):
		for machine in self.machine_list:
			if machine_config['machine_name'] == machine.mid_user_defined:
				new_machine = machine
		try:
			model = Model()
			c_name = new_machine.juju_cloud_name
			m_name = new_machine.juju_model_name
			m_user = 'admin'
			model_name = c_name + ":" + m_user + '/' + m_name
			await model.connect(model_name)
			
			#######################
			_id = new_machine.mid_vnfm
			machine_ready = False
			while not machine_ready:
				await model.disconnect()
				await asyncio.sleep(1)
				
				await model.connect(model_name)
				
				if model.machines[str(_id)].data["agent-status"]["current"] == "started":
					if model.machines[str(_id)].data["addresses"]:
						new_machine.mid_vim = model.machines[str(_id)].data["instance-id"]
						self.logger.debug("mid_lxc of the new container is %s", new_machine.mid_vim)
						
						addresses = model.machines[str(_id)].data["addresses"]
						for address in addresses:
							if address["type"] == "ipv4":  # and address["scope"] == "local-cloud":
								ip = address["value"]
								new_machine.ip = ip
								self.logger.debug("ip of the new container is {}".format(ip))
								machine_ready = True
						if not machine_ready:
							self.logger.info(
								"No ip address found for the machine {}".format(new_machine.mid_user_defined))
							machine_ready = True
		except Exception as ex:
			raise ex
		
		finally:
			await model.disconnect()
	
	async def delete_machine(self, service_name, machine_name_vnfm, machine_id_ro, machine_name_userdefined,
	                         jcloud, jmodel,
	                         slice_name, subslice_name=None, user="admin"):
		model = Model()
		try:
			c_name = jcloud
			m_name = jmodel
			model_name = c_name + ":" + user + "/" + m_name
			retry_connect = True
			number_retry = 0
			while number_retry <= self.max_retry and retry_connect:
				number_retry += 1
				try:
					self.logger.debug(
						"{} time trying to connect to juju model:{} to add lxc machine".format(number_retry,
						                                                                       model_name))
					await model.connect(model_name)
					retry_connect = False
					self.logger.debug("Successful connection to the model {} ".format(model_name))
				except:
					await model.disconnect()
					await asyncio.sleep(self.interval_access)
			
			try:
				await model.machines[str(machine_name_vnfm)].destroy(force=True)
				cmd_destroy_kvm = ["uvt-kvm", "destroy", machine_name_userdefined]
				output_list = await run_command(*cmd_destroy_kvm)
			except:
				self.logger.critical("Either the application does not exist it can not be removed")
			self.logger.info("Remove the machine {} hosting the application {}".format(machine_name_vnfm, service_name))
		except Exception as ex:
			self.logger.error(traceback.format_exc())
			raise ex
		finally:
			await model.disconnect()
	
	def register_machine_juju(self, cloud_name,
								model_name,
								mid_ro,
								machine_config):
		try:
			new_machine = _PhysicalMachine()
			new_machine.register(cloud_name,
								 model_name,
								 mid_ro,
								 machine_config)
			self.machine_list.append(new_machine)
		except Exception as ex:
			raise ex

	def allocate_machine(self, new_machine, service_name, mid_ro, machine_name):
		for machine_current in self.machine_list:
			if new_machine.mid_vnfm == machine_current.mid_vnfm:
				machine_current.available = False
				machine_current.tmp_service_name = service_name
				machine_current.tmp_mid_ro = mid_ro
				machine_current.mid_user_defined = machine_name
				machine_current.ip = new_machine.ip
				break
	
	def release_machine(self):
		raise NotImplementedError()
	
	def get_stats(self):
		raise NotImplementedError()
	
	def validate(self):
		raise NotImplementedError()


class _VmKvm():
	def __init__(self):
		self.logger = logging.getLogger('jox.VimDriver.VmKvm')
		self.subslice_name = list() # list of subslice srerved by the machine
		
		# credential of juju
		self.juju_cloud_name = ""
		self.juju_model_name = ""
		self.juju_endpoint = ""
		self.juju_user_passwd = dict() # list of user names and password
		
		self.mid_user_defined = ""
		self.mid_vnfm = "" # juju id of the machine in case of juju
		self.mid_vim = "" # value assigned by LXD hypervisor
		self.mid_ro  = "" # name given by the resource controller
		
		self.ip = ""
		self.template = ""
		
		self.cpu = ""
		self.memory = ""
		self.disc_size = ""
		
		self.os_series = ""
		self.os_version = ""

		self.auto = False
		
		self.available = True

		self.tmp_service_name = None
		self.tmp_mid_ro = None
	
	def build(self,
	          subslice_name,
	          cloud_name,
	          model_name,
	          mid_ro,
	          machine_config):
		try:
			self.subslice_name.append(subslice_name)
			
			# credential of juju
			self.juju_cloud_name = cloud_name
			self.juju_model_name = model_name
			self.juju_endpoint = None
			
			self.mid_user_defined = machine_config['machine_name']
			self.mid_vim = ""  # value assigned by LXD hypervisor
			self.mid_ro = mid_ro  # name given by the resource controller
			
			self.cpu = machine_config['host']['num_cpus']
			self.disc_size = machine_config['host']['disk_size']
			self.memory = machine_config['host']['mem_size']
			if machine_config['os']['distribution'] == "Ubuntu":
				os_version = str(machine_config['os']['version'])
				try:
					self.os_series = global_varialbles.OS_SERIES[os_version]
				except:
					message = "The os version {} for the machine {} from the subslice {} is not defined. Please define it in gv file in the variable OS_SERIES".format(os_version, machine_config['machine_name'], subslice_name)
					self.logger.debug(message)
					self.logger.critical(message)
					self.logger.info(message)
		except Exception as ex:
			raise ex

	def register(self,
				 cloud_name,
				 model_name,
				 mid_ro,
				 machine_config):
		try:
			# credential of juju
			self.juju_cloud_name = cloud_name
			self.juju_model_name = model_name
			self.juju_endpoint = None

			self.mid_user_defined = machine_config['machine_name']
			self.mid_vim = ""
			self.mid_vnfm = machine_config['juju_id']
			self.mid_ro = mid_ro  # name given by the resource controller

			self.cpu = machine_config['host']['num_cpus']
			self.disc_size = machine_config['host']['disk_size']
			self.memory = machine_config['host']['mem_size']
			if machine_config['os']['distribution'] == "Ubuntu":
				os_version = str(machine_config['os']['version'])
				for os_v in global_varialbles.OS_SERIES:
					if (os_version in os_v) or (os_v in os_version):
						self.os_series = global_varialbles.OS_SERIES[os_v]
				if self.os_series == "":
					message = "The os version {} for the machine {} is not defined. Please define it in gv file in the variable OS_SERIES".format(
						os_version, machine_config['machine_name'])
					self.logger.critical(message)
					self.logger.info(message)
			self.ip = machine_config['ip_addresses']
			self.available = machine_config['machine_available']

		except ValueError as ex:
			raise ex

	def validate(self, cloud_name, model_name, machine_config):
		raise NotImplementedError()


class _VmLxc():
	
	def __init__(self):
		self.logger = logging.getLogger('jox.VimDriver.VmLxc')
		self.subslice_name = list()  # list of subslice srerved by the machine
		
		# credential of juju
		self.juju_cloud_name = ""
		self.juju_model_name = ""
		self.juju_endpoint = ""
		self.juju_user_passwd = dict()  # list of user names and password
		
		self.mid_user_defined = ""
		self.mid_vnfm = ""  # juju id of the machine in case of juju
		self.mid_vim = ""  # value assigned by LXD hypervisor
		self.mid_ro = ""  # name given by the resource controller
		
		self.ip = ""
		self.template = ""
		
		self.cpu = ""
		self.memory = ""
		self.disc_size = ""
		
		self.os_series = ""
		self.os_version = ""

		self.auto = False
		self.available = True

		self.tmp_service_name = None
		self.tmp_mid_ro = None

		
	def build(self,
	          subslice_name,
	          cloud_name,
	          model_name,
	          mid_ro,
	          machine_config):
		try:
			self.subslice_name.append(subslice_name)
			
			# credential of juju
			self.juju_cloud_name = cloud_name
			self.juju_model_name = model_name
			self.juju_endpoint = None
			
			self.mid_user_defined = machine_config['machine_name']
			self.mid_vim = ""  # value assigned by LXD hypervisor
			self.mid_ro = mid_ro  # name given by the resource controller
			
			self.cpu = machine_config['host']['num_cpus']
			self.disc_size = machine_config['host']['disk_size']
			self.memory = machine_config['host']['mem_size']
			if machine_config['os']['distribution'] == "Ubuntu":
				self.os_version = str(machine_config['os']['version'])
				try:
					self.os_series = global_varialbles.OS_SERIES[self.os_version]
				except:
					message = "The os version {} for the machine {} from the subslice {} is not defined. Please define it in gv file in the variable OS_SERIES".format(
							self.os_version, machine_config['machine_name'], subslice_name)
					self.logger.critical(message)
					self.logger.info(message)
		except ValueError as ex:
			raise ex
	
	def register(self,
	          cloud_name,
	          model_name,
	          mid_ro,
	          machine_config):
		try:
			# credential of juju
			self.juju_cloud_name = cloud_name
			self.juju_model_name = model_name
			self.juju_endpoint = None
			
			self.mid_user_defined = machine_config['machine_name']
			self.mid_vim = ""
			self.mid_vnfm = machine_config['juju_id']
			self.mid_ro = mid_ro  # name given by the resource controller
			
			self.cpu = machine_config['host']['num_cpus']
			self.disc_size = machine_config['host']['disk_size']
			self.memory = machine_config['host']['mem_size']
			if machine_config['os']['distribution'] == "Ubuntu":
				self.os_version = str(machine_config['os']['version'])
				for os_v in global_varialbles.OS_SERIES:
					if (self.os_version  in os_v) or (os_v in self.os_version):
						self.os_series = global_varialbles.OS_SERIES[os_v]
				if self.os_series == "":
					message = "The os version {} for the machine {} is not defined. Please define it in gv file in the variable OS_SERIES".format(
							self.os_version, machine_config['machine_name'])
					self.logger.critical(message)
					self.logger.info(message)
			self.ip = machine_config['ip_addresses']
			self.available = machine_config['machine_available']
			
		except ValueError as ex:
			raise ex
		
	def validate(self, cloud_name, model_name, machine_config):
		"""
		:param cloud_name:
		:param model_name:
		:param machine_config:
		:return:
		"""
		raise NotImplementedError()


class _PhysicalMachine():
	
	def __init__(self):
		self.logger = logging.getLogger('jox.VimDriver.PhysicalMachine')
		self.zone = None
		self.domain = list()  # a physical machine could be connected to different domains through two interfaces
		self.hostname = None
		self.dns_name = None
		# machine status
		self.alive = False
		self.connected = False
		
		self.available = True # to indicate whether the machine as a whole is reserved for certain application

		self.tmp_service_name = None
		self.tmp_mid_ro = None
		"""
		every address will have the following characteristics
		self.addresses[0] = {
				"value": "ip address"
				"type": "ipv4, ipv6"
				"scope": "private, public, local-machine"
				}
		"""
		self.addresses = list()
		self.ip = None
		self.interfaces = None
		
		""" total resources """
		self.host_cpu_tot = 0
		self.host_mem_tot = 0
		self.host_disc_size_tot = 0
		""" available resources """
		self.host_cpu_ava_percent = 0
		self.host_mem_ava = 0
		self.host_disc_size_ava= 0
		
		""" os characteristics """
		self.os_arch = "" # e.g. x86_64
		self.os_type = "" # e.g. linux
		self.os_dist = "" # e.g. Ubuntu
		self.os_version = "" # e.g. 16.04
		
		"""virtualization support"""
		self.virt_lxd = False
		self.virt_kvm = False
		
		self.tags = None
		
		self.list_lxd_machines = list()
		self.list_kvm_machines = list()
		
		self.subslice_name = list() # list of subslice srerved by the machine
		
		# credential of juju
		self.juju_cloud_name = ""
		self.juju_model_name = ""
		self.juju_endpoint = ""
		self.juju_user_passwd = dict()  # list of user names and password
		
		self.mid_user_defined = list()
		self.mid_vnfm = ""  # juju id of the machine in case of juju
		self.mid_vim = ""  # value assigned by LXD hypervisor
		self.mid_ro = ""  # name given by the resource controller

	def build(self,
			  subslice_name,
			  cloud_name,
			  model_name,
			  mid_ro,
			  machine_config):
		try:
			self.subslice_name.append(subslice_name)

			# credential of juju
			self.juju_cloud_name = cloud_name
			self.juju_model_name = model_name
			self.juju_endpoint = None

			self.mid_user_defined = machine_config['machine_name']
			self.mid_vim = ""  # value assigned by LXD hypervisor
			self.mid_ro = mid_ro  # name given by the resource controller

			self.cpu = machine_config['host']['num_cpus']
			self.disc_size = machine_config['host']['disk_size']
			self.memory = machine_config['host']['mem_size']
			if machine_config['os']['distribution'] == "Ubuntu":
				os_version = str(machine_config['os']['version'])
				try:
					self.os_series = global_varialbles.OS_SERIES[os_version]
				except:
					message = "The os version {} for the machine {} from the subslice {} is not defined. Please define it in gv file in the variable OS_SERIES".format(
						os_version, machine_config['machine_name'], subslice_name)
					self.logger.debug(message)
					self.logger.critical(message)
					self.logger.info(message)
		except Exception as ex:
			raise ex
	# def build_2(self,
	#           zone,
	#           domain,
	#           hostname,
	#           dns_name,
	#           status_alive,
	#           status_connected,
	#           set_addresses,
	#           cpu_tot,
	#           mem_tot,
	#           disc_size_tot,
	#           cpu_ava,
	#           mem_ava,
	#           disc_size_ava,
	#           os_arch,
	#           os_type,
	#           os_dist,
	#           os_version,
	#           lxd_support,
	#           kvm_support,
	#           tags
	#           ):
	# 	try:
	# 		self.zone = zone
	# 		self.domain = domain
	# 		self.hostname = hostname
	# 		self.dns_name = dns_name
	# 		self.dns_name = dns_name
	# 		self.alive = status_alive
	# 		self.connected = status_connected
	# 		self.addresses = set_addresses
	#
	# 		self.host_cpu_tot = cpu_tot
	# 		self.host_mem_tot = mem_tot
	# 		self.host_disc_size_tot = disc_size_tot
	#
	# 		self.host_cpu_ava_percent = cpu_ava
	# 		self.host_mem_ava = mem_ava
	# 		self.host_disc_size_ava = disc_size_ava
	#
	# 		self.os_arch = os_arch
	# 		self.os_type = os_type
	# 		self.os_dist = os_dist
	# 		self.os_version = os_version
	#
	# 		self.virt_lxd = lxd_support
	# 		self.virt_kvm = kvm_support
	#
	# 		# TODO to deal with tags here
	# 		self.tags = tags
	# 	except ValueError as ex:
	# 		raise ex

	def register(self,
				 cloud_name,
				 model_name,
				 mid_ro,
				 machine_config):
		try:
			# credential of juju
			self.juju_cloud_name = cloud_name
			self.juju_model_name = model_name
			self.juju_endpoint = None

			self.mid_user_defined = machine_config['machine_name']
			self.mid_vim = ""
			self.mid_vnfm = machine_config['juju_id']
			self.mid_ro = mid_ro  # name given by the resource controller

			self.cpu = machine_config['host']['num_cpus']
			self.disc_size = machine_config['host']['disk_size']
			self.memory = machine_config['host']['mem_size']
			if machine_config['os']['distribution'] == "Ubuntu":
				os_version = str(machine_config['os']['version'])
				for os_v in global_varialbles.OS_SERIES:
					if (os_version in os_v) or (os_v in os_version):
						self.os_series = global_varialbles.OS_SERIES[os_v]
				if self.os_series == "":
					message = "The os version {} for the machine {} is not defined. Please define it in gv file in the variable OS_SERIES".format(
						os_version, machine_config['machine_name'])
					self.logger.critical(message)
					self.logger.info(message)
			self.addresses = machine_config['ip_addresses']
			self.ip = machine_config['ip_addresses']
			self.available = machine_config['machine_available']
			self.domain = machine_config['domain']
			self.hostname = machine_config['domain']
			self.dns_name = machine_config['dns_name']
			self.interfaces = machine_config['interfaces']

			""" total resources """
			self.host_cpu_tot = machine_config['host']['cpu_number']
			self.host_mem_tot = machine_config['host']['mem_total']
			self.host_disc_size_tot = None
			""" available resources """
			self.host_cpu_ava_percent = machine_config['host']['cpu_percent']
			self.host_mem_ava = machine_config['host']['mem_free']
			self.host_disc_size_ava = None

		except ValueError as ex:
			raise ex

		
	def release(self, subslice, machine_user_defined_name):
		self.available = True
		self.subslice_name.remove(subslice)
		self.mid_user_defined.remove(machine_user_defined_name)
		
	def validate(self, cloud_name, model_name, machine_config):
		raise NotImplementedError()


async def run_command(*args):
	arguments = (args[1] if len(args) > 1 else args[0])
	process = await asyncio.create_subprocess_exec(
		*arguments,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT)
	stdout, stderr = await process.communicate()
	return (stdout.decode("utf-8")).strip()
async def machine_configuration_for_jujuCharm(ssh_user, machine_ip, ssh_key_private, logger):
	cmd_ssh_1 = ["ssh", "{}@{}".format(ssh_user, machine_ip), "echo", "export", "LC_CTYPE=en_US.UTF-8", ">>" "~.bashrc"]
	cmd_ssh_2 = ["ssh", "{}@{}".format(ssh_user, machine_ip), "echo", "export", "LC_ALL=en_US.UTF-8", ">>" "~.bashrc"]
	cmd_ssh_3 = ["ssh", "{}@{}".format(ssh_user, machine_ip), "source", ".bashrc"]

	cmd_ssh_4 = ["ssh", "{}@{}".format(ssh_user, machine_ip), "sudo", "apt-get", "update", "-y"]
	cmd_ssh_5 = ["ssh", "{}@{}".format(ssh_user, machine_ip), "sudo", "apt-get", "upgrade", "-y"]
	cmd_ssh_6 = ["ssh", "{}@{}".format(ssh_user, machine_ip), "sudo", "apt-get", "install",
				 "tmux",
				 "curl",
				 "bridge-utils",
				 "cloud-image-utils",
				 "cloud-utils",
				 "cpu-checker",
				 "distro-info",
				 "genisoimage",
				 "libaio1",
				 "libibverbs1",
				 "libnl-3-200",
				 "libnl-route-3-200",
				 "libnspr4",
				 "libnss3",
				 "librados2",
				 "librbd1",
				 "msr-tools",
				 "qemu-block-extra",
				 "qemu-utils",
				 "sharutils",
				 "ubuntu-fan",
				 "-y"]

	cmd_kvm_ssh_vm = ["ssh", "-o", "StrictHostKeyChecking={}".format("no"), "-i", ssh_key_private,
					  "{}@{}".format(ssh_user, machine_ip), "pwd"]

	cmd_kvm_ssh_vm_out = await run_command(cmd_kvm_ssh_vm)
	message = "ensuring ssh to the machine {}".format(machine_ip)
	logger.info(message)

	cmd_ssh_1_out = await run_command(cmd_ssh_1)
	message = "configure local {} to the machine {}".format(cmd_ssh_1[4], machine_ip)
	logger.info(message)

	cmd_ssh_2_out = await run_command(cmd_ssh_2)
	message = "configure local {} to the machine {}".format(cmd_ssh_2[4], machine_ip)
	logger.info(message)

	cmd_ssh_3_out = await run_command(cmd_ssh_3)

	cmd_ssh_4_out = await run_command(cmd_ssh_4)
	message = "doing sudo apt-get update to the machine {}".format(cmd_ssh_2[4], machine_ip)
	logger.info(message)

	cmd_ssh_5_out = await run_command(cmd_ssh_5)
	message = "doing sudo apt-get upgrade to the machine {}".format(cmd_ssh_2[4], machine_ip)
	logger.info(message)

	cmd_ssh_6_out = await run_command(cmd_ssh_6)
	message = "installing required packages for charms in the machine {}".format(cmd_ssh_2[4], machine_ip)
	logger.info(message)