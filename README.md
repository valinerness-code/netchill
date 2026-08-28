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

### Local development

```bash
cd netchill
mvn -B package dependency:copy-dependencies -DincludeScope=runtime
set DATABASE_URL=postgresql://user:password@localhost:5432/netchill
java -cp "target/classes;target/dependency/*" AuthServer
```

Then open:

```text
http://localhost:8080
```

## Render deployment

1. Push this project to a GitHub repository.
2. On Render, click New + and choose Blueprint.
3. Connect your GitHub repo.
4. Apply the `render.yaml` blueprint.
5. Render builds the Docker image, serves the webpages, and runs the `/api/login` and `/api/register` endpoints from the same service.
6. The blueprint creates the `netchill-db` Postgres database and passes its connection string to the service.

### Render config

This repository includes a `render.yaml` file that configures the static site and Render Postgres database.

## Notes

- The webpages and authentication API are served from the same Java process in production.
- The home page is a static mock-up with a limited set of movie and TV titles.
