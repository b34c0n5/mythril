"""This module contains functions to set up and execute concolic message
calls."""

import binascii

from typing import List, Union

from mythril.exceptions import IllegalArgumentError
from mythril.disassembler.disassembly import Disassembly
from mythril.laser.ethereum.cfg import Node, Edge, JumpType
from mythril.laser.smt import symbol_factory
from mythril.laser.ethereum.state.calldata import ConcreteCalldata
from mythril.laser.ethereum.state.global_state import GlobalState
from mythril.laser.ethereum.state.world_state import WorldState
from mythril.laser.ethereum.transaction.transaction_models import (
    MessageCallTransaction,
    ContractCreationTransaction,
    tx_id_manager,
)


def execute_contract_creation(
    laser_evm,
    callee_address,
    caller_address,
    origin_address,
    data,
    gas_limit,
    gas_price,
    value,
    code=None,
    track_gas=False,
    contract_name=None,
):
    """Executes a contract creation transaction concretely.

    :param laser_evm:
    :param callee_address:
    :param caller_address:
    :param origin_address:
    :param code:
    :param data:
    :param gas_limit:
    :param gas_price:
    :param value:
    :param track_gas:
    :return:
    """

    open_states: List[WorldState] = laser_evm.open_states[:]
    del laser_evm.open_states[:]

    data = binascii.b2a_hex(data).decode("utf-8")

    for open_world_state in open_states:
        next_transaction_id = tx_id_manager.get_next_tx_id()
        transaction = ContractCreationTransaction(
            world_state=open_world_state,
            identifier=next_transaction_id,
            gas_price=gas_price,
            gas_limit=gas_limit,  # block gas limit
            origin=origin_address,
            code=Disassembly(data),
            caller=caller_address,
            contract_name=contract_name,
            call_data=None,
            call_value=value,
        )
        _setup_global_state_for_execution(laser_evm, transaction)

    return laser_evm.exec(True, track_gas=track_gas)


def execute_message_call(
    laser_evm,
    callee_address,
    caller_address,
    origin_address,
    data,
    gas_limit,
    gas_price,
    value,
    code=None,
    track_gas=False,
) -> Union[None, List[GlobalState]]:
    """Execute a message call transaction from all open states.

    :param laser_evm:
    :param callee_address:
    :param caller_address:
    :param origin_address:
    :param code:
    :param data:
    :param gas_limit:
    :param gas_price:
    :param value:
    :param track_gas:
    :return:
    """

    open_states: List[WorldState] = laser_evm.open_states[:]
    del laser_evm.open_states[:]
    for open_world_state in open_states:
        next_transaction_id = tx_id_manager.get_next_tx_id()
        code = code or open_world_state[callee_address].code.bytecode
        transaction = MessageCallTransaction(
            world_state=open_world_state,
            identifier=next_transaction_id,
            gas_price=gas_price,
            gas_limit=gas_limit,
            origin=origin_address,
            code=Disassembly(code),
            caller=caller_address,
            callee_account=open_world_state[callee_address],
            call_data=ConcreteCalldata(next_transaction_id, data),
            call_value=value,
        )

        _setup_global_state_for_execution(laser_evm, transaction)

    return laser_evm.exec(track_gas=track_gas)


def _setup_global_state_for_execution(laser_evm, transaction) -> None:
    """Set up global state and cfg for a transactions execution.

    :param laser_evm:
    :param transaction:
    """
    # TODO: Resolve circular import between .transaction and ..svm to import LaserEVM here
    global_state = transaction.initial_global_state()
    global_state.transaction_stack.append((transaction, None))

    new_node = Node(
        global_state.environment.active_account.contract_name,
        function_name=global_state.environment.active_function_name,
    )

    if laser_evm.requires_statespace:
        laser_evm.nodes[new_node.uid] = new_node
    if transaction.world_state.node and laser_evm.requires_statespace:
        laser_evm.edges.append(
            Edge(
                transaction.world_state.node.uid,
                new_node.uid,
                edge_type=JumpType.Transaction,
                condition=None,
            )
        )
        new_node.constraints = global_state.world_state.constraints

    global_state.world_state.transaction_sequence.append(transaction)
    global_state.node = new_node
    new_node.states.append(global_state)
    laser_evm.work_list.append(global_state)


def execute_transaction(*args, **kwargs) -> Union[None, List[GlobalState]]:
    """
    Chooses the transaction type based on callee address and
    executes the transaction
    """
    try:
        if kwargs["callee_address"] == "":
            if kwargs["caller_address"] == "":
                kwargs["caller_address"] = kwargs["origin"]
            return execute_contract_creation(*args, **kwargs)
        kwargs["callee_address"] = symbol_factory.BitVecVal(
            int(kwargs["callee_address"], 16), 256
        )
    except KeyError as k:
        raise IllegalArgumentError(f"Argument not found: {k}")
    return execute_message_call(*args, **kwargs)
