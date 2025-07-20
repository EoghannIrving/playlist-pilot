# Securing API Credentials

Playlist Pilot relies on multiple external services that require API keys. Follow these guidelines to keep your credentials safe.

## Environment variables

- Use the provided `env.example` as a template and create a `.env` file for your real values.
- Never commit the `.env` file to version control. It should be listed in `.gitignore`.
- When running without Docker, export the variables in your shell or use a tool like `direnv`.

## Docker secrets

- In Docker Swarm or compose v3+ you can store secrets using the `docker secret` command.
- Create a secret: `printf "<your-key>" | docker secret create openai_api_key -`.
- Update your Compose or Swarm service to read the secret at `/run/secrets/openai_api_key`.

## Avoid plain-text configuration

- Keep `settings.json` outside of your repository and mount it when starting the container.
- Do not hardcode API keys in source files or commit them to version control.

Following these practices helps prevent accidental leakage of sensitive information.
