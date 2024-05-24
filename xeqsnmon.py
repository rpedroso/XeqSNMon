from gevent import monkey; monkey.patch_all()  # noqa

import os
import pickle
import logging
from datetime import datetime
from copy import copy

import gevent
import requests
import humanize
from pydispatch import dispatcher
from origamibot import OrigamiBot as Bot


# NODE_URL = 'http://localhost:9231/json_rpc'
NODE_URL = 'http://154.38.165.93:9231/json_rpc'


class SNode:
    __slots__ = ('registration_height',
                 'last_reward_block_height',
                 'last_reward_transaction_index',
                 'last_uptime_proof',
                 'operator_address',
                 'contributors',
                 'is_pool',
                 'portions_for_operator',
                 'service_node_pubkey',
                 'staking_requirement',
                 'total_contributed',
                 'total_reserved',
                 # 'sn_dict',
                 )

    def __init__(self, sn_dict):
        for key, value in sn_dict.items():
            setattr(self, key, value)
        # self.sn_dict = sn = sn_dict
        # self.registration_height = sn['registration_height']
        # self.last_reward_block_height = sn['last_reward_block_height']
        # self.last_reward_transaction_index = \
        #     sn['last_reward_transaction_index']
        # self.last_uptime_proof = sn['last_uptime_proof']
        # self.operator_address = sn['operator_address']

    def __repr__(self):
        # return repr(self.sn_dict)
        # print(self.__slots__)
        ret = [(key, self.get(key)) for key in self.__slots__]
        return repr(dict(ret))

    def get(self, key):
        return getattr(self, key)


class SNodes:
    def __init__(self, node_list=[]):
        self._node_list = [SNode(node) for node in node_list]

    def __iter__(self):
        # return self
        for item in self._node_list:
            yield item

    def __contains__(self, obj):
        for node in self._node_list:
            if obj.service_node_pubkey == node.service_node_pubkey:
                return True
        return False
        # return obj in self._node_list

    def __len__(self):
        return len(self._node_list)

    def __getitem__(self, key):
        print('getitem', key)
        # return getattr(self, item)
        if isinstance(key, slice):
            # Get the start, stop, and step from the slice
            return [self._node_list[ii]
                    for ii in range(*key.indices(len(self._node_list)))]
        elif isinstance(key, int):
            if key < 0: # Handle negative indices
                key += len(self._node_list)
            if key < 0 or key >= len(self._node_list):
                raise IndexError("The index (%d) is out of range." % key)
            return self._node_list[key]
        else:
            raise TypeError("Invalid argument type.")


    # def __next__(self):
    #     try:
    #         result = self._node_list[self._index]
    #     except IndexError:
    #         raise StopIteration
    #     self._index += 1
    #     return result

    def append(self, node):
        self._node_list.append(node)

    def copy(self):
        return copy(self)


def get_all():
    resp = requests.post(NODE_URL,
                         json={
                             "jsonrpc": "2.0",
                             "id": "0",
                             "method": "get_service_nodes"
                         },
                         timeout=2).json()['result']['service_node_states']
    return SNodes(resp)


def check_vanish(prev_list, current_list):
    vanish_list = SNodes()

    for node in prev_list:
        if node not in current_list:
            vanish_list.append(node)

    # For testing - add a node to the list
    # if not vanish_list:
    #     vanish_list.append(node)

    if vanish_list:
        logging.warning('Vanished Node(s):')

        for node in vanish_list:
            logging.warning(f'{node.service_node_pubkey}')
        dispatcher.send('EVT_VANISHED_NODES', sender=dispatcher.Anonymous,
                        nodes=vanish_list)


def check_new(prev_list, current_list):
    new_list = SNodes()

    for node in current_list:
        if node not in current_list:
            new_list.append(node)

    # For testing - add a node to the list
    # if not new_list:
    #     new_list.append(node)

    if new_list:
        logging.warning('New node(s):')

        for node in new_list:
            logging.warning(f'\t{node.service_node_pubkey}')
        dispatcher.send('EVT_NEW_NODES', dispatcher.Anonymous, nodes=new_list)


def check_uptime_proof(node_list):
    delayed_list = SNodes()
    now = datetime.timestamp(datetime.utcnow())
    for node in node_list:
        # Ignore.
        if node.last_uptime_proof == 0:
            continue
        proof_age = now - node.last_uptime_proof

        if proof_age > 1800:
            delayed_list.append(node)

    if delayed_list:
        logging.warning('Delayed node(s):')

        for node in delayed_list:
            proof_age = now - node.last_uptime_proof
            hproof = humanize.precisedelta(proof_age, format="%0.4f")
            logging.warning(f'\t{node.service_node_pubkey}')
            logging.warning(f'\t\tDelayed by {hproof}')

        dispatcher.send('EVT_DELAYED_NODES', sender=dispatcher.Anonymous,
                        nodes=delayed_list)


def run_once():
    try:
        with open('node_list.dump', 'rb') as f:
            prev_node_list = pickle.load(f)
    except FileNotFoundError:
        prev_node_list = None

    resp = get_all()

    if prev_node_list:
        check_vanish(prev_node_list, resp)
        check_new(prev_node_list, resp)

    prev_node_list = resp.copy()

    check_uptime_proof(resp)

    with open('node_list.dump', 'wb') as f:
        pickle.dump(prev_node_list, f)

    logging.info('Total nodes:', len(resp))


def main():
    run_once()
    # while True:
    #     run_once()
    #     logging.info('Sleeping...')
    #     gevent.sleep(10)


# ENV VARS
# FROM = os.getenv('FROM_ADDRESS')
# FROM_PASS = os.getenv('FROM_PASS')
# TO = os.getenv('TO_ADDRESS')

TOKEN = os.getenv('TOKEN')
TO = os.getenv('TO')

if not TOKEN or not TO:
    raise ValueError()

bot = Bot(TOKEN)


def chunk_list(lst, chunk_size=5):
    # list_chunked = [my_list[i:i + chunk_size] \
    #    for i in range(0, len(my_list), chunk_size)]
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


class Listener:
    def on_vanished_nodes(self, nodes):
        print('on_vanished_nodes')
        for chunk in chunk_list(nodes, 5):
            pks = '\n'.join(str(node.service_node_pubkey) for node in chunk)
            bot.send_message(TO, f'Vanished node(s):\n{pks}\n')

    def on_new_nodes(self, nodes):
        print('on_new_nodes', nodes)
        for chunk in chunk_list(nodes, 5):
            pks = '\n'.join(str(node.service_node_pubkey) for node in chunk)
            bot.send_message(TO, f'New node(s):\n{pks}\n')

    def on_delayed_nodes(self, nodes):
        print('on_delayed_nodes')
        for chunk in chunk_list(nodes, 5):
            pks = '\n'.join(str(node.service_node_pubkey) for node in chunk)
            bot.send_message(TO, f'Delayed node(s):\n{pks}\n')


def bot_main():
    global listener

    listener = Listener()

    dispatcher.connect(listener.on_vanished_nodes, 'EVT_VANISHED_NODES')
    dispatcher.connect(listener.on_new_nodes, 'EVT_NEW_NODES')
    dispatcher.connect(listener.on_delayed_nodes, 'EVT_DELAYED_NODES')


class FakeBot:
    def __init__(self, *args):
        pass

    def send_message(self, chat_id, message, **kwargs):
        print('_' * 60)
        print(message)
        print('_' * 60)


if __name__ == "__main__":
    # gevent.spawn(bot_main)
    bot_main()
    main()
