"""
This test only checks whether dumping is successful, not whether the dumped state space makes sense
"""

from mythril.mythril import MythrilAnalyzer, MythrilDisassembler
from mythril.ethereum import util
from mythril.solidity.soliditycontract import EVMContract
from tests import TESTDATA_INPUTS
from types import SimpleNamespace


def test_generate_graph():
    for input_file in TESTDATA_INPUTS.iterdir():
        if input_file.name != "origin.sol.o":
            continue
        contract = EVMContract(input_file.read_text())
        disassembler = MythrilDisassembler()

        disassembler.contracts.append(contract)
        args = SimpleNamespace(
            execution_timeout=5,
            max_depth=30,
            solver_timeout=10000,
            no_onchain_data=True,
            loop_bound=None,
            create_timeout=None,
            disable_dependency_pruning=False,
            custom_modules_directory=None,
            pruning_factor=0,
            parallel_solving=True,
            unconstrained_storage=True,
            call_depth_limit=3,
            disable_iprof=True,
            solver_log=None,
            transaction_sequences=None,
            disable_coverage_strategy=False,
            disable_mutation_pruner=False,
            enable_summaries=False,
            enable_state_merging=False,
        )
        analyzer = MythrilAnalyzer(
            disassembler=disassembler,
            strategy="dfs",
            address=(util.get_indexed_address(0)),
            cmd_args=args,
        )

        analyzer.graph_html(transaction_count=1)
