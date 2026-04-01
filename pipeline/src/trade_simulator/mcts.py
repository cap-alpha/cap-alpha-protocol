"""
Trade Simulator: Monte Carlo Tree Search (MCTS) Engine
Author: Cap Alpha Protocol

This module implements the MCTS algorithm for exploring the trade space.
It uses:
1. Selection (UCT)
2. Expansion (Propose Trades)
3. Simulation (Rollout with Heuristic Policy)
4. Backpropagation (Update Value)
"""

import math
import random
from typing import Dict, List, Optional

from trade_simulator.agent import Agent
from trade_simulator.state import LeagueState, TradeAction


class MCTSNode:
    def __init__(
        self,
        state: LeagueState,
        parent: Optional["MCTSNode"] = None,
        action: Optional[TradeAction] = None,
    ):
        self.state = state
        self.parent = parent
        self.action = action  # The action that led to this state
        self.children: List["MCTSNode"] = []
        self.visits = 0
        self.value = 0.0  # Aggregate Reward

    def is_fully_expanded(self) -> bool:
        # Simplified: Check if children count matches possible actions
        # In reality, this needs dynamic checks
        return len(self.children) > 0  # Placeholder

    def best_child(self, exploration_weight: float = 1.41) -> "MCTSNode":
        """
        Select child using UCT (Upper Confidence Bound for Trees).
        """
        best_score = -float("inf")
        best_node = None

        for child in self.children:
            exploit = child.value / (child.visits + 1e-6)
            explore = math.sqrt(math.log(self.visits + 1) / (child.visits + 1e-6))
            uct_score = exploit + (exploration_weight * explore)

            if uct_score > best_score:
                best_score = uct_score
                best_node = child

        return best_node


class MCTS:
    def __init__(self, root_state: LeagueState, agents: Dict[str, Agent]):
        self.root = MCTSNode(root_state)
        self.agents = agents

    def search(self, iterations: int = 1000) -> TradeAction:
        """
        Execute MCTS for N iterations.
        Returns the best immediate action (Trade).
        """
        for _ in range(iterations):
            node = self._select(self.root)
            if not node.state.is_terminal():  # Use simplistic terminal check for now
                node = self._expand(node)
            reward = self._simulate(node)
            self._backpropagate(node, reward)

        return self.root.best_child(exploration_weight=0.0).action

    def _select(self, node: MCTSNode) -> MCTSNode:
        while node.is_fully_expanded() and node.children:
            node = node.best_child()
        return node

    def _expand(self, node: MCTSNode) -> MCTSNode:
        # Get legal actions for active team (e.g. Random Team or specific turn)
        # For POC, assume active team is whoever's turn it is
        active_team = list(node.state.teams.keys())[0]  # Simplification
        actions = node.state.get_legal_actions(active_team)

        for action in actions:
            new_state = node.state.apply_action(action)
            child_node = MCTSNode(new_state, parent=node, action=action)
            node.children.append(child_node)

        return random.choice(node.children) if node.children else node

    def _simulate(self, node: MCTSNode) -> float:
        # Adversarial Rollout:
        # Randomly simulate futures, but use Agent Utility to decide
        # Return the final "Win Probability" or "Utility"
        return 0.5  # Placeholder Reward

    def _backpropagate(self, node: MCTSNode, reward: float):
        while node:
            node.visits += 1
            node.value += reward
            node = node.parent
