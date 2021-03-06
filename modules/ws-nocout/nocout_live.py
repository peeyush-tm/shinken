'''
nocout_live.py
===================

Module to fetch current data for a list of services running
on a set of devices
'''

from ast import literal_eval
import memcache
from multiprocessing import Process, Queue
import re
import subprocess

from shinken.log import logger

# TODO: Get check mk related vars properly
check_mk_bin = '/omd/dev_slave/slave_2/bin/cmk'


def main(**kw):
	"""
	Entry point for all the functions

	Returns:
		{
	 "success": 1,
	 "message": "Data fetched successfully",
	 "error_message": None,
	 "value": [] # The current values for the desired service data sources
	}
	"""
	logger.warning('kw: {0}'.format(kw))
	response = {
			"success": 1,
			"message": "Data fetched successfully",
			"error_message": None,
			"value": []
			}
	action = 'live'
	if action == 'live':
		response['value'] = poll_device(
				device_list=kw.get('device_list'),
				service_list=kw.get('service_list'),
				bs_name_ss_mac_mapping=kw.get('bs_name_ss_mac_mapping'),
				ss_name_mac_mapping=kw.get('ss_name_mac_mapping'),
				ds=kw.get('ds'),
				)
	else:
		response.update({
			"message": "No data",
			"error_message": "No action defined for this case"
			})

	return response


def poll_device(**kw):
	response = []
	try:
		logger.info('[Polling Iteration Start]')
		device_list = kw.get('device_list')
		service_list = kw.get('service_list')
		bs_name_ss_mac_mapping = kw.get('bs_name_ss_mac_mapping')
		ss_name_mac_mapping = kw.get('ss_name_mac_mapping')
	except Exception as exc:
		logger.error('Problem with request params: {0}'.format(exc))
	logger.info('device_list: {0}'.format(device_list))
	logger.info('service_list: {0}'.format(service_list))
	try:
		data_source_list = kw.get('ds')
	except Exception as exc:
		data_source_list = ['']
		logger.error('No ds in req obj: {0}'.format(exc))
	if not data_source_list:
		data_source_list = ['']

	q = Queue()
	jobs = [
			Process(
				target=get_current_value,
				args=(q,),
				kwargs=
				{
					'device': device,
					'service_list': service_list,
					'data_source_list': data_source_list,
					'bs_name_ss_mac_mapping': bs_name_ss_mac_mapping,
					'ss_name_mac_mapping': ss_name_mac_mapping
					}
				) for device in device_list
			]
	for j in jobs:
		j.start()
	for k in jobs:
		k.join()

	##logger.debug('Queue ' + pformat(q.qsize()))
	while True:
		if not q.empty():
			response.append(q.get())
		else:
			break
	logger.info('[Polling Iteration End]')

	return response


def get_current_value(
		q,
		device=None,
		service_list=None,
		data_source_list=None,
		bs_name_ss_mac_mapping=None,
		ss_name_mac_mapping=None
		):
	""" Function to perform live polling for device(s)"""
	interface_services = [
			'cambium_ul_rssi',
			'cambium_ul_jitter',
			'cambium_reg_count',
			'cambium_ul_jitter',
			'cambium_rereg_count',
			'cambium_ss_connected_bs_ip_invent'
			]

	wimax_ss_port_service = [
	 		'wimax_ss_speed_status',
	 		'wimax_ss_autonegotiation_status',
	 		'wimax_ss_duplex_status',
	 		'wimax_ss_uptime',
	 		'wimax_dl_modulation_change_invent',
	 		'wimax_ss_link_status'
	 		]
	wimax_services = [
			'wimax_dl_rssi',
			'wimax_ul_rssi',
			'wimax_dl_cinr',
			'wimax_ul_cinr',
			'wimax_dl_intrf',
			'wimax_ul_intrf',
			'wimax_modulation_dl_fec',
			'wimax_modulation_ul_fec'
			]
	cambium_services = [
			'cambium_ul_rssi',
			'cambium_ul_jitter',
			'cambium_reg_count',
			'cambium_rereg_count'
			]
	rad5k_services = [
			'rad5k_ul_rssi' ,
			'rad5k_dl_rssi',
			'rad5k_ss_dl_utilization' ,
			'rad5k_ss_ul_utilization',
			'rad5k_dl_time_slot_alloted_invent',
			'rad5k_ul_time_slot_alloted_invent',
			'rad5k_dl_estmd_throughput_invent',
			'rad5k_ul_estmd_throughput_invent',
			'rad5k_ul_uas_invent',
			'rad5k_dl_es_invent',
			'rad5k_ul_ses_invent',
			'rad5k_ul_bbe_invent',
			'rad5k_ss_cell_radius_invent',
			'rad5k_ss_cmd_rx_pwr_invent'
			]

	ss_device, ss_mac, bs_device = None, None, None
	old_device = device
	filtered_ss_data = []
	ss_host_name = None
	ss_mac_list, bs_device_list = [], []

	# Data sources for ping service
	pl, rta = None, None
	ip = None

	for service in service_list:
		device = old_device
		old_service = service
		if service in wimax_services:
			old_service = service
			service = 'wimax_topology'
		if service in interface_services:
			old_service = service
			service = 'cambium_topology_discover'
		if service in wimax_ss_port_service:
			old_service = service
			service = 'wimax_ss_port_params'
		if service in rad5k_services:
			old_service = service
			service = 'rad5k_topology_discover'
		# Getting result from compiled checks output
		cmd = '%s -nvp --checks=%s %s' % (check_mk_bin, service, device)
		# For host check [ping service]
		if service.lower() == 'ping':
			# Get the device ip from device name
			 try:
			 	 memc = memcache.Client(['10.133.19.165:11211'])
			 	 ip = memc.get(device)
			 except Exception, e:
			 	 logger.info('Error in getting ip from : ')
			 cmd = 'ping -w 2 -c 1 %s' % ip
		logger.info('cmd: {0}'.format(cmd))
		#start = datetime.daetime.now()
		# Fork a subprocess
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
		check_output, error = p.communicate()
		logger.warning('Check_output: {0}, error: {1}'.format(check_output, error))
		if check_output:
			if old_service in interface_services:
			    data_value = []
			    try:
				check_output = filter(
						lambda t: 'cambium_topology_discover' in t, check_output.split('\n')
						)
				check_output = check_output[0].split('- ')[1].split(' ')

				for ss_mac_entry in bs_name_ss_mac_mapping.get(device):
					filtered_ss_output = filter(
							lambda t:  ss_mac_entry.lower() in t, check_output
							)
					filtered_ss_data.extend(filtered_ss_output)

				logger.info('filtered_ss_data: {0}'.format(filtered_ss_data))
				index = cambium_services.index(old_service)

				for entry in filtered_ss_data:
					data_value = entry.split('/')[index+2]
					cal_ss_mac = entry.split('/')[1]
					for host_name,mac_value in ss_name_mac_mapping.items():
						if mac_value ==  cal_ss_mac.lower():
							ss_host_name = host_name
							break
					data_dict = {ss_host_name:data_value}
					q.put(data_dict)

			    except Exception, e:
			 	logger.error('Empty check_output: {0}'.format(e))

				for host_name,mac_value in ss_name_mac_mapping.items():
					ss_host_name = host_name
					data_dict = {ss_host_name: []}
			 		q.put(data_dict)
			 		return

			elif str(old_service) in wimax_services:
				filtered_ss_data =[]
				try:
					data_value = []	
					check_output = filter(
							lambda t: 'wimax_topology' in t, check_output.split('\n')
							)
					check_output = check_output[0].split('- ')[1].split(' ')
					#logger.debug('Final check_output : ' + pformat(check_output))

					for ss_mac_entry in bs_name_ss_mac_mapping.get(device):
						filtered_ss_output = filter(
								lambda t:  ss_mac_entry.lower() in t,check_output
								)
						filtered_ss_data.extend(filtered_ss_output)

					index = wimax_services.index(old_service)
					#logger.debug('filterred_ss_data: ' + pformat(filtered_ss_data))

					for entry in filtered_ss_data:
						value = entry.split('=')[1].split(',')[index]
						data_value.append(value)
						cal_ss_mac = entry.split('=')[0]
						for host_name,mac_value in ss_name_mac_mapping.items():
							if mac_value ==  cal_ss_mac.lower():
								ss_host_name = host_name
								break
						data_dict = {ss_host_name:data_value}
						data_value = []
						q.put(data_dict)

					logger.error(filtered_ss_data)
				except Exception as exc:
					logger.error('Empty check_output: {0}'.format(exc))
					for host_name,mac_value in ss_name_mac_mapping.items():
						data_dict = {host_name:[]}
						q.put(data_dict)
					return
			elif str(old_service) in wimax_ss_port_service:
				try:
					data_value =  []
					check_output =  filter(
							lambda t: 'wimax_ss_port_params' in t, check_output.split('\n')
							)
					check_output = check_output[0].split('- ')[1].split(',')
					index =  wimax_ss_port_service.index(old_service)
					value = check_output[index].split('=')[1]
					data_value.append(value)
					data_dict = {old_device:data_value}
					data_value = []
					q.put(data_dict)
				except Exception as exc:
					logger.error('Empty check_output: {0}'.format(exc))
					data_dict = {old_device: []}
					data_value = []
					q.put(data_dict)
					return	
			elif str(old_service) in rad5k_services:
				data_value = []
				try:
					check_output = filter(
							lambda t: 'rad5k_topology_discover' in t, check_output.split('\n')
							)
					check_output = check_output[0].split('- ')[1].split(' ')
					for ss_mac_entry in bs_name_ss_mac_mapping.get(device):
						filtered_ss_output = filter(
								lambda t:  ss_mac_entry.lower() in t, check_output
								)
						filtered_ss_data.extend(filtered_ss_output)
					logger.info('filtered_ss_data: {0}'.format(filtered_ss_data))
					index = rad5k_services.index(old_service)
					for entry in filtered_ss_data:
						data_entry = entry.split('=')[1]
						data_value = data_entry.split('/')[index]
						cal_ss_ip = data_entry.split('/')[-1]
						for host_name,ss_ip_value in ss_name_mac_mapping.items():
							if ss_ip_value ==  cal_ss_ip:
								ss_host_name = host_name
								break
						data_dict = {ss_host_name:data_value}
						q.put(data_dict)
				except Exception, e:
					logger.error('Empty check_output: {0}'.format(e))
					for host_name,mac_value in ss_name_mac_mapping.items():
						ss_host_name = host_name
						data_dict = {ss_host_name: []}
						q.put(data_dict)
						return
			elif old_service.lower() == 'ping':
				check_output = check_output.split('\n')[-3:]
				logger.debug('check_output after split: {0}'.format(check_output))
				pl_info, rta_info = check_output[0], check_output[1]
				if pl_info:
					pl = pl_info.split(',')[-2].split()[0]
					pl = pl.strip('%')
				if rta_info:
					rta = rta_info.split('=')[1].split('/')[1]
					rta = rta.strip('ms')
				if 'pl' in data_source_list:
					data_dict = {device: [pl]}
				if 'rta' in data_source_list:
					data_dict = {device: [rta]}
				q.put(data_dict)
				return
			else:
				reg_exp1 = re.compile(r'(?<=\()[^)]*(?=\)$)', re.MULTILINE)
				# Parse perfdata for all services running on that device
				ds_current_states = re.findall(reg_exp1, check_output)
				logger.info('ds_current_states : %s' % ds_current_states)
				# Placing all the ds values into one single list
				if ds_current_states:
					ds_values = ds_current_states[0].split(' ')
					logger.info('ds_values : %s' % ds_values)

					for ds in data_source_list:
						# Parse the output to get current value for that data source
						desired_ds = filter(lambda x: ds in x.split('=')[0], ds_values)
						logger.debug('desired_ds : %s' % desired_ds)
						data_values = (map(lambda x: x.split('=')[1].split(';')[0], desired_ds))
						#logger.debug('data_values:' + pformat(data_values))
						data_dict = {old_device: data_values}
						q.put(data_dict)

				else:
					data_dict = {old_device: []}
					q.put(data_dict)
