# Netchill

A Netflix-inspired landing page and sign-in flow built with plain HTML, CSS, and JavaScript.

## Security Features

This application includes multiple layers of security protection:

### Input Validation & Sanitization
- **Email validation**: Regex-based format validation for all email inputs
- **Password validation**: Minimum 6 characters with allowed character set restrictions
- **HTML escaping**: XSS prevention by converting special characters (`<`, `>`, `&`, `"`, `'`) to HTML entities
- **SQL injection prevention**: Removal of potentially harmful SQL characters (`'`, `"`, `;`, backtick, backslash)
- **Input trimming**: All form inputs are trimmed of whitespace before processing

### HTTP Security Headers
- **Content-Security-Policy (CSP)**: Prevents inline script execution and restricts resource loading
- **X-Content-Type-Options**: Prevents MIME-type sniffing attacks
- **X-Frame-Options**: Protects against clickjacking by restricting framing
- **X-XSS-Protection**: Additional XSS protection header
- **Referrer-Policy**: Controls referrer information leakage

### Protected Endpoints
- Sign-up form: Email sanitized before alert display
- Sign-in form: Email and password sanitized, only email stored (never store passwords)
- All inputs validated before localStorage storage or external links

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
