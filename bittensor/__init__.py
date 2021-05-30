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


# Nest Asyncio for colab support.
import nest_asyncio
nest_asyncio.apply()

# Bittensor code and protocol version.
__version__ = '1.0.4'
__version_as_int__ = (100 * 1) + (10 * 0) + (1 * 4)  # Integer representation

# Vocabulary dimension.
#__vocab_size__ = len( tokenizer ) + len( tokenizer.additional_special_tokens) + 100 # Plus 100 for eventual token size increase.
__vocab_size__ = 50378

# Tensor dimension.
# NOTE (const): if/when this increases peers must be responsible for trimming or expanding output to this size.
__network_dim__ = 512 # All network responses have shape = [ __batch_size__, __sequence_dim__, __network_dim__ ]

# Substrate chain block time (seconds).
__blocktime__ = 6

import bittensor.bittensor_pb2 as proto
import bittensor.bittensor_pb2_grpc as grpc

# Load components.
import bittensor.tokenizer
import bittensor.config 
import bittensor.logging
import bittensor.nucleus

from bittensor._cli import cli as cli
from bittensor._axon import axon as axon
from bittensor._wallet import wallet as wallet
from bittensor._config import config as config
from bittensor._receptor import receptor as receptor
from bittensor._endpoint import endpoint as endpoint
from bittensor._dendrite import dendrite as dendrite
from bittensor._executor import executor as executor
from bittensor._metagraph import metagraph as metagraph
from bittensor._subtensor import subtensor as subtensor
from bittensor._tokenizer import tokenizer as tokenizer
from bittensor._serializer import serializer as serializer
from bittensor._dataloader import dataloader as dataloader

from bittensor._cli.cli_impl import CLI as CLI
from bittensor._axon.axon_impl import Axon as Axon
from bittensor._wallet.wallet_impl import Wallet as Wallet
from bittensor._config.config_impl import Config as Config
from bittensor._receptor.receptor_impl import Receptor as Receptor
from bittensor._endpoint.endpoint_impl import Endpoint as Endpoint
from bittensor._executor.executor_impl import Executor as Executor
from bittensor._dendrite.dendrite_impl import Dendrite as Dendrite
from bittensor._metagraph.metagraph_impl import Metagraph as Metagraph
from bittensor._subtensor.subtensor_impl import Subtensor as Subtensor
from bittensor._serializer.serializer_impl import Serializer as Serializer
from bittensor._dataloader.dataloader_impl import Dataloader as Dataloader

# ---- LOGGING ----
__debug_on__ = False
bittensor.logging.init_logger()

# Hardcoded entry point nodes. 
__akira_entrypoints__ = [
    "fermi.akira.bittensor.com:9944",
    "copernicus.akira.bittensor.com:9944",
    "buys.akira.bittensor.com:9944",
    "nobel.akira.bittensor.com:9944",
    "mendeleev.akira.bittensor.com:9944",
    "rontgen.akira.bittensor.com:9944",
    "feynman.akira.bittensor.com:9944",
    "bunsen.akira.bittensor.com:9944",
    "berkeley.akira.bittensor.com:9944",
    "huygens.akira.bittensor.com:9944"
]
__kusanagi_entrypoints__ = [
    "fermi.kusanagi.bittensor.com:9944",
    "copernicus.kusanagi.bittensor.com:9944",
    "buys.kusanagi.bittensor.com:9944",
    "nobel.kusanagi.bittensor.com:9944",
    "mendeleev.kusanagi.bittensor.com:9944",
    "rontgen.kusanagi.bittensor.com:9944",
    "feynman.kusanagi.bittensor.com:9944",
    "bunsen.kusanagi.bittensor.com:9944",
    "berkeley.kusanagi.bittensor.com:9944",
    "huygens.kusanagi.bittensor.com:9944"
]
__boltzmann_entrypoints__ = [
    'feynman.boltzmann.bittensor.com:9944',
]
__local_entrypoints__ = [
    '127.0.0.1:9944'
]