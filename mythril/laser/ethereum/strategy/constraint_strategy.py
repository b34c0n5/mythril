from mythril.laser.ethereum.state.global_state import GlobalState
from mythril.laser.ethereum.strategy.basic import BasicSearchStrategy
from mythril.support.support_utils import ModelCache

import logging

log = logging.getLogger(__name__)


class DelayConstraintStrategy(BasicSearchStrategy):
    def __init__(self, work_list, max_depth, **kwargs):
        super().__init__(work_list, max_depth)
        self.model_cache = ModelCache()
        self.pending_worklist = []
        log.info("Loaded search strategy extension: DelayConstraintStrategy")

    def get_strategic_global_state(self) -> GlobalState:
        """Returns the next state

        :return: Global state
        """
        while len(self.work_list) == 0:
            state = self.pending_worklist.pop(0)
            model = state.world_state.constraints.get_model()
            if model is not None:
                self.model_cache.put(model, 1)
                self.work_list.append(state)
        state = self.work_list.pop(0)
        return state
