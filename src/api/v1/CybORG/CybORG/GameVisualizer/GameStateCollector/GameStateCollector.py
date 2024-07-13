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

from CybORG.GameVisualizer.GameStateCollector.utils import get_host_info, get_node_color, get_node_border

class RewardTracker:
    def __init__(self):
        self.rewards = None
    def __repr__(self):
        return str({agent: dict(rewards) for agent, rewards in self.rewards.items()})
    
class GameStateCollector:
    def __init__(self, environment='sim'):
        self.environment = environment
        self.blue_agent_name: str = ""
        self.red_agent_name: str = ""
        self.cyborg = None
        self.num_steps = None
        self.ip_map = None
        self.host_map = None
        self.true_state = None
        self.true_table = None
        self.accumulated_rewards = collections.defaultdict(lambda: collections.defaultdict(float))
        self.game_states = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(dict)))
        
        self.compromised_hosts = set(['User0'])
        self.exploited_hosts = set()
        self.escalated_hosts = set(['User0'])
        self.discovered_subnets = set()
        self.discovered_systems = set()

    def set_environment(self, cyborg=None, red_agent_name=None, blue_agent_name=None, num_steps=30):
        self.cyborg = cyborg
        self.blue_agent_name = blue_agent_name
        self.red_agent_name = red_agent_name
        self.num_steps= num_steps
        self._create_ip_host_maps()
        
    def _create_ip_host_maps(self):
        self.ip_map = dict(map(lambda item: (str(item[0]), item[1]), self.cyborg.environment_controller.state.ip_addresses.items()))
        self.host_map = {host: str(ip) for ip, host in self.ip_map.items()}
        self.cidr_map = {lan_name: str(ip) for lan_name, ip in self.cyborg.get_cidr_map().items()}
        self.cidr_to_host_map = {str(ip): lan_name for lan_name, ip in self.cyborg.get_cidr_map().items()}
        self.cyborg_ip_to_host_map = {str(ip): host for host, ip in self.cyborg.get_ip_map().items()}
        self.cyborg_host_to_ip_map = {host: str(ip) for host, ip in self.cyborg.get_ip_map().items()}

    def _get_true_state(self):
        return deepcopy(self.cyborg.get_agent_state('True'))

    def _get_last_reward(self, agent_type):
        return self.cyborg.get_rewards()[agent_type]

    def _update_rewards(self, agent_type, reward):
        for metric, value in reward.items():
            self.accumulated_rewards[agent_type][metric] += value

    def _get_agent_rewards(self, agent_type):
        return {metric: value for metric, value in self.accumulated_rewards[agent_type].items()}

    def get_rewards(self):
        return {agent: dict(rewards) for agent, rewards in self.accumulated_rewards.items()}

    def create_state_snapshot(self, actions:dict, observations:dict):
        ############
        ## fo viz ##
        ############

        state_snapshot = {}
        
        for host_type in ['Blue', 'Red']:
            action = actions[host_type]
            observation = observations[host_type]
            
            state_snapshot[host_type] = self.generate_state_snapshot(action, observation, host_type)
                
        return state_snapshot   

    def generate_state_snapshot(self, action, observation, host_type: str):
        target_host, action_type, isSuccess = self.parse_observation(action, observation, self.host_map, self.ip_map)
        true_obs = self._get_true_state() | {}
        
        link_diagram = self.cyborg.environment_controller.state.link_diagram
        
        # @To-Do: handles string in a very ad-hoc manner 
        if action_type == "Monitor":
            target_host = "the whole network"

        if action_type == "Monitor":
            target_host = "the whole network"
            
        decription = f"at Host User0 do {action_type} on {target_host}" if host_type == "Red" else f"at Host Defender do {action_type} on {target_host}"
        action_info = {
            "action": decription, 
            "success": isSuccess
        }
        
        (
            target_host,
            discovered_subnet, 
            discovered_system,
            exploited_host,
            escalated_host,
            remove_host,
            restore_host
        ) = self.update_hosts(target_host, action_type, self.host_map, self.ip_map, host_type)
        
        node_colors = [get_node_color(node, 
                                      self.discovered_subnets, 
                                      self.discovered_systems, 
                                      self.escalated_hosts, 
                                      self.exploited_hosts) for node in link_diagram.nodes]
        
        node_borders = [get_node_border(node, target_host=target_host) for node in link_diagram.nodes]

        host_info = [get_host_info(node, true_obs) for node in link_diagram.nodes]

        compromised_hosts = self.compromised_hosts.copy()

        reward = self._get_last_reward(host_type)

        self._update_rewards(host_type, reward)

        accu_reward = self._get_agent_rewards(host_type)
        # print(self.accumulated_rewards)

        positions = nx.spring_layout(link_diagram, dim=3, seed=3113794652)
        node_positions = [
            {'id': str(node), 'x': float(pos[0]), 'y': float(pos[1]), 'z': float(pos[2])}
            for node, pos in positions.items()
        ]
        
        # action_snapshot = {
        #     # Populate with necessary state information
        #     'link_diagram': nx.node_link_data(link_diagram),
        #     'node_positions': node_positions,
        #     'node_colors': node_colors,
        #     'node_borders': node_borders,
        #     'compromised_hosts': compromised_hosts,
        #     'host_info': host_info,
        #     'action_info': action_info,
        #     'host_map': self.host_map,
        #     'obs': observation,
        #     'reward': reward,
        #     'accumulate_reward': accu_reward,
        # }

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
        
    def parse_observation(self, action, observation, host_map, ip_map):
        isSuccess = str(observation['success']) == 'TRUE'
        action_str_split = action.split(" ")
        n = len(action_str_split)
        action_type = action_str_split[0]
        target_host = ""
        if isSuccess:
            target_host = action_str_split[-1] if n > 1 else target_host
            # Update target ho st if it's an IP address to get the hostname
            if target_host in ip_map:
                target_host = ip_map.get(target_host, target_host) 
            elif target_host in self.cidr_to_host_map:
                target_host = self.cidr_to_host_map.get(target_host, target_host)+"_router"
        return target_host, action_type, isSuccess
        
    def update_hosts(self, target_host, action_type, host_map, ip_map, host_type='Red'):
        discovered_subnet, discovered_system, exploited_host, escalated_host = None, None, None, None
        remove_host, restore_host = None, None

        if host_type == 'Red':
            # Check Red's actions
            if target_host:
                if 'ExploitRemote' in action_type:
                    exploited_host = target_host
                elif 'PrivilegeEscalate' in action_type or 'Impact' in action_type:
                    escalated_host = target_host
                elif 'DiscoverRemoteSystems' in action_type:
                    discovered_subnet = target_host
                elif 'DiscoverNetworkServices' in action_type:
                    discovered_system = target_host
                    
        elif host_type == 'Blue':
            # Check Blue's actions
            if target_host:
                if 'Remove' in action_type:
                    remove_host = target_host
                elif 'Restore' in action_type:
                    restore_host = target_host
        
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
            
        return target_host, discovered_subnet, discovered_system, exploited_host, escalated_host, remove_host, restore_host
  
    def reset(self):
        self.compromised_hosts = set(['User0'])
        self.exploited_hosts = set()
        self.escalated_hosts = set(['User0'])
        self.discovered_subnets = set()
        self.discovered_systems = set()
        self._create_ip_host_maps()

    def store_state(self, state_snapshot, episode, step):
        self.game_states[self.num_steps][self.red_agent_name][episode][step] = state_snapshot.copy()

    def get_game_state(self):
        return self.game_states