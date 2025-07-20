# Agent Instructions

This repository uses **black** for formatting, **pylint** for linting, and **pytest** for testing.

When making changes:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pylint black pytest
   ```
2. Format the code:
   ```bash
   black .
   ```
3. Lint the code:
   ```bash
   pylint core api services utils
   ```
4. Run the test suite:
   ```bash
   pytest
   ```
5. Ensure all commands succeed before committing.
6. Use clear commit messages and provide a PR summary of changes and test results.

