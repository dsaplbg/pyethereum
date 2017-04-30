from ethereum.state import State
from ethereum.block import FakeHeader, Block
from ethereum.utils import decode_hex, parse_int_or_hex, sha3, to_string, \
    remove_0x_head, encode_hex, big_endian_to_int
from ethereum.config import default_config, Env
from ethereum.exceptions import InvalidTransaction
import ethereum.transactions as transactions
import ethereum.state_transition as state_transition
import copy
import json

from ethereum.slogging import LogRecorder, configure_logging, set_level
config_string = ':info,eth.vm.log:trace,eth.vm.op:trace,eth.vm.stack:trace,eth.vm.exit:trace,eth.pb.msg:trace,eth.pb.tx:debug'

# configure_logging(config_string=config_string)

fake_headers = {}

def mk_fake_header(blknum):
    if blknum not in fake_headers:
        fake_headers[blknum] = FakeHeader(sha3(to_string(blknum)))
    return fake_headers[blknum]

basic_env = {
    "currentCoinbase": "2adc25665018aa1fe0e6bc666dac8fc2697ff9ba",
    "currentDifficulty": "256",
    "currentGasLimit": "1000000000",
    "currentNumber": "257",
    "currentTimestamp": "1",
    "previousHash": "5e20a0453cecd065ea59c37ac63e079ee08998b6045136a8ce6635c7912ec0b6"
}

konfig = copy.copy(default_config)

konfig_homestead = copy.copy(konfig)
konfig_homestead["HOMESTEAD_FORK_BLKNUM"] = 0
konfig_homestead["ANTI_DOS_FORK_BLKNUM"] = 2**99
konfig_homestead["CLEARING_FORK_BLKNUM"] = 2**99
konfig_homestead["METROPOLIS_FORK_BLKNUM"] = 2**99

konfig_tangerine = copy.copy(konfig)
konfig_tangerine["HOMESTEAD_FORK_BLKNUM"] = 0
konfig_tangerine["ANTI_DOS_FORK_BLKNUM"] = 0
konfig_tangerine["CLEARING_FORK_BLKNUM"] = 2**99
konfig_tangerine["METROPOLIS_FORK_BLKNUM"] = 2**99

konfig_spurious = copy.copy(konfig)
konfig_spurious["HOMESTEAD_FORK_BLKNUM"] = 0
konfig_spurious["ANTI_DOS_FORK_BLKNUM"] = 0
konfig_spurious["CLEARING_FORK_BLKNUM"] = 0
konfig_spurious["METROPOLIS_FORK_BLKNUM"] = 2**99

konfig_metropolis = copy.copy(konfig)
konfig_metropolis["HOMESTEAD_FORK_BLKNUM"] = 0
konfig_metropolis["ANTI_DOS_FORK_BLKNUM"] = 0
konfig_metropolis["CLEARING_FORK_BLKNUM"] = 0
konfig_metropolis["METROPOLIS_FORK_BLKNUM"] = 0

configs = {
    #"Homestead": konfig_homestead,
    #"EIP150": konfig_tangerine,
    "EIP158": konfig_spurious,
    "Metropolis": konfig_metropolis
}

def mk_state_diff(prev, post):
    o = {}
    for k in prev.keys():
        if k not in post:
            o[k] = ["-", prev[k]]
    for k in post.keys():
        if k not in prev:
            o[k] = ["+", post[k]]
        elif prev[k] != post[k]:
            ok = {}
            for key in ('nonce', 'balance', 'code'):
                if prev[k][key] != post[k][key]:
                    ok[key] = [prev[k][key], "->", post[k][key]]
            if prev[k]["storage"] != post[k]["storage"]:
                ok["storage"] = {}
                for sk in prev[k]["storage"].keys():
                    if sk not in post[k]["storage"]:
                        ok["storage"][sk] = ["-", prev[k]["storage"][sk]]
                for sk in post[k]["storage"].keys():
                    if sk not in prev[k]["storage"]:
                        ok["storage"][sk] = ["+", post[k]["storage"][sk]]
                    else:
                        ok["storage"][sk] = [prev[k]["storage"][sk], "->", post[k]["storage"][sk]]
            o[k] = ok
    return o

def compute_state_test_unit(state, txdata, indices, konfig):
    state.env.config = konfig
    s = state.snapshot()
    try:
        # Create the transaction
        tx = transactions.Transaction(
            nonce=parse_int_or_hex(txdata['nonce'] or b"0"),
            gasprice=parse_int_or_hex(txdata['gasPrice'] or b"0"),
            startgas=parse_int_or_hex(txdata['gasLimit'][indices["gas"]] or b"0"),
            to=decode_hex(remove_0x_head(txdata['to'])),
            value=parse_int_or_hex(txdata['value'][indices["value"]] or b"0"),
            data=decode_hex(remove_0x_head(txdata['data'][indices["data"]])))
        if 'secretKey' in txdata:
            tx.sign(decode_hex(remove_0x_head(txdata['secretKey'])))
        else:
            tx.v = parse_int_or_hex(txdata['v'])
        # Run it
        prev = state.to_dict()
        success, output = state_transition.apply_transaction(state, tx)
        print("Applied tx")
    except InvalidTransaction as e:
        print("Exception: %r" % e)
        success, output = False, b''
    state.commit()
    post = state.to_dict()
    output_decl = {
        "hash": '0x' + encode_hex(state.trie.root_hash),
        "indexes": indices,
        "diff": mk_state_diff(prev, post)
    }
    state.revert(s)
    return output_decl


def init_state(env, pre):
    # Setup env
    state = State(
        env=Env(config=konfig),
        block_prevhash=decode_hex(remove_0x_head(env['previousHash'])),
        prev_headers=[mk_fake_header(i) for i in range(parse_int_or_hex(env['currentNumber']) -1,
                                                       max(-1, parse_int_or_hex(env['currentNumber']) -257), -1)],
        block_number=parse_int_or_hex(env['currentNumber']),
        block_coinbase=decode_hex(remove_0x_head(env['currentCoinbase'])),
        block_difficulty=parse_int_or_hex(env['currentDifficulty']),
        gas_limit=parse_int_or_hex(env['currentGasLimit']),
        timestamp=parse_int_or_hex(env['currentTimestamp']))

    # Fill up pre
    for address, h in list(pre.items()):
        assert len(address) in (40, 42)
        address = decode_hex(remove_0x_head(address))
        assert set(h.keys()) == set(['code', 'nonce', 'balance', 'storage'])
        state.set_nonce(address, parse_int_or_hex(h['nonce']))
        state.set_balance(address, parse_int_or_hex(h['balance']))
        state.set_code(address, decode_hex(remove_0x_head(h['code'])))
        for k, v in h['storage'].items():
            state.set_storage_data(address,
                                   big_endian_to_int(decode_hex(k[2:])),
                                   decode_hex(v[2:]))

    state.commit()
    return state

def verify_state_test(test):
    print("Verifying state test")
    _state = init_state(test["env"], test["pre"])
    for config_name, results in test["post"].items():
        # Old protocol versions may not be supported
        if config_name not in configs:
            continue
        print("Testing for %s" % config_name)
        for result in results:
            data = test["transaction"]['data'][result["indexes"]["data"]]
            if len(data) > 2000:
                data = "data<%d>" % (len(data) // 2 - 1)
            print("Checking for values: g %d v %d d %s" % (
                  parse_int_or_hex(test["transaction"]['gasLimit'][result["indexes"]["gas"]]),
                  parse_int_or_hex(test["transaction"]['value'][result["indexes"]["value"]]),
                  data))
            computed = compute_state_test_unit(_state, test["transaction"], result["indexes"], configs[config_name])
            if computed["hash"][-64:] != result["hash"][-64:]:
                for k in computed["diff"]:
                    print(k, computed["diff"][k])
                raise Exception("Hash mismatch, computed: %s, supplied: %s" % (computed["hash"], result["hash"]))
            else:
                print("Hash matched!: %s" % computed["hash"])
