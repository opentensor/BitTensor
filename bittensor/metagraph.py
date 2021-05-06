# The MIT License (MIT)
# Copyright © 2021 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated 
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, 
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of 
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION 
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.

import argparse
import asyncio
import copy
import pandas as pd
import json
import math
import numpy
import random
import time
import torch
import tqdm.asyncio

from munch import Munch
from termcolor import colored
from loguru import logger
from typing import List, Tuple, List

import bittensor
import bittensor.config as config_utils
import bittensor.utils.networking as net
from bittensor.subtensor import Subtensor
from bittensor.crypto.keyfiles import KeyFileError

MAX_INT_WEIGHT = 4294967295 # Max weight value on chain.


# Static network state object.
class _MetagraphState():
    """ Maintains the chain state as a torch object.

        Args:
            tau (:obj:`int`): 
                current, per block, token inflation rate.

            block (:obj:`int`):
                state block number.

            uids (:obj:`torch.LongTensor` of shape :obj:`(metagraph.n)`):
                UIDs for each neuron ordered by index.
            
            stake (:obj:`torch.LongTensor` of shape :obj:`(metagraph.n)`):
                Stake balance for each neuron ordered by index.
                
            lastemit (:obj:`torch.LongTensor` of shape :obj:`(metagraph.n)`):
                Last emission call for each neuron ordered by index.

            weights (:obj:`torch.FloatTensor` of shape :obj:`(metagraph.n, metagraph.n)`):
                Full weight matrix on chain.

            neurons (List[bittensor.proto.Neuron]) 
                List of endpoints on the network.

    """
    def __init__(self):
        self.tau = 0.5
        self.block = 0
        self.n = 0
        self.uids = torch.tensor([])
        self.stake = torch.tensor([])
        self.lastemit = torch.tensor([])
        self.weights = torch.tensor([[]])
        self.neurons = []

class Metagraph():
    """
    Maintains the chain state as a torch object.
    """
    def __init__(   
            self, 
            config: 'Munch' = None, 
            subtensor: 'bittensor.subtensor.Subtensor' = None,
            **kwargs,
        ):
        r""" Initializes a new Metagraph chain interface.
            Args:
                config (:obj:`Munch`, `optional`): 
                    metagraph.Metagraph.config()
                subtensor (:obj:`bittensor.subtensor.Subtensor`, `optional`):
                    subtensor interface utility.
        """
        if config == None:
            config = Metagraph.default_config()
        # bittensor.config.Config.update_with_kwargs(config.metagraph, kwargs) 
        Metagraph.check_config(config)
        self.config = config

        if subtensor == None:
            subtensor = bittensor.subtensor.Subtensor( self.config )
        self.subtensor = subtensor

        self.last_sync = 0
        self._metagraph = _MetagraphState()

    @staticmethod
    def default_config() -> Munch:
        # Parses and returns a config Munch for this object.
        parser = argparse.ArgumentParser(); 
        Metagraph.add_args(parser) 
        config = config_utils.Config.to_config(parser); 
        return config

    @staticmethod   
    def add_args(parser: argparse.ArgumentParser):
        bittensor.subtensor.Subtensor.add_args( parser )
        
    @staticmethod   
    def check_config(config: Munch):
        pass

    @property
    def tau(self) -> torch.FloatTensor:
        r""" tau: the chain per block inflation rate.
            
            Returns:
                tau (:obj:`torchFloatTensor` of shape :obj:`(1)`):
                    Current chain inflation rate.
        """
        return self._metagraph.tau

    @property
    def n(self) -> int:
        r""" Return the number of known neurons on chain.
            
            Returns:
                n (int):
                    number of known neurons.

        """
        return self._metagraph.n

    @property
    def block(self) -> int:
        r""" Return the block number.

             Returns:
                block (:obj:`int`):
                    local chain state block number.
        """
        return self._metagraph.block

    @property
    def lastemit(self) -> torch.LongTensor:
        r""" Returns neuron last update block.
            
            Returns:
                lastemit (:obj:`int`):
                    last emit time.
        """
        return self._metagraph.lastemit

    @property
    def uids(self) -> torch.LongTensor:
        r""" Returns uids of each neuron. Uids are synonymous with indices.
            Returns:
                uids (:obj:`torch.LongTensor` of shape :obj:`(metagraph.n)`):
                    unique id for each neuron.
        """
        return self._metagraph.uids

    @property
    def stake(self) -> torch.FloatTensor:
        r""" Returns neuron stake values.
            
            Returns:
                stake (:obj:`torch.FloatTensor` of shape :obj:`(metagraph.n)`):
                    stake of each known neuron.

        """
        return self._metagraph.stake

    @property
    def S(self) -> torch.FloatTensor:
        r""" Returns neurons stake values.
             
             Returns:
                S (:obj:`torch.FloatTensor` of shape :obj:`(metagraph.n)`):
                    Stake of each known neuron.
        """
        return self._metagraph.stake

    @property
    def I(self) -> torch.FloatTensor:
        r""" Returns neuron incentives: tau * R / sum(R)
        
            Returns:
                I (:obj:`torch.FloatTensor` of shape :obj:`(metagraph.n)`):
                    Block incentive for each neuron. 
        """
        I =  (self.tau * self.ranks) / torch.sum(self.ranks)
        I = torch.where(torch.isnan(I), torch.zeros_like(I), I)
        return I.view(self._metagraph.n)

    @property
    def ranks(self) -> torch.FloatTensor:
        r""" Returns neuron ranks: W^t * S
           
            Returns:
                ranks (:obj:`torch.FloatTensor` of shape :obj:`(metagraph.n)`):
                    Rank of each neuron.

        """
        if self.W.shape[0] == 0:
            return torch.tensor([])
        else:
            S = self.S.view(self._metagraph.n, 1)
            W = torch.transpose(self.W.view(self._metagraph.n, self._metagraph.n), 0, 1)
            R = torch.matmul(W, S).view(self._metagraph.n)
        return R

    @property
    def R(self) -> torch.FloatTensor:
        r""" Returns neuron ranks: W^t * S
             
             Returns:
                rank (:obj:`torch.FloatTensor` of shape :obj:`(metagraph.n)`):
                    Rank of each neuron.
        """
        return self.ranks

    @property
    def neurons(self) -> List[bittensor.proto.Neuron]:
        r""" Return neuron endpoint information for each neuron.
            
            Returns:
                neurons (:obj:`List[bittensor.proto.Neuron]` of shape :obj:`(metagraph.n)`):
                    Endpoint information for each neuron.

        """
        return self._metagraph.neurons

    @property
    def public_keys(self) -> List[str]:
        r""" Return the ordered public keys for state neurons.
        
            Returns:
                public_keys (:obj:`List[str]` of shape :obj:`(metagraph.n)`):
                    Public keys of each neuron.

        """
        return self._metagraph.public_keys

    @property
    def W(self) -> torch.FloatTensor:
        r""" Return full weight matrix from chain.
             Returns:
                W (:obj:`torch.LongFloat` of shape :obj:`(metagraph.n, metagraph.n)`):
                    Weight matrix.
        """
        return self._metagraph.weights

    @property
    def weights(self) -> torch.FloatTensor:
        r""" Return full weight matrix from chain.
             Returns:
                W (:obj:`torch.LongFloat` of shape :obj:`(metagraph.n, metagraph.n)`):
                    Weight matrix.
        """
        return self._metagraph.weights

    @property
    def public_keys( self ) -> List[str]:
        r""" Returns neuron public keys.
            Returns:
                public_keys (:obj:`List[str] of shape :obj:`(metagraph.n)`):
                    Neuron public keys.
        """
        return [neuron.public_key for neuron in self.neurons]

    def sync(self):
        r""" Synchronizes the local self._metagraph with the chain state.
        """
        loop = asyncio.get_event_loop()
        loop.set_debug(enabled=True)
        loop.run_until_complete(self._async_sync())

    async def _async_sync( self ):

        # Query chain info.
        chain_lastemit = dict( await self.subtensor.async_get_last_emit() ) #  Optional[ List[Tuple[uid, lastemit]] ]
        chain_stake = dict( await self.subtensor.async_get_stake() ) #  Optional[ List[Tuple[uid, stake]] ]
        chain_block = int( await self.subtensor.async_get_current_block()) #  Optional[ int ]

        # Update state.
        new_size = len(chain_stake)
        old_size = self._metagraph.n
        self._metagraph.n = new_size
        self._metagraph.block = chain_block
        self._metagraph.neurons = self._metagraph.neurons + [ None for _ in range(new_size - old_size) ]
        self._metagraph.uids = torch.tensor( range(new_size) )
        self._metagraph.stake = torch.tensor([ (float(chain_stake[uid])/1000000000) for uid in range(new_size)])
        self._metagraph.lastemit = torch.tensor([ chain_lastemit[uid] for uid in range(new_size)])

        # Fill new weights
        old_weights = self._metagraph.weights
        self._metagraph.weights = torch.zeros([new_size, new_size])
        self._metagraph.weights[:old_size, :old_size] = old_weights
        
        # Fill updates from queries.
        pending_queries = []
        for uid, lastemit in chain_lastemit.items():
            if lastemit > self.last_sync:
                pending_queries.append( self.fill_uid( uid = uid ) )
        for query in tqdm.asyncio.tqdm.as_completed( pending_queries ):
            await query
        print ('\n')

    # Function which fills weights and neuron info for a uid.
    async def fill_uid ( self, uid: int ) -> bool:
        #try:
        weight_uids = await self.subtensor.async_weight_uids_for_uid( uid ) 
        weight_vals = await self.subtensor.async_weight_vals_for_uid( uid ) 
        neuron = await self.subtensor.async_get_neuron_for_uid( uid )
        neuron_proto = bittensor.proto.Neuron(
                version = bittensor.__version__,
                public_key = neuron['hotkey'],
                address = bittensor.utils.networking.int_to_ip(int(neuron['ip'])),
                port = neuron['port'],
                uid = neuron['uid'], 
                modality = neuron['modality'],
                ip_type = neuron['ip_type']          
        )
        self._metagraph.neurons[uid] = neuron_proto
        row = torch.zeros( [ self._metagraph.n ] )
        for uid_j, val in list(zip( weight_uids, weight_vals )):
            row[ uid_j ] = float(val)
        self._metagraph.weights[ uid ] = row
        return True
        # except Exception as e:
        #     print ()
        #     print(colored('x', 'red'), end ="")
        #     return False

    def __str__(self):
        if self.n != 0:
            peers_online = torch.numel(torch.where( self.block - self.lastemit < 1000 )[0])
        else:
            peers_online = 0
        peers_online = torch.numel(torch.where( self.block - self.lastemit < 1000 )[0])
        return '<green>Metagraph:</green> block:<cyan>{}</cyan>, inflation_rate:<cyan>{}</cyan>, staked:<green>\u03C4{}</green>/<cyan>\u03C4{}</cyan>, active:<green>{}</green>/<cyan>{}</cyan>\n'.format(self.block, self.tau.item(), torch.sum(self.S), self.block/2, peers_online, self.n)

    def __full_str__(self):
        uids = self._metagraph.uids.tolist()
        rows = [self.S.tolist(), self.R.tolist(), self.I.tolist(), self.incentive.tolist(), self.row.tolist(), self.col.tolist()]
        for i in range(self.n):
            rows.append(self.W[i, :].tolist())
        df = pd.DataFrame(rows, columns=uids)
        df = df.rename(index={df.index[0]: 'S'})
        df = df.rename(index={df.index[1]: 'R'})
        df = df.rename(index={df.index[2]: 'I'})
        df = df.rename(index={df.index[3]: 'incentive'})
        df = df.rename(index={df.index[4]: 'row'})
        df = df.rename(index={df.index[5]: 'col'})
        for i in range(self.n):
            df = df.rename(index={df.index[i + 6]: uids[i]})
        df.rename_axis(colored('[uid]', 'red'), axis=1)
        return 'Metagraph:\nuid: {}, inflation_rate: {} block: {} n_neurons: {} \n'.format(self.uid, self.tau, self.block, self.n) + df.to_string(na_rep = '', max_rows=5000, max_cols=25, min_rows=25, line_width=1000, float_format = lambda x: '%.3f' % x, col_space=1, justify='left')

    def __to_tensorboard__(self, tensorboard, global_step):
        tensorboard.add_scalar('Metagraph/neurons', self.n, global_step)
        tensorboard.add_scalar('Metagraph/inflation_rate', self.tau, global_step)


