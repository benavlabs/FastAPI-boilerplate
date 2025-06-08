# Contributing to FastAPI-boilerplate

Thank you for your interest in contributing to FastAPI-boilerplate! This guide is meant to make it easy for you to get started.
Contributions are appreciated, even if just reporting bugs, documenting stuff or answering questions. To contribute with a feature:

## Setting Up Your Development Environment

### Cloning the Repository
Start by forking and cloning the FastAPI-boilerplate repository:

1. **Fork the Repository**: Begin by forking the project repository. You can do this by visiting https://github.com/igormagalhaesr/FastAPI-boilerplate and clicking the "Fork" button.
1. **Create a Feature Branch**: Once you've forked the repo, create a branch for your feature by running `git checkout -b feature/fooBar`.
1. **Testing Changes**: Ensure that your changes do not break existing functionality by running tests. In the root folder, execute `uv run pytest` to run the tests.

### Using uv for Dependency Management
FastAPI-boilerplate uses uv for managing dependencies. If you don't have uv installed, follow the instructions on the [official uv website](https://docs.astral.sh/uv/).

Once uv is installed, navigate to the cloned repository and install the dependencies:
```sh
cd FastAPI-boilerplate
uv sync
```

### Activating the Virtual Environment
uv creates a virtual environment for your project. Activate it using:

```sh
source .venv/bin/activate
```

Alternatively, you can run commands directly with `uv run` without activating the environment:
```sh
uv run python your_script.py
```

## Making Contributions

### Coding Standards
- Follow PEP 8 guidelines.
- Write meaningful tests for new features or bug fixes.

### Testing with Pytest
FastAPI-boilerplate uses pytest for testing. Run tests using:
```sh
uv run pytest
```

### Linting
Use mypy for type checking:
```sh
mypy src
```

Use ruff for style:
```sh
ruff check --fix
ruff format
```

Ensure your code passes linting before submitting.

### Using pre-commit for Better Code Quality

It helps in identifying simple issues before submission to code review. By running automated checks, pre-commit can ensure code quality and consistency.

1. **Install Pre-commit**:
   - **Installation**: Install pre-commit in your development environment. Use the command `uv add --dev pre-commit` or `pip install pre-commit`.
   - **Setting Up Hooks**: After installing pre-commit, set up the hooks with `pre-commit install`. This command will install hooks into your .git/ directory which will automatically check your commits for issues.
1. **Committing Your Changes**:
   After making your changes, use `git commit -am 'Add some fooBar'` to commit them. Pre-commit will run automatically on your files when you commit, ensuring that they meet the required standards.
   Note: If pre-commit identifies issues, it may block your commit. Fix these issues and commit again. This ensures that all contributions are of high quality.
1. **Pushing Changes and Creating Pull Request**:
   Push your changes to the branch using `git push origin feature/fooBar`.
   Visit your fork on GitHub and create a new Pull Request to the main repository.

### Additional Notes

**Stay Updated**: Keep your fork updated with the main repository to avoid merge conflicts. Regularly fetch and merge changes from the upstream repository.
**Adhere to Project Conventions**: Follow the coding style, conventions, and commit message guidelines of the project.
**Open Communication**: Feel free to ask questions or discuss your ideas by opening an issue or in discussions.

## Submitting Your Contributions

### Creating a Pull Request
After making your changes:

- Push your changes to your fork.
- Open a pull request with a clear description of your changes.
- Update the README.md if necessary.


### Code Reviews
- Address any feedback from code reviews.
- Once approved, your contributions will be merged into the main branch.

## Code of Conduct
Please adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) to maintain a welcoming and inclusive environment.

Thank you for contributing to FastAPI-boilerplate🚀
