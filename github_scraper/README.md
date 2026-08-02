[project]
name = "github-repository-summary-api"
version = "1.0.0"
description = "Generate structured AI summaries from GitHub repository URLs"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
