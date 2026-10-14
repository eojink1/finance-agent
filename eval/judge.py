"""LLM judge: checks an open-ended answer against the task's checklist of points it must make.

Used for questions like "Why did I spend more in March?", where no single string is right but
the causes planted in the data are known. Score = fraction of checklist items the answer makes.
"""

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agent.langchain_agent import chat_model

# Different family from the agent, so it doesn't favour its own style; ~$0.0003 per judgment.
JUDGE_MODEL = "anthropic/claude-haiku-5.5"

JUDGE_PROMPT = ChatPromptTemplate.from_template(
    """You grade an assistant's answer to a personal finance question.

For each checklist item, decide whether the answer clearly makes that point. A number matches
if it is within 1% of the checklist's number. Judge only what the answer says; a point that is
implied but never stated is not met.

Question: {question}

Answer: {answer}

Checklist:
{checklist}"""
)


class ItemVerdict(BaseModel):
    item: str = Field(description="The checklist item, copied exactly")
    reason: str = Field(description="One short sentence: where the answer makes the point, or not")
    met: bool = Field(description="True if the answer clearly makes this point")


class Verdict(BaseModel):
    items: list[ItemVerdict]

    @property
    def score(self) -> float:
        met = [item for item in self.items if item.met]
        return len(met) / len(self.items)


def judge(question: str, answer: str, checklist: list[str]) -> Verdict:
    """One verdict per checklist item, in order."""
    numbered = [f"{i}. {item}" for i, item in enumerate(checklist, 1)]
    model = chat_model(JUDGE_MODEL).with_structured_output(Verdict)
    grader = JUDGE_PROMPT | model
    inputs = {"question": question, "answer": answer, "checklist": "\n".join(numbered)}
    verdict = grader.invoke(inputs)

    if len(verdict.items) != len(checklist):
        raise ValueError(f"judge returned {len(verdict.items)} verdicts for {len(checklist)} items")
    return verdict
