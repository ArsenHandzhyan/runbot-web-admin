# AGENTS.md - Guidelines for Agentic Coding Agents

This file provides instructions for agentic coding agents working on the RunBot Web Admin repository. It includes build/lint/test commands and code style guidelines.

## Build/Lint/Test Commands

### Build Commands
- Install dependencies: `pip install -r requirements.txt`
- Run the web app locally: `python run_local.py` (uses SQLite by default, or set DATABASE_URL)
- Run the Telegram bot test: `python test_bot.py` (requires TELEGRAM_BOT_TOKEN)
- Run the web app in production mode: `python app.py` (requires DATABASE_URL)

### Lint Commands
No formal linter is configured. Use your discretion or add one (e.g., flake8, black).
- Suggested: `pip install flake8` then `flake8 src/`
- Type checking: `pip install mypy` then `mypy src/` (though not enforced)

### Test Commands
No formal test framework is set up. Tests are minimal.
- Run the Telegram bot test: `python test_bot.py`
- For unit tests, if added later: `python -m pytest tests/` (assume pytest will be added)
- To run a single test (future): `python -m pytest tests/test_file.py::TestClass::test_method -v`

### Environment Setup
- Copy `.env.example.r2` to `.env` and fill in values.
- Set DATABASE_URL (e.g., `sqlite:///./test.db` for local, PostgreSQL for prod).
- Set ADMIN_USERNAME, ADMIN_PASSWORD, WEB_SECRET_KEY.
- For bot: TELEGRAM_BOT_TOKEN, R2 credentials if using storage.

## Code Style Guidelines

### General Principles
- Follow PEP 8 for Python code.
- Use descriptive names.
- Write readable, maintainable code.
- Prefer explicit over implicit.
- Add docstrings for functions and classes.
- Keep functions short and focused (under 50 lines).

### Imports
- Standard library imports first.
- Third-party imports second.
- Local imports last.
- Group imports with blank lines.
- Example:
  ```python
  import os
  import sys

  from flask import Flask, request
  from sqlalchemy import create_engine

  from src.database.db import DatabaseManager
  ```

### Formatting
- Indentation: 4 spaces (no tabs).
- Line length: 88 characters (like Black).
- Use double quotes for strings, single for docstrings.
- Trailing commas in multi-line structures.
- Blank lines: 1 between function definitions, 2 between class definitions.

### Types
- Use type hints where possible.
- Import from typing: `from typing import Optional, List, Dict`
- For function parameters and return types.
- Example:
  ```python
  def get_user(user_id: int) -> Optional[Dict[str, str]]:
      pass
  ```

### Naming Conventions
- Functions and variables: snake_case (e.g., `get_user_data`)
- Classes: CamelCase (e.g., `DatabaseManager`)
- Constants: UPPER_CASE (e.g., `MAX_RETRIES`)
- Private methods: leading underscore (e.g., `_validate_input`)
- Modules: snake_case (e.g., `database_manager.py`)

### Error Handling
- Use try/except for expected errors.
- Log exceptions with logging module.
- Don't catch broad exceptions unless necessary.
- Raise custom exceptions for business logic errors.
- Example:
  ```python
  try:
      result = risky_operation()
  except ValueError as e:
      logger.error(f"Validation error: {e}")
      raise
  ```

### Comments and Documentation
- Use # for inline comments.
- Docstrings for modules, classes, functions using triple quotes.
- Keep comments up-to-date.
- Example:
  ```python
  def calculate_score(points: int) -> float:
      """Calculate user score based on points.

      Args:
          points: Number of points earned.

      Returns:
          Calculated score as float.
      """
      return points * 1.5
  ```

### SQLAlchemy Usage
- Use ORM for queries, not raw SQL.
- Define relationships explicitly.
- Use sessions properly with context managers.
- Example:
  ```python
  with db_manager.session_scope() as session:
      user = session.query(User).filter(User.id == user_id).first()
  ```

### Flask Best Practices
- Use blueprints for modular routes.
- Validate input with WTForms or similar.
- Use flash for user messages.
- Secure routes with login_required decorator.
- Example route:
  ```python
  @app.route('/users/<int:user_id>')
  @login_required
  def user_profile(user_id):
      user = get_user(user_id)
      return render_template('user.html', user=user)
  ```

### Security
- Never log sensitive data (passwords, tokens).
- Use environment variables for secrets.
- Validate user input to prevent injection.
- Use HTTPS in production.

### Git and Version Control
- Commit often with descriptive messages.
- Use feature branches (e.g., feat/add-user-auth).
- Follow conventional commits: `feat:`, `fix:`, `docs:`.
- Pull requests for major changes.

### Performance
- Avoid N+1 queries with SQLAlchemy.
- Use pagination for large lists.
- Cache where appropriate.

### Testing (Future)
- Write unit tests for logic.
- Integration tests for API endpoints.
- Use fixtures for test data.
- Mock external dependencies.

### Deployment
- Use environment variables for config.
- Containerize with Docker if needed.
- Monitor logs and errors.

### Additional Rules
No Cursor or Copilot rules found in the repository.

This file is ~150 lines. Follow these guidelines to maintain consistency.