import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.KeySpec;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class AuthServer {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int ITERATIONS = 210_000;
    private static final int KEY_LENGTH = 256;

    private AuthServer() {
    }

    public static void main(String[] args) throws IOException, SQLException {
        int port = Integer.parseInt(System.getenv().getOrDefault("API_PORT",
            System.getenv().getOrDefault("PORT", "8080")));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/", AuthServer::staticFile);
        server.createContext("/api/register", AuthServer::register);
        server.createContext("/api/login", AuthServer::login);
        initializeDatabase();
        server.start();
        System.out.println("Auth API listening on port " + port);
    }

    private static void staticFile(HttpExchange exchange) throws IOException {
        String method = exchange.getRequestMethod();
        boolean isHead = "HEAD".equalsIgnoreCase(method);
        if (!"GET".equalsIgnoreCase(method) && !isHead) {
            exchange.getResponseHeaders().set("Allow", "GET, HEAD");
            respond(exchange, 405, "Method not allowed");
            return;
        }

        String requestPath = exchange.getRequestURI().getPath();
        String relativePath = "/".equals(requestPath) ? "index.html" : requestPath.substring(1);
        File file = new File(relativePath).getCanonicalFile();
        File root = new File(".").getCanonicalFile();

        if (!file.toPath().startsWith(root.toPath()) || !file.isFile()) {
            // No index.html on disk (this backend has no bundled frontend) -- still
            // return 200 with no body for a HEAD health check on "/" specifically,
            // so platform health checks see a healthy status rather than a 404.
            if (isHead && "/".equals(requestPath)) {
                exchange.getResponseHeaders().set("Content-Length", "0");
                exchange.sendResponseHeaders(200, -1);
                exchange.close();
                return;
            }
            respond(exchange, 404, "Not found");
            return;
        }

        String contentType = URLConnection.guessContentTypeFromName(file.getName());
        if (contentType != null) {
            exchange.getResponseHeaders().set("Content-Type", contentType);
        }
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");

        if (isHead) {
            exchange.getResponseHeaders().set("Content-Length", String.valueOf(file.length()));
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
            return;
        }

        exchange.sendResponseHeaders(200, file.length());
        try (InputStream input = new FileInputStream(file);
             OutputStream output = exchange.getResponseBody()) {
            input.transferTo(output);
        }
    }

    private static void register(HttpExchange exchange) throws IOException {
        if (!isPost(exchange)) return;
        Map<String, String> data = parseForm(exchange);
        String email = data.getOrDefault("email", "").trim().toLowerCase();
        String password = data.getOrDefault("password", "");

        if (!email.matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$") || password.length() < 6 || password.length() > 128) {
            respond(exchange, 400, "Invalid email or password");
            return;
        }

        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        try (Connection connection = database();
             PreparedStatement statement = connection.prepareStatement(
                     "INSERT INTO users (email, password_hash, password_salt) VALUES (?, ?, ?)")) {
            statement.setString(1, email);
            statement.setString(2, hash(password, salt));
            statement.setBytes(3, salt);
            statement.executeUpdate();
            respond(exchange, 201, "Account created");
        } catch (SQLException error) {
            if ("23505".equals(error.getSQLState())) {
                respond(exchange, 409, "An account with that email already exists");
            } else {
                error.printStackTrace();
                respond(exchange, 500, "Database error");
            }
        }
    }

    private static void login(HttpExchange exchange) throws IOException {
        if (!isPost(exchange)) return;
        Map<String, String> data = parseForm(exchange);
        String email = data.getOrDefault("email", "").trim().toLowerCase();
        String password = data.getOrDefault("password", "");

        try (Connection connection = database();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT password_hash, password_salt FROM users WHERE email = ?")) {
            statement.setString(1, email);
            try (ResultSet result = statement.executeQuery()) {
                if (result.next() && hash(password, result.getBytes("password_salt")).equals(result.getString("password_hash"))) {
                    respond(exchange, 200, "Signed in");
                } else {
                    respond(exchange, 401, "Invalid email or password");
                }
            }
        } catch (SQLException error) {
            error.printStackTrace();
            respond(exchange, 500, "Database error");
        }
    }

    private static Connection database() throws SQLException {
        String databaseUrl = System.getenv("DATABASE_URL");
        if (databaseUrl != null && !databaseUrl.isBlank()) {
            URI databaseUri = URI.create(databaseUrl.trim());
            if (!"postgres".equalsIgnoreCase(databaseUri.getScheme())
                    && !"postgresql".equalsIgnoreCase(databaseUri.getScheme())) {
                throw new IllegalStateException("DATABASE_URL must be a PostgreSQL connection URL");
            }
            String host = databaseUri.getHost();
            String path = databaseUri.getPath();
            if (host == null || path == null || path.length() < 2) {
                throw new IllegalStateException("DATABASE_URL must include a database host and name");
            }
            Properties properties = new Properties();
            String[] credentials = databaseUri.getUserInfo() == null
                    ? new String[0]
                    : databaseUri.getUserInfo().split(":", 2);
            if (credentials.length == 2) {
                properties.setProperty("user", credentials[0]);
                properties.setProperty("password", credentials[1]);
            }
            properties.setProperty("sslmode", "require");
            String port = databaseUri.getPort() > 0 ? ":" + databaseUri.getPort() : "";
            return DriverManager.getConnection("jdbc:postgresql://" + host + port + path, properties);
        }

        Properties properties = new Properties();
        properties.setProperty("user", required("PGUSER"));
        properties.setProperty("password", required("PGPASSWORD"));
        properties.setProperty("sslmode", "require");
        String host = required("PGHOST");
        String port = System.getenv().getOrDefault("PGPORT", "5432");
        String database = required("PGDATABASE");
        return DriverManager.getConnection("jdbc:postgresql://" + host + ":" + port + "/" + database, properties);
    }

    private static void initializeDatabase() throws SQLException {
        try (Connection connection = database();
             PreparedStatement statement = connection.prepareStatement(
                     "CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL, password_hash TEXT NOT NULL, password_salt BYTEA NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")) {
            statement.executeUpdate();
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalStateException(name + " is not configured");
        return value;
    }

    private static String hash(String password, byte[] salt) {
        try {
            KeySpec spec = new PBEKeySpec(password.toCharArray(), salt, ITERATIONS, KEY_LENGTH);
            byte[] encoded = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            return Base64.getEncoder().encodeToString(encoded);
        } catch (NoSuchAlgorithmException | InvalidKeySpecException error) {
            throw new IllegalStateException("Password hashing is unavailable", error);
        }
    }

    private static Map<String, String> parseForm(HttpExchange exchange) throws IOException {
        try (InputStream input = exchange.getRequestBody()) {
            String body = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            Map<String, String> values = new HashMap<>();
            for (String pair : body.split("&")) {
                String[] parts = pair.split("=", 2);
                if (parts.length == 2) values.put(URLDecoder.decode(parts[0], StandardCharsets.UTF_8), URLDecoder.decode(parts[1], StandardCharsets.UTF_8));
            }
            return values;
        }
    }

    private static boolean isPost(HttpExchange exchange) throws IOException {
        if ("POST".equalsIgnoreCase(exchange.getRequestMethod())) return true;
        exchange.getResponseHeaders().set("Allow", "POST");
        respond(exchange, 405, "Method not allowed");
        return false;
    }

    private static void respond(HttpExchange exchange, int status, String message) throws IOException {
        byte[] body = message.getBytes(StandardCharsets.UTF_8);

        // Inject Essential Global CORS Metadata Elements
        exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
        exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
        exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type, Authorization");

        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");

        // HEAD requests (e.g. Render's health check pinging "/") must carry the
        // same Content-Length a GET would return, but no body. Passing the real
        // body length to sendResponseHeaders on a HEAD request triggers a JDK
        // warning, so we set Content-Length manually and send -1 (no body) instead.
        if ("HEAD".equalsIgnoreCase(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Content-Length", String.valueOf(body.length));
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
            return;
        }

        exchange.sendResponseHeaders(status, body.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
    }
}