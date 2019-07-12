import re
import json

class Client:
	def __init__(self, client_name, ip_address):
		self.client_name = client_name
		self.ip_address = ip_address
		self.kills = 0
		self.kills_by_type = {}
		self.killstreak = 0
		self.best_killstreak = 0
		self.deaths = 0
		self.deaths_by_type = {}
		self.oopsies = 0
		self.assists = 0
		self.base_defends = 0
		self.flag_defends = 0
		self.flag_grabs = 0
		self.flag_captures = 0
		self.flag_carry_time = 0
		self.current_class = None
		self.aliases = [client_name]
		self.playing_timestamp = None
		self.playing_total = 0
		self.flag_grab_timestamp = None
		self.flag_color = None
		self.class_playing_timestamp = None
		self.class_playing_total = {}

	def increment_dict(self, dict_collection, key, increment = 1):
		if key not in dict_collection:
			dict_collection[key] = 0
		dict_collection[key] += increment

	def change_name(self, client_name):
		if client_name not in self.aliases:
			self.aliases.append(client_name)
		self.client_name = client_name

	def change_class(self, timestamp, class_name):
		if self.current_class != class_name:
			self.end_current_class(timestamp)

		if class_name is not None:
			self.current_class = class_name
			self.class_playing_timestamp = timestamp

	def end_current_class(self, timestamp):
		if self.current_class is None:
			return
		if timestamp > self.class_playing_timestamp:
			current_played_time = (timestamp - self.class_playing_timestamp)
			self.increment_dict(self.class_playing_total, self.current_class, current_played_time)
			self.playing_total += current_played_time
		self.current_class = None
		self.class_playing_timestamp = None

	def end_match(self, timestamp):
		self.flagless_state(timestamp)
		self.killstreak_ender(timestamp)
		self.end_current_class(timestamp)

	def disconnected(self, timestamp):
		self.end_match(timestamp)

	def flagless_state(self, timestamp):
		if self.flag_grab_timestamp is None:
			return
		if timestamp > self.flag_grab_timestamp:
			self.flag_carry_time += (timestamp - self.flag_grab_timestamp)
		self.flag_grab_timestamp = None
		self.flag_color = None

	def killstreak_ender(self, timestamp):
		if self.killstreak > self.best_killstreak:
			self.best_killstreak = self.killstreak
		self.killstreak = 0

	def frag(self, timestamp, kill_type):
		self.increment_dict(self.kills_by_type, kill_type)
		self.kills += 1
		self.killstreak += 1

	def intentional_death(self, timestamp):
		self.flagless_state(timestamp)

	def death(self, timestamp, kill_type, self_inflicted):
		self.flagless_state(timestamp)
		self.killstreak_ender(timestamp)
		self.deaths += 1
		self.increment_dict(self.deaths_by_type, kill_type)
		if self_inflicted:
			self.oopsies += 1

	def defend_base(self, timestamp):
		self.base_defends += 1

	def defend_flag(self, timestamp):
		self.flag_defends += 1

	def flag_grab(self, timestamp, flag_color):
		self.flag_grabs += 1
		self.flag_grab_timestamp = timestamp
		self.flag_color = flag_color

	def flag_assist(self, timestamp):
		self.assists += 1

	def flag_capture(self, timestamp):
		self.flagless_state(timestamp)
		self.flag_captures += 1

	def convert_to_data(self):
		return {
			'lastClientName': self.client_name,
			'aliases': [a for a in self.aliases if a != "UnnamedPlayer"],
			'lastIpAddress': self.ip_address,
			'kills': self.kills,
			'killstreak': self.best_killstreak,
			'killsByType': self.kills_by_type,
			'deaths': self.deaths,
			'deathsByType': self.deaths_by_type,
			'oopsies': self.oopsies,
			'assists': self.assists,
			'baseDefends': self.base_defends,
			'flagDefends': self.flag_defends,
			'flagGrabs': self.flag_grabs,
			'flagCaptures': self.flag_captures,
			'flagCarryTime': self.flag_carry_time,
			'playedTime': self.playing_total,
			'playedTimeByClass': self.class_playing_total
		}

class LogParser:
	def __init__(self):
		self.standard_message_expression = re.compile("\s*(?P<timestamp_minutes>\d+):(?P<timestamp_seconds>\d{2}) (?P<message>.*)\s*")
		self.init_game_regex = re.compile("InitGame:.*")
		self.client_connected_regex = re.compile("ClientConnect: (?P<client_number>\d+), Name: (?P<client_name>.*), Ip: (?P<ip_address>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d{1,5} DATE:.*")
		self.client_changed_regex = re.compile("ClientUserinfoChanged: (?P<client_number>\d+) n\\\\(?P<client_name>.*)\\\\t\\\\\d+\\\\.*(?P<team>blue|red)(?P<class>\w+)\\\\hmodel\\\\.*\\\\wfc\\\\(?P<wfc>\d+)")
		self.client_disconnected_regex = re.compile("ClientDisconnect: (?P<client_number>\d+)")
		self.kill_regex = re.compile("Kill: (?P<killer_number>\d+) (?P<victim_number>\d+) (?P<kill_type>\d+): (?P<killer_name>.*) killed (?P<victim_name>.*) by (?P<kill_type_name>.*)")
		self.defend_base_regex = re.compile("(?P<client_name>.*) defends the (?P<flag_color>RED|BLUE) base!")
		self.defend_flag_regex = re.compile("(?P<client_name>.*) defends the (?P<flag_color>RED|BLUE) flag!")
		self.grab_flag_regex = re.compile("(?P<client_name>.*) got the (?P<flag_color>RED|BLUE) flag!")
		self.assist_carrier_regex = re.compile("(?P<client_name>.*) defends a (?P<flag_color>RED|BLUE) carrier from an agressive enemy!")
		self.capture_flag_regex = re.compile("(?P<client_name>.*) captured the (?P<flag_color>RED|BLUE) flag!")

		self.intentional_death_types = ['MOD_SUICIDE', 'MOD_KAMIKAZE']

		self.unique_clients = []
		self.clients_by_name = {}
		self.clients_by_number = {}
		self.clients_by_ip = {}

	def check_regex(self, timestamp, message, expression, handler):
		match_result = expression.match(message)
		if match_result:
			handler(timestamp, match_result)
			return True
		else:
			return False

	def init_game(self, timestamp, match_result):
		for client in self.unique_clients:
			client.end_match(timestamp)
		self.clients_by_number = {}

	def client_connected(self, timestamp, match_result):
		client_number = match_result.group('client_number')
		client_name = match_result.group('client_name')
		ip_address = match_result.group('ip_address')
		client = None
		if client_name != 'UnnamedPlayer' and client_name in self.clients_by_name:
			client = self.clients_by_name[client_name]
		elif ip_address in self.clients_by_ip:
			client = self.clients_by_ip[ip_address]
		else:
			client = Client(client_name, ip_address)
			self.unique_clients.append(client)
		
		client.ip_address = ip_address
		client.change_name(client_name)
		self.clients_by_ip[ip_address] = client
		self.clients_by_number[client_number] = client
		self.clients_by_name[client.client_name] = client

	def client_changed(self, timestamp, match_result):
		client_number = match_result.group('client_number')
		client_name = match_result.group('client_name')
		if client_number not in self.clients_by_number:
			return
		client = self.clients_by_number[client_number]
		if client.client_name != client_name:
			client.change_name(client_name)
			self.clients_by_name[client.client_name] = client

		#I think this is a class index? non-zero seems to be a currently playing class
		wfc = match_result.group('wfc')
		current_class = None
		if wfc != '0':
			current_class = match_result.group('class')

		#this might pass None for someone not currently playing a class
		client.change_class(timestamp, current_class)

	def client_disconnected(self, timestamp, match_result):
		client_number = match_result.group('client_number')
		if client_number not in self.clients_by_number:
			return
		client = self.clients_by_number[client_number]
		client.disconnected(timestamp)
		del self.clients_by_number[client_number]

	def kill(self, timestamp, match_result):
		killer_number = match_result.group('killer_number')
		victim_number = match_result.group('victim_number')
		kill_type_name = match_result.group('kill_type_name')
		if killer_number == victim_number:
			if killer_number in self.clients_by_number:
				if kill_type_name in self.intentional_death_types:
					self.clients_by_number[killer_number].intentional_death(timestamp)
				else:
					#that's an oopsie
					self.clients_by_number[killer_number].death(timestamp, kill_type_name, True)
		else:
			if killer_number in self.clients_by_number:
				self.clients_by_number[killer_number].frag(timestamp, kill_type_name)
			if victim_number in self.clients_by_number:
				self.clients_by_number[victim_number].death(timestamp, kill_type_name, False)

	def defend_base(self, timestamp, match_result):
		client_name = match_result.group('client_name')
		if client_name not in self.clients_by_name:
			return
		self.clients_by_name[client_name].defend_base(timestamp)

	def defend_flag(self, timestamp, match_result):
		client_name = match_result.group('client_name')
		if client_name not in self.clients_by_name:
			return
		self.clients_by_name[client_name].defend_flag(timestamp)

	def grab_flag(self, timestamp, match_result):
		client_name = match_result.group('client_name')
		flag_color = match_result.group('flag_color')
		if client_name not in self.clients_by_name:
			return
		self.clients_by_name[client_name].flag_grab(timestamp, flag_color)

	def assist_carrier(self, timestamp, match_result):
		client_name = match_result.group('client_name')
		if client_name not in self.clients_by_name:
			return
		self.clients_by_name[client_name].flag_assist(timestamp)

	def capture_flag(self, timestamp, match_result):
		client_name = match_result.group('client_name')
		if client_name not in self.clients_by_name:
			return
		self.clients_by_name[client_name].flag_capture(timestamp)

	def parse(self, log_file):
		handlers = [
			(self.init_game_regex, self.init_game),
			(self.client_connected_regex, self.client_connected),
			(self.client_changed_regex, self.client_changed),
			(self.client_disconnected_regex, self.client_disconnected),
			(self.kill_regex, self.kill),
			(self.defend_base_regex, self.defend_base),
			(self.defend_flag_regex, self.defend_flag),
			(self.grab_flag_regex, self.grab_flag),
			(self.assist_carrier_regex, self.assist_carrier),
			(self.capture_flag_regex, self.capture_flag)
		]

		timestamp = 0
		with open(log_file, 'r') as f:
			for line in f:
				line_match = self.standard_message_expression.match(line)
				if line_match:
					timestamp = int(line_match.group('timestamp_minutes')) * 60 + int(line_match.group('timestamp_seconds'))
					message = line_match.group('message')
					for (expression, handler) in handlers:
						if self.check_regex(timestamp, message, expression, handler):
							break;

		if timestamp > 0:
			for client in self.unique_clients:
				client.end_match(timestamp)

	def export_json(self, json_file):
		client_data = [client.convert_to_data() for client in self.unique_clients]
		with open(json_file, 'w') as f:
			json.dump(client_data, f, indent=4, sort_keys=True)

if __name__ == '__main__':
	parser = LogParser()
	parser.parse("games.log")
	parser.export_json("results.json")