from pathlib import Path
from dataclasses import dataclass
import openpyxl


@dataclass
class Question:
    """A single test question from the Excel dataset."""
    index: int
    question: str
    expected: str
    category: str = ""
    reset_session: bool = False


@dataclass
class QuestionSet:
    """A collection of test questions loaded from Excel."""
    questions: list[Question]
    source_file: str

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self):
        return iter(self.questions)

    def completed_count(self, results: dict[int, dict]) -> int:
        return sum(1 for q in self.questions if q.index in results)


def load_questions(
    file_path: str,
    question_column: str = "问题",
    expected_column: str = "期望答案",
    category_column: str = "",
    reset_session_column: str = "",
) -> QuestionSet:
    """Load test questions from an Excel file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    wb = openpyxl.load_workbook(path)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError(f"Excel file is empty: {file_path}")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    try:
        q_idx = headers.index(question_column)
        e_idx = headers.index(expected_column)
    except ValueError as e:
        available = ", ".join(headers)
        raise ValueError(f"Column not found: {e}\nAvailable columns: {available}")

    c_idx = headers.index(category_column) if category_column and category_column in headers else -1
    r_idx = headers.index(reset_session_column) if reset_session_column and reset_session_column in headers else -1

    questions = []
    for i, row in enumerate(rows[1:], start=1):
        question = str(row[q_idx]).strip() if row[q_idx] else ""
        expected = str(row[e_idx]).strip() if row[e_idx] else ""
        if not question:
            continue
        category = str(row[c_idx]).strip() if c_idx >= 0 and row[c_idx] else ""
        reset = False
        if r_idx >= 0 and row[r_idx]:
            val = str(row[r_idx]).strip()
            reset = val in ("是", "yes", "True", "true", "1", "Y", "y")
        questions.append(Question(index=i, question=question, expected=expected,
                                  category=category, reset_session=reset))

    wb.close()
    return QuestionSet(questions=questions, source_file=str(path))
