import bittensor
import os

the_wallet = bittensor.wallet(
    path = '/tmp/pytest',
    name = 'pytest',
    hotkey = 'pytest',
) 

def test_create_wallet():
    the_wallet.create_new_coldkey( use_password=False, overwrite = True )
    the_wallet.create_new_hotkey( use_password=False, overwrite = True )
    assert os.path.isfile(the_wallet.coldkeyfile)
    assert os.path.isfile(the_wallet.hotkeyfile)
    assert os.path.isfile(the_wallet.coldkeypubfile)

def test_wallet_config():
    config = bittensor.wallet.config()
    config.wallet.name
    config.wallet.path
    config.wallet.hotkey

def test_wallet_keypair():  
    the_wallet.hotkey
    the_wallet.coldkeypub

test_create_wallet()
test_wallet_config()
test_wallet_keypair()