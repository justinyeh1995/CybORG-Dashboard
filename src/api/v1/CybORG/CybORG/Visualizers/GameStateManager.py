import subprocess
import inspect
import time
import os
from copy import deepcopy
from statistics import mean, stdev
import random
import collections
import networkx as nx

from pprint import pprint
from enum import Enum
from CybORG.Agents.Wrappers.TrueTableWrapper import true_obs_to_table

class GameStateManager:
    def __init__(self):
        self.blue_agent_type = None
        self.red_agent_type = None
        self.cyborg = None
        self.num_steps = None
        self.ip_map = None
        self.host_map = None
        self.true_state = None
        self.true_table = None
        self.game_states = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(dict)))
        
        self.compromised_hosts = set(['User0'])
        self.exploited_hosts = set()
        self.escalated_hosts = set(['User0'])
        self.discovered_subnets = set()
        self.discovered_systems = set()

    def set_environment(self, cyborg=None, red_agent_type=None, blue_agent_type=None, num_steps=30):
        self.cyborg = cyborg
        self.blue_agent_type = blue_agent_type
        self.red_agent_type = red_agent_type
        self.num_steps= num_steps
        self._create_ip_host_maps()
        
    def _create_ip_host_maps(self):
        self.ip_map = self.cyborg.get_ip_map()
        self.cidr_map = {lan_name: str(ip) for lan_name, ip in self.cyborg.get_cidr_map().items()}
        self.cidr_to_host_map = {str(ip): lan_name for lan_name, ip in self.cyborg.get_cidr_map().items()}
        self.cyborg_ip_to_host_map = {str(ip): host for host, ip in self.ip_map.items()}
        self.cyborg_host_to_ip_map = {host: str(ip) for host, ip in self.ip_map.items()}
        self.host_map = {host: str(ip) for ip, host in self.ip_map.items()}

    def _get_true_state(self):
        return deepcopy(self.cyborg.get_agent_state('True'))

    def _get_true_state_table(self):
        self.true_state = self._get_true_state()
        return true_obs_to_table(self.true_state, self.cyborg)

    def _get_host_info(self, node):
        # if '_router' in node:
        #     return ""

        # hover_text = ""

        # true_obs = self._get_true_state()
        # node_info = true_obs[node]

        # hover_text += "System info:<br>"
        # system_info = node_info.get('System info', {})
        # os_info = f"{system_info.get('OSType', '').name} " \
        #   f"{system_info.get('OSDistribution', '').name} " \
        #   f"({system_info.get('Architecture', '').name})"

        # hover_text += os_info + "<br><br>"

        # hover_text += "Processes info:<br>"
        
        # processes = node_info.get('Processes', [])
        # for proc in processes:
        #     process_name = proc.get('Process Name', 'N/A')
        #     pid = proc.get('PID', 'N/A')
        #     username = proc.get('Username', 'N/A')
        #     port_info = ', '.join([f"Port: {conn['local_port']}" for conn in proc.get('Connections', [])])
        #     hover_text+=f"- {process_name} (PID: {pid}, User: {username}, {port_info})<br>"
        
        if '_router' in node:
            subnet = node.split("_")[0]
            return f"Subnet: {self.cidr_map[subnet]}"

        hover_text = f"IP Address: {self.cyborg_host_to_ip_map[node]}"

        return hover_text
        
    
    def _get_node_color(self, node):
        color = "green"
        
        if 'router' in node:
            if node in self.discovered_subnets:
                color = 'rosybrown'
        
        if node in self.discovered_systems:
            color = "pink"
        
        if node in self.escalated_hosts:
            color = "red"
            
        elif node in self.exploited_hosts:
            color = "orange"
        
        return color

    def _get_node_border(self, node, target_host=None, reset_host=None):
        if target_host and node in target_host:
            border = dict(width=2, color='black')
        elif reset_host and node in reset_host:
            border = dict(width=2, color='black')
        else:
            border = dict(width=0, color='white')
        return border
        
    def _parse_action(self, cyborg, action_str, agent, host_map, ip_map):
        action_type = action_str.split(" ")[0]
        target_host = ""
        if cyborg.get_observation(agent)['success'].__str__() == 'TRUE':
            action_str_split = action_str.split(" ")
            n = len(action_str_split)
            target_host = action_str_split[-1] if n > 1 else target_host
            # Update target host if it's an IP address to get the hostname
            print(target_host)
            if target_host in ip_map:
                target_host = ip_map.get(target_host, target_host) 
            elif target_host in self.cidr_to_host_map:
                target_host = self.cidr_to_host_map.get(target_host, target_host) 
        return target_host, action_type

    def _update_host_status(self, cyborg, action_str, host_map, ip_map, host_type='Red'):
        target_host, discovered_subnet, discovered_system, exploited_host, escalated_host = None, None, None, None, None
        reset_host, remove_host, restore_host = None, None, None

        if host_type == 'Red':
            # Check Red's actions
            target_host, action_type = self._parse_action(cyborg, action_str, 'Red', host_map, ip_map)
            if target_host:
                if 'ExploitRemote' in action_type:
                    exploited_host = target_host
                elif 'PrivilegeEscalate' in action_type or 'Impact' in action_type:
                    escalated_host = target_host
                elif 'DiscoverRemoteSystems' in action_type:
                    #@ To-Do code smells
                    _cidr = ".".join(target_host.split(".")[:3])
                    for ip in ip_map:
                        if _cidr in ip and 'router' in self.cyborg_ip_to_host_map[ip]:
                            discovered_subnet = self.cyborg_ip_to_host_map[ip]
                            target_host = discovered_subnet
                elif 'DiscoverNetworkServices' in action_type:
                    discovered_system = target_host
                    
        elif host_type == 'Blue':
            # Check Blue's actions
            reset_host, action_type = self._parse_action(cyborg, action_str, 'Blue', host_map, ip_map)
            if reset_host:
                if 'Remove' in action_type:
                    remove_host = reset_host
                elif 'Restore' in action_type:
                    restore_host = reset_host
        
        if discovered_subnet:
            self.discovered_subnets.add(discovered_subnet)

        if discovered_system:
            self.discovered_systems.add(discovered_system)
        
        if exploited_host:
            self.exploited_hosts.add(exploited_host)
            self.compromised_hosts.add(exploited_host)
        if remove_host:
            self.exploited_hosts.discard(remove_host)
            self.compromised_hosts.discard(remove_host)
        if escalated_host:
            self.escalated_hosts.add(escalated_host)
            self.compromised_hosts.add(escalated_host)
        if restore_host:
            self.escalated_hosts.discard(restore_host)
            self.compromised_hosts.discard(restore_host)
            
        return target_host, reset_host, discovered_subnet, discovered_system, exploited_host, escalated_host, remove_host, restore_host

    def _create_action_snapshot(self, action_str, host_type):
        link_diagram = self.cyborg.environment_controller.state.link_diagram

        target_host, action_type = self._parse_action(self.cyborg, action_str, host_type, self.host_map, self.ip_map)
        # @To-Do: handles string in a very ad-hoc manner 
        if action_type == "Monitor":
            target_host = "the whole network"
            
        decription = f"At Host User0 do {action_type} on {target_host}" if host_type == "Red" else f"At Host Defender do {action_type} on {target_host}"
        action_info = {
            "action": decription, 
            "success": self.cyborg.get_observation(host_type)['success'].__str__()
        }
        
        (
            target_host,
            reset_host,
            discovered_subnet, 
            discovered_system,
            exploited_host,
            escalated_host,
            remove_host,
            restore_host
        ) = self._update_host_status(
            self.cyborg,
            action_str,
            self.host_map,
            self.ip_map,
            host_type=host_type
        )

        node_colors = [self._get_node_color(node) for node in link_diagram.nodes]
        
        node_borders = [self._get_node_border(node, 
                                        target_host=target_host, 
                                        reset_host=reset_host) 
                        for node in link_diagram.nodes]

        host_info = [self._get_host_info(node) for node in link_diagram.nodes]

        compromised_hosts = self.compromised_hosts.copy()

        self.true_table = self._get_true_state_table()

        positions = nx.spring_layout(link_diagram, dim=3, seed=3113794652)
        node_positions = [
            {'id': str(node), 'x': float(pos[0]), 'y': float(pos[1]), 'z': float(pos[2])}
            for node, pos in positions.items()
        ]
        
        action_snapshot = {
            # Populate with necessary state information
            'link_diagram': nx.node_link_data(link_diagram),  # Assuming link_diagram is a NetworkX graph
            'node_positions': node_positions,
            'node_colors': node_colors,
            'node_borders': node_borders,
            'compromised_hosts': list(compromised_hosts),
            'host_info': host_info,
            'action_info': action_info,
            'host_map': self.host_map,
        }

        return action_snapshot
        
    def create_state_snapshot(self):
        # ... Logic to create and return a snapshot of the current game state ...
        ############
        ## fo viz ##
        ############
        state_snapshot = {}
                    
        for type in ['Blue', 'Red']:
            action_str = self.cyborg.get_last_action(type).__str__()
            state_snapshot[type] = self._create_action_snapshot(action_str, type)

        #elif self.environment == 'emu':
            
        return state_snapshot

    def reset(self):
        self.compromised_hosts = set(['User0'])
        self.exploited_hosts = set()
        self.escalated_hosts = set(['User0'])
        self.discovered_subnets = set()
        self.discovered_systems = set()
        self._create_ip_host_maps()

    def store_state(self, state_snapshot, episode, step):
        self.game_states[self.num_steps][self.red_agent_type][episode][step] = state_snapshot.copy()

    def get_game_state(self):
        return self.game_states
