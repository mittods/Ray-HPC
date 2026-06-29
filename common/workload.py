"""Synthetic workload generator for the benchmark.

Produces a pool of (source_code, test_cases) pairs that are designed to:
  - Be representative of real competitive-programming submissions
  - Have deterministic content so both Celery and Ray receive identical inputs
  - Cover C++ (compiled) and Python (interpreted) programs
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import NamedTuple

from common.config import PROBLEM_POOL_SIZE, TESTCASES_PER_PROBLEM


class TestCase(NamedTuple):
    input: str
    expected_output: str


@dataclass
class SyntheticProblem:
    problem_id: int
    name: str
    source_code: str
    language: str       # 'cpp' | 'python'
    test_cases: list[TestCase]


# ─── Synthetic C++ program templates ─────────────────────────────────────────

_CPP_SUM = """\
#include <iostream>
int main() {
    int a, b;
    std::cin >> a >> b;
    std::cout << a + b << std::endl;
    return 0;
}
"""

_CPP_FACTORIAL = """\
#include <iostream>
int main() {
    long long n;
    std::cin >> n;
    long long result = 1;
    for (long long i = 2; i <= n; i++) result *= i;
    std::cout << result << std::endl;
    return 0;
}
"""

_CPP_FIBONACCI = """\
#include <iostream>
int main() {
    int n;
    std::cin >> n;
    if (n <= 0) { std::cout << 0 << std::endl; return 0; }
    long long a = 0, b = 1;
    for (int i = 2; i <= n; i++) { long long c = a + b; a = b; b = c; }
    std::cout << (n == 1 ? a : b) << std::endl;
    return 0;
}
"""

_CPP_REVERSE = """\
#include <iostream>
#include <string>
#include <algorithm>
int main() {
    std::string s;
    std::cin >> s;
    std::reverse(s.begin(), s.end());
    std::cout << s << std::endl;
    return 0;
}
"""

_CPP_PRIMES = """\
#include <iostream>
#include <vector>
int main() {
    int n;
    std::cin >> n;
    std::vector<bool> sieve(n + 1, true);
    sieve[0] = sieve[1] = false;
    for (int i = 2; i * i <= n; i++)
        if (sieve[i])
            for (int j = i*i; j <= n; j += i) sieve[j] = false;
    int count = 0;
    for (int i = 2; i <= n; i++) if (sieve[i]) count++;
    std::cout << count << std::endl;
    return 0;
}
"""

_PROBLEM_SPECS = [
    ("SumAB",      _CPP_SUM,       "cpp"),
    ("Factorial",  _CPP_FACTORIAL, "cpp"),
    ("Fibonacci",  _CPP_FIBONACCI, "cpp"),
    ("Reverse",    _CPP_REVERSE,   "cpp"),
    ("CountPrimes",_CPP_PRIMES,    "cpp"),
]


def _generate_testcases(problem_name: str, n: int, seed: int) -> list[TestCase]:
    rng = random.Random(seed)
    cases: list[TestCase] = []

    for _ in range(n):
        if problem_name == "SumAB":
            a, b = rng.randint(0, 10**9), rng.randint(0, 10**9)
            cases.append(TestCase(f"{a} {b}", str(a + b)))

        elif problem_name == "Factorial":
            k = rng.randint(1, 20)
            result = 1
            for i in range(2, k + 1):
                result *= i
            cases.append(TestCase(str(k), str(result)))

        elif problem_name == "Fibonacci":
            k = rng.randint(1, 40)
            a, b = 0, 1
            for _ in range(2, k + 1):
                a, b = b, a + b
            cases.append(TestCase(str(k), str(b if k > 1 else a)))

        elif problem_name == "Reverse":
            s = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(10))
            cases.append(TestCase(s, s[::-1]))

        elif problem_name == "CountPrimes":
            k = rng.randint(10, 1000)
            sieve = [True] * (k + 1)
            sieve[0] = sieve[1] = False
            for i in range(2, int(k**0.5) + 1):
                if sieve[i]:
                    for j in range(i * i, k + 1, i):
                        sieve[j] = False
            count = sum(1 for x in range(2, k + 1) if sieve[x])
            cases.append(TestCase(str(k), str(count)))

        else:
            cases.append(TestCase("0", "0"))

    return cases


def build_problem_pool(
    pool_size: int = PROBLEM_POOL_SIZE,
    testcases_per_problem: int = TESTCASES_PER_PROBLEM,
    seed: int = 42,
) -> list[SyntheticProblem]:
    """Build a deterministic pool of synthetic problems."""
    specs = (_PROBLEM_SPECS * ((pool_size // len(_PROBLEM_SPECS)) + 1))[:pool_size]
    problems = []
    for i, (name, code, lang) in enumerate(specs):
        problems.append(
            SyntheticProblem(
                problem_id=i + 1,
                name=name,
                source_code=code,
                language=lang,
                test_cases=_generate_testcases(name, testcases_per_problem, seed=seed + i),
            )
        )
    return problems


@dataclass
class Submission:
    submission_id: str
    problem: SyntheticProblem


def generate_submissions(
    n: int,
    problem_pool: list[SyntheticProblem],
    seed: int = 0,
) -> list[Submission]:
    """Generate N submission tasks by sampling from the problem pool."""
    rng = random.Random(seed)
    submissions = []
    for i in range(n):
        problem = rng.choice(problem_pool)
        submissions.append(
            Submission(
                submission_id=f"sub-{i:06d}",
                problem=problem,
            )
        )
    return submissions
