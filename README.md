# Netchill

A Netflix-inspired landing page and sign-in flow built with plain HTML, CSS, and JavaScript.

## Local development

### Option 1: Python static server

```bash
cd /workspaces/netchill
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

### Option 2: Docker Compose

```bash
cd /workspaces/netchill
docker compose up --build
```

Then open:

```text
http://localhost:80
```

## Docker build

```bash
docker build -t netchill:latest .
docker run -p 80:80 netchill:latest
```

## Render deployment

1. Push this project to a GitHub repository.
2. On Render, click New + and choose Web Service.
3. Connect your GitHub repo.
4. Use the following settings:
   - Runtime: Docker
   - Dockerfile path: `Dockerfile`
   - Root directory: `.`
5. Click Create Web Service.
6. Render will build and deploy the container automatically.

### Render config

This repository includes a `render.yaml` file for the basic Render setup.

## Notes

- This is a front-end demo project.
- The sign-in form uses a `mailto:` workflow for demonstration purposes, so the user’s mail client opens with the entered email address and message.
- The home page is a static mock-up with a limited set of movie and TV titles.
