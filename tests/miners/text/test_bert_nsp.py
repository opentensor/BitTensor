import os, sys, time
from unittest.mock import MagicMock
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("miners/TEXT/")
import bittensor
import torch
import numpy
from bert_nsp.bert_nsp import Miner


def test_run_bert_nsp():
    miner = Miner(
        epoch_length = 1,
        n_epochs = 1,
    )
    miner.subtensor.connect = MagicMock(return_value = True)    
    miner.subtensor.subscribe = MagicMock(return_value = True)  
    miner.metagraph.set_weights = MagicMock()   
    miner.metagraph.sync = MagicMock()  
    miner.run()
test_run_bert_nsp()