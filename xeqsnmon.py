import time
import pickle
import logging
from datetime import datetime
from copy import copy

import requests
import humanize
from pydispatch import dispatcher
try:
    from config_local import bot, TO, NODE_URL
except ImportError:
    from config import bot, TO, NODE_URL


class Daemon:
    __slots__ = ('alt_blocks_count',
                 'block_size_limit',
                 'block_size_median',
                 'block_weight_limit',
                 'block_weight_median',
                 'bootstrap_daemon_address',
                 'cumulative_difficulty',
                 'cumulative_difficulty_top64',
                 'database_size',
                 'difficulty',
                 'difficulty_top64',
                 'free_space',
                 'grey_peerlist_size',
                 'height',
                 'height_without_bootstrap',
                 'incoming_connections_count',
                 'mainnet',
                 'nettype',
                 'offline',
                 'outgoing_connections_count',
                 'rpc_connections_count',
                 'stagenet',
                 'start_time',
                 'status',
                 'target',
                 'target_height',
                 'testnet',
                 'top_block_hash',
                 'tx_count',
                 'tx_pool_size',
                 'untrusted',
                 'update_available',
                 'version',
                 'was_bootstrap_ever_used',
                 'white_peerlist_size',
                 'wide_cumulative_difficulty',
                 'wide_difficulty')

    def __init__(self, sn_dict):
        raise TypeError("This class cannot be instantiated directly.")

    @classmethod
    def info(cls):
        obj = super().__new__(cls)
        sn_dict = requests.get(NODE_URL + '/get_info', timeout=20).json()
        for key, value in sn_dict.items():
            setattr(obj, key, value)
        return obj


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
                 )

    def __init__(self, sn_dict):
        for key, value in sn_dict.items():
            setattr(self, key, value)

    def __repr__(self):
        ret = [(key, self.get(key)) for key in self.__slots__]
        return repr(dict(ret))

    def get(self, key):
        return getattr(self, key)


class SNodes:
    def __init__(self, node_list=[]):
        self._node_list = [SNode(node) for node in node_list]

    def __iter__(self):
        for item in self._node_list:
            yield item

    def __contains__(self, obj):
        for node in self._node_list:
            if obj.service_node_pubkey == node.service_node_pubkey:
                return True
        return False

    def __len__(self):
        return len(self._node_list)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self._node_list[ii]
                    for ii in range(*key.indices(len(self._node_list)))]
        elif isinstance(key, int):
            if key < 0:  # Handle negative indices
                key += len(self._node_list)
            if key < 0 or key >= len(self._node_list):
                raise IndexError("The index (%d) is out of range." % key)
            return self._node_list[key]
        else:
            raise TypeError("Invalid argument type.")

    def append(self, node):
        self._node_list.append(node)

    def copy(self):
        return copy(self)

    @staticmethod
    def get_all():
        for i in range(5):
            try:
                resp = requests.post(NODE_URL + '/json_rpc',
                             json={
                                 "jsonrpc": "2.0",
                                 "id": "0",
                                 "method": "get_service_nodes"
                             },
                             timeout=20
                             ).json()['result']['service_node_states']
                break
            except requests.exceptions.ReadTimeout:
                logging.warning('Timeout: retrying...')
                time.sleep(.2)
        return SNodes(resp)

    def check_vanish(self, node):
        if node not in self:
            return True
        return False

    def check_new(self, node, prev_list):
        if node not in prev_list:
            return True
        return False

    def check_delayed(self, node):
        now = datetime.timestamp(datetime.now())
        proof_age = now - node.last_uptime_proof

        if proof_age > 5400:
            return True
        return False

    def check_to_expire(self, node, daemon):
        expires_at = node.registration_height + 20180
        blocks_left = expires_at - daemon.height
        if 0 < blocks_left <= 720:
            return True
        return False

    def check(self):
        try:
            with open('node_list.dump', 'rb') as f:
                prev_node_list = pickle.load(f)
        except FileNotFoundError:
            prev_node_list = None

        daemon = Daemon.info()

        new_prev_node_list = self.copy()

        vanish_list = SNodes()
        new_list = SNodes()
        delayed_list = SNodes()
        to_expire_list = SNodes()

        if prev_node_list:
            for node in prev_node_list:
                is_vanished_node = self.check_vanish(node)
                if is_vanished_node:
                    vanish_list.append(node)

        for node in self:
            if prev_node_list:
                is_new_node = self.check_new(node, prev_node_list)
                if is_new_node:
                    new_list.append(node)
                    continue

            is_delayed = self.check_delayed(node)
            if is_delayed:
                delayed_list.append(node)

            is_to_expire = self.check_to_expire(node, daemon)
            if is_to_expire:
                to_expire_list.append(node)

        if vanish_list:
            dispatcher.send('EVT_VANISHED_NODES', sender=dispatcher.Anonymous,
                            nodes=vanish_list, daemon=daemon)
        if new_list:
            dispatcher.send('EVT_NEW_NODES',
                            dispatcher.Anonymous, nodes=new_list)

        if delayed_list:
            dispatcher.send('EVT_DELAYED_NODES', sender=dispatcher.Anonymous,
                            nodes=delayed_list)

        if to_expire_list:
            dispatcher.send('EVT_TO_EXPIRE_NODES', sender=dispatcher.Anonymous,
                            nodes=to_expire_list, daemon=daemon)

        if 1:  # vanish_list or new_list or delayed_list or to_expire_list:
            dispatcher.send('EVT_TOTAL_NODES', sender=dispatcher.Anonymous,
                            nodes=self, daemon=daemon)

        with open('node_list.dump', 'wb') as f:
            pickle.dump(new_prev_node_list, f)

        logging.info('Total nodes:', len(self))


def chunk_list(lst, chunk_size=5):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


class Listener:
    def on_vanished_nodes(self, nodes, daemon):
        for chunk in chunk_list(nodes, 40):
            pk_list = []
            for node in chunk:
                if node.registration_height + 20180 <= daemon.height:
                    expired = '💥 Expired'
                else:
                    expired = '🩸 Lost'
                pk_list.append(
                    f'{node.service_node_pubkey[:10]}... - {expired} - '
                    f'Registration Height: {node.registration_height}'
                )

            pks = '\n'.join(pk_list)
            bot.send_message(TO, f'Vanished node(s):\n{pks}\n')

    def on_new_nodes(self, nodes):
        for chunk in chunk_list(nodes, 40):
            pk_list = []
            for node in chunk:
                pk_list.append(
                    f'{node.service_node_pubkey[:10]}... - '
                    f'Registration Height: {node.registration_height}'
                )

            pks = '\n'.join(pk_list)
            bot.send_message(TO, f'⭐️ New node(s):\n{pks}\n')

    def on_delayed_nodes(self, nodes):
        now = datetime.timestamp(datetime.now())
        for chunk in chunk_list(nodes, 40):
            pk_list = []
            for node in chunk:
                proof_age = now - node.last_uptime_proof
                if node.last_uptime_proof == 0:
                    hproof = '🚫 Proof not received'
                else:
                    hproof = "🕙 %s" % humanize.precisedelta(
                        proof_age, format="%0.4f")

                pk_list.append(
                    f'{node.service_node_pubkey[:10]}... - {hproof}')

            pks = '\n'.join(pk_list)
            bot.send_message(TO, f'Delayed node(s):\n{pks}\n')

    def on_total_nodes(self, nodes, daemon):
        uniq = len(set(node.operator_address for node in nodes))
        total = len(nodes)
        bot.send_message(TO,
                         '<code>'
                         f'Total node(s): {total}\n'
                         f'Operators:     {uniq}\n'
                         f'Height:        {daemon.height}\n</code>',
                         parse_mode="HTML"
                         )

    def on_to_expire_nodes(self, nodes, daemon):
        for chunk in chunk_list(nodes, 40):
            pk_list = []
            for node in chunk:
                expires_at = node.registration_height + 20180
                blocks_left = expires_at - daemon.height
                pk_list.append(
                    f'{node.service_node_pubkey[:10]}... - '
                    f'To expire at {expires_at} ({blocks_left} '
                    'blocks left)'
                )

            pks = '\n'.join(pk_list)
            bot.send_message(TO, f'🧨 To expire node(s):\n{pks}\n')


def main():
    global listener

    listener = Listener()

    dispatcher.connect(listener.on_vanished_nodes, 'EVT_VANISHED_NODES')
    dispatcher.connect(listener.on_new_nodes, 'EVT_NEW_NODES')
    dispatcher.connect(listener.on_delayed_nodes, 'EVT_DELAYED_NODES')
    dispatcher.connect(listener.on_total_nodes, 'EVT_TOTAL_NODES')
    dispatcher.connect(listener.on_to_expire_nodes, 'EVT_TO_EXPIRE_NODES')

    nodes = SNodes.get_all()
    nodes.check()


if __name__ == "__main__":
    main()
