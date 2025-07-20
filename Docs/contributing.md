# Contributing Guide

Thank you for considering a contribution to Playlist Pilot! To get started:

1. **Fork the repository** and create a descriptive feature branch.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the tests** to ensure everything passes:
   ```bash
   pytest
   ```
4. **Format** and **lint** your code:
   ```bash
   black .
   pylint core api services utils
   ```
5. Commit your changes and open a **pull request** against `main`. Include a clear description of your changes.

Feel free to open an issue first if you want to discuss a feature or bug fix.
