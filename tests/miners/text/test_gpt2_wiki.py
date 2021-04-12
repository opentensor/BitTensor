import os, sys, time
from unittest.mock import MagicMock
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("miners/TEXT/")
import bittensor
import torch
import numpy
from gpt2_wiki.gpt2_wiki import Miner

def test_run_gpt2():
    miner = Miner(
        epoch_length = 1,
        n_epochs = 1,
    )
    miner.neuron.subtensor.connect = MagicMock(return_value = True)    
    miner.neuron.subtensor.subscribe = MagicMock(return_value = True)  
    miner.neuron.metagraph.set_weights = MagicMock()   
    miner.neuron.metagraph.sync = MagicMock()  
    miner.run()
test_run_gpt2()