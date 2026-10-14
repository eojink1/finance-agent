"""The task sets the agent can run on, by split name. A split's tasks are in data/tasks/{split}.jsonl."""

import json

from agent.tools import ROOT
from datasets.bank import BANK
from datasets.dabstep import DABSTEP

DATASETS = {"dev": DABSTEP, "all": DABSTEP, "bank": BANK}


def load_tasks(split: str) -> list[dict]:
    """The split's tasks, one dict per line of its tasks file."""
    with open(ROOT / "data" / "tasks" / f"{split}.jsonl") as f:
        return [json.loads(line) for line in f]
