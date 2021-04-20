#!/bin/python3
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
"""BERT Next Sentence Prediction Neuron.

This file demonstrates training the BERT neuron with next sentence prediction.

Example:
    $ python miners/text/bert_nsp.py

To run with a config file:
    $ python miners/text/bert_nsp.py --config <path to config file>

"""
import argparse
import copy
import math
import os
import random
import sys
import torch
import torch.nn.functional as F
import bittensor

from qqdm import qqdm, format_str
from tqdm import tqdm
from munch import Munch
from termcolor import colored
from datasets import load_dataset
from types import SimpleNamespace
from typing import Tuple, List, Optional
from torch.nn.utils import clip_grad_norm_
from pytorch_transformers import WarmupCosineWithHardRestartsSchedule

from nuclei.bert import BertNSPNucleus
from loguru import logger
logger = logger.opt(colors=True)

class Miner( bittensor.neuron.BasicNeuron ):

    def __init__( self, config: Munch = None, **kwargs ):

        if config == None:
            config = Miner.default_config();       
        config = copy.deepcopy(config); bittensor.config.Config.update_with_kwargs(config, kwargs )
        logger.info( bittensor.config.Config.toString( config ) )
        Miner.check_config( config )
        self.config = config

        # ---- Row Weights ----
        # Neuron specific mechanism weights.
        self.row_weights = torch.ones([1])

        # ---- Model ----
        self.model = BertNSPNucleus( self.config )

        # ---- Optimizer ----
        self.optimizer = torch.optim.SGD( self.model.parameters(), lr = self.config.miner.learning_rate, momentum = self.config.miner.momentum )
        self.scheduler = WarmupCosineWithHardRestartsSchedule( self.optimizer, 50, 300 )

        # ---- Dataset ----
        self.corpus = bittensor.datasets.NSPCorpus (
            dataset = load_dataset('glue', 'cola')['train'],
            tokenizer = bittensor.__tokenizer__() 
        )
        super(Miner, self).__init__( self.config )

    @staticmethod
    def default_config() -> Munch:
        parser = argparse.ArgumentParser(); 
        Miner.add_args(parser) 
        config = bittensor.config.Config.to_config(parser); 
        return config

    @staticmethod
    def add_args(parser: argparse.ArgumentParser):
        parser.add_argument('--miner.learning_rate', default=0.01, type=float, help='Training initial learning rate.')
        parser.add_argument('--miner.momentum', default=0.98, type=float, help='Training initial momentum for SGD.')
        parser.add_argument('--miner.clip_gradients', default=0.8, type=float, help='Implement gradient clipping to avoid exploding loss on smaller architectures.')
        parser.add_argument('--miner.epoch_length', default=500, type=int, help='Iterations of training per epoch')
        parser.add_argument('--miner.batch_size_train', default=1, type=int, help='Training batch size.')
        parser.add_argument('--miner.n_epochs', default=-1, type=int, help='Miner runs for this many epochs, or forever if < 0')
        BertNSPNucleus.add_args( parser )
        bittensor.neuron.BasicNeuron.add_args( parser )

    @staticmethod
    def check_config(config: Munch):
        assert config.miner.momentum > 0 and config.miner.momentum < 1, "momentum must be a value between 0 and 1"
        assert config.miner.batch_size_train > 0, "batch_size_train must a positive value"
        assert config.miner.learning_rate > 0, "learning_rate must be a positive value."
        BertNSPNucleus.check_config( config )
        bittensor.neuron.BasicNeuron.check_config( config )

    def should_run( self, epoch: int ) -> bool:
        r""" Called by neuron.run() every epoch, if the response is false, training stops.
        """
        if self.config.miner.n_epochs < 0:
            return True
        elif epoch < self.config.miner.n_epochs:
            return True
        else:
            return False

    def should_save( self ) -> bool:
        r""" This function is called by neuron.run() after every epoch.
            If this function returns True, the model is saved to disk and can be reloaded late.
            Returns:
                should_save (bool):
                    True by default. Saves model after each epoch.
        """
        if self.epoch_loss < self.last_saved_loss:
            return True
        else:
            return False

    def should_reload(self) -> bool:
        r""" This function is called by neuron.run() after every epoch.
            If the function returns True the model state is saved to neuron.full_path.
            Returns:
                should_reload (bool):
                    False by default. Does not reload the model after each epoch.
        """
        if torch.any(torch.isnan(torch.cat([param.view(-1) for param in self.model.parameters()]))):
            return True

    def get_state_dict( self ) -> dict:
        r""" This function is called by neuron.save_model() on save.
            The function must return a state dict which will be passed to neuron.reload_from_state_dict.       
            Returns:
                state_dict (:obj:`dict`): 
                    Dictionary containing run state information such as the model parameters.
        """
        return {
            'model_state': self.model.state_dict(), 
            'optimizer_state': self.optimizer.state_dict(),
        }

    def reload_from_state_dict( self, state_dict: dict):
        r""" This function is called by neuron.reload_model() on reload.
            The function must reload the training state from the passed state_dict. 
            Args:
                state_dict (:obj:`dict`): 
                    Dictionary containing run state information such as the model parameters. Output 
                    of get_state_dict.
        """
        self.model.load_state_dict( state_dict['model_state'] )
        self.optimizer.load_state_dict( state_dict['optimizer_state'] )
    
    # ---- Axon Forward call ----
    def forward_call( self, pubkey:str, inputs: torch.FloatTensor, modality:int ) -> torch.FloatTensor:
        r""" This function is called by neuron.forward_loop which can be overridden by the base class.
            The arguments reflect an RPC request from another neuron in the network, the response tensor
            from this function is processed and returned to the caller.
            
            Args:
                pubkey ( str, `required`): 
                    The public key of the caller.
                inputs ( :obj:`torch.Tensor`, `required`):
                    torch inputs to be forward processed.
                modality ( bittensor.proto.Modality, `required`):
                    modality of inputs e.g. bittensor.proto.Modality.TEXT.
            
            Returns:
                outputs (:obj:`torch.FloatTensor`): 
                    The model's outputs as a torch tensor of shape [batch_size, sequence_len, __network_dim__]
        """
        output = self.model.local_forward (
            inputs = inputs        
        )
        return output.local_hidden

    # ---- Axon Backward call ----
    def backward_call( self, pubkey:str, inputs_x:torch.FloatTensor, grads_dy:torch.FloatTensor, modality:int ) -> torch.FloatTensor:
        r""" This function is called by neuron.backward_loop which can be overridden by the base class.
            The arguments reflect an RPC backward request from another neuron in the network, the response tensor
            should be the gradients of the miner's model w.r.t to the inputs and the passed output grads.
            
            Args:
                pubkey ( str, `required`): 
                    The public key of the caller.
                inputs_x ( :obj:`torch.Tensor`, `required`):
                    torch inputs from previous forward call.
                grads_dy ( :obj:`torch.Tensor`, `required`):
                    torch grads of forward output.
                modality ( bittensor.proto.Modality, `required`):
                    modality of inputs e.g. bittensor.proto.Modality.TEXT.
            
            Returns:
                outputs (:obj:`torch.FloatTensor`): 
                    The gradients w.r.t to the inputs [batch_size, sequence_len, __network_dim__]
        """
        # This function is null because the inputs are int64s without gradients. 
        return None

    # ---- Get Row Weights ----
    def get_row_weights( self ) -> torch.FloatTensor:
        r""" This function is called after each training epoch to recieve. Returns row_weights
            to submit to chain.
            Returns:
                row_weights ( torch.FloatTensor, shape=(self.metagraph.n) ): 
                    torch row_weights matching the metagraph size.
                    weight values should be normalized and be in range [0,1].
        """
        self.row_weights = torch.nn.functional.pad( self.row_weights, pad = [0, self.metagraph.n - self.row_weights.numel()] )
        self.row_weights = F.normalize( self.row_weights, p = 1, dim = 0) # Ensure normalization.
        return self.row_weights

    # ---- Get Batches ----
    # Returns a list of batches for the next training epoch.
    def get_epoch_batches( self, epoch:int ) -> List[ dict ]:
        r""" Returns training batches for an epoch.
            Returns:
                batches ( List[dict], shape=(self.config.miner.epoch_length) ): 
                    List of batches as dictionary containing tokenized sentences
                    'inputs' = torch.LongTensor.
        """
        logger.info('Preparing {} batches for epoch ...', self.config.miner.epoch_length)
        batches = []
        for _ in  tqdm( range( self.config.miner.epoch_length ) ):
            batches.append( self.corpus.next_batch( self.config.miner.batch_size_train ) )
        return batches
    
    # ---- Training call ----
    def training_call( self, batch: dict ) -> SimpleNamespace:
        """ Run a single training batch through the model and apply a gradient update.
            Args:
                batch ( dict, `required`): 
                    training batch dictionary as returned from get_epoch_batches            
            Returns:
                outputs ( SimpleNamespace ): 
                    SimpleNamespace output as returned by a nucleus forward call.
                    Must include fields local_loss, remote_loss, distillation_loss
        """
        # ---- Forward pass ----
        inputs = batch['inputs'].to( self.model.device )
        attention_mask = batch['attention_mask'].to( self.model.device )
        targets = batch['targets'].to( self.model.device )
        output = self.model.remote_forward(
            neuron = self,
            inputs = inputs, 
            attention_mask = attention_mask,
            targets = targets,
        )

        # ---- Backward pass ----
        output.loss = output.local_target_loss + output.distillation_loss + output.remote_target_loss
        output.loss.backward() # Accumulates gradients on the model.
        clip_grad_norm_( self.model.parameters(), self.config.miner.clip_gradients ) # clip model gradients
        self.optimizer.step() # Applies accumulated gradients.
        self.optimizer.zero_grad() # Zeros out gradients for next accummulation

        # ---- Train row weights ----
        batch_weights = torch.mean(output.router.weights, axis = 0).to( self.model.device ) # Average over batch.
        self.row_weights = (1 - 0.03) * self.row_weights + 0.03 * batch_weights # Moving avg update.
        self.row_weights = F.normalize( self.row_weights, p = 1, dim = 0) # Ensure normalization.

        return output

if __name__ == "__main__":
    # ---- Build and Run ----
    miner = Miner()
    miner.run()
