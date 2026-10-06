import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.KeySpec;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Base64;
import java.util.Deque;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class AuthServer {
    private static final SecureRandom RANDOM = new SecureRandom();

    // New accounts use the current OWASP-recommended count. Existing accounts keep the
    // count they were created with (stored per-user) and are upgraded on next login.
    private static final int ITERATIONS = 600_000;
    private static final int LEGACY_ITERATIONS = 210_000;
    private static final int KEY_LENGTH = 256;

    private static final int MAX_BODY = 8 * 1024;
    private static final byte[] DUMMY_SALT = new byte[16];

    private static final Pattern EMAIL =
            Pattern.compile("^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\\.[A-Za-z]{2,}$");
    private static final Pattern NAME =
            Pattern.compile("^\\p{L}+(?:[ '\\-]\\p{L}+)*$");

    // Rate limits
    private static final long LOGIN_WINDOW_MS = 15 * 60_000L;
    private static final int LOGIN_MAX_FAILS_PER_EMAIL = 5;
    private static final int LOGIN_MAX_FAILS_PER_IP = 20;
    private static final long REGISTER_WINDOW_MS = 60 * 60_000L;
    private static final int REGISTER_MAX_PER_IP = 10;
    private static final Limiter LIMITER = new Limiter();

    // Optional: lets the Streamlit server forward the real end-user IP (see clientIp).
    private static final String API_SECRET = System.getenv("API_SHARED_SECRET");
    private static final Pattern IP_LIKE = Pattern.compile("^[0-9A-Fa-f:.]{3,45}$");
    private static final Pattern IPV4 = Pattern.compile(
            "^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$");

    // Header carrying the visitor's IP that the edge in front of this service sets itself.
    // Render sits behind Cloudflare, which OVERWRITES CF-Connecting-IP, so clients cannot forge
    // it. X-Forwarded-For is deliberately NOT used: a client can pre-fill it with fake values.
    // Set CLIENT_IP_HEADER to another header name, or to "none" to disable this source.
    private static final String CLIENT_IP_HEADER = clientIpHeaderName();

    // Password policy for NEW accounts. Existing accounts can still sign in with what they have.
    private static final int PASSWORD_MIN_LENGTH = 8;
    private static final int PASSWORD_MAX_LENGTH = 128;
    private static final Set<String> COMMON_PASSWORDS = Set.copyOf(Arrays.asList(
            "password", "password1", "password12", "password123", "password1234", "passw0rd",
            "p@ssw0rd", "p@ssword", "pa$$word", "12345678", "123456789", "1234567890",
            "123123123", "11111111", "111111111", "00000000", "87654321", "987654321",
            "12341234", "12121212", "qwertyui", "qwerty123", "qwertyuiop", "qwerty1234",
            "asdfghjk", "asdfghjkl", "zxcvbnm1", "1q2w3e4r", "1qaz2wsx", "zaq12wsx",
            "qazwsxedc", "q1w2e3r4", "abc12345", "abcd1234", "abcdefgh", "iloveyou",
            "iloveyou1", "letmein1", "welcome1", "welcome123", "admin123", "administrator",
            "monkey123", "dragon123", "football", "baseball", "basketball", "superman",
            "trustno1", "sunshine", "princess", "starwars", "whatever", "mustang1",
            "michael1", "jennifer", "computer", "internet", "changeme", "default123",
            "netchill", "netchill1", "netchill123", "netflix1", "netflix123", "netflixchill"));

    // CPU protection. A PBKDF2 hash is deliberately expensive, so only a few may run at the
    // same time and the whole API only accepts so many login/register attempts per minute.
    private static final int HASH_CONCURRENCY = envInt("HASH_CONCURRENCY", 2, 1, 8);
    private static final int GLOBAL_AUTH_PER_MINUTE = envInt("GLOBAL_AUTH_PER_MINUTE", 120, 10, 100_000);
    private static final long HASH_WAIT_MS = 4_000L;
    private static final Semaphore HASH_SLOTS = new Semaphore(HASH_CONCURRENCY, true);

    private AuthServer() {
    }

    /** Thrown for client mistakes; turned into a 400 response by safe(). */
    private static final class BadRequest extends RuntimeException {
        BadRequest(String message) {
            super(message);
        }
    }

    /** Thrown when too many password hashes are already running; turned into a 429 by safe(). */
    private static final class Busy extends RuntimeException {
        Busy() {
            super("Server is busy", null, false, false);
        }
    }

    /** Small in-memory sliding-window limiter. */
    private static final class Limiter {
        private final Map<String, Deque<Long>> hits = new ConcurrentHashMap<>();

        boolean isLimited(String key, int max, long windowMs) {
            Deque<Long> queue = hits.get(key);
            if (queue == null) return false;
            long now = System.currentTimeMillis();
            synchronized (queue) {
                while (!queue.isEmpty() && now - queue.peekFirst() > windowMs) queue.pollFirst();
                return queue.size() >= max;
            }
        }

        void record(String key) {
            Deque<Long> queue = hits.computeIfAbsent(key, k -> new ArrayDeque<>());
            synchronized (queue) {
                queue.addLast(System.currentTimeMillis());
            }
        }

        void clear(String key) {
            hits.remove(key);
        }

        void cleanup(long maxAgeMs) {
            long now = System.currentTimeMillis();
            hits.entrySet().removeIf(entry -> {
                synchronized (entry.getValue()) {
                    Long last = entry.getValue().peekLast();
                    return last == null || now - last > maxAgeMs;
                }
            });
        }
    }

    public static void main(String[] args) throws IOException, SQLException {
        int port = Integer.parseInt(System.getenv().getOrDefault("API_PORT",
            System.getenv().getOrDefault("PORT", "8080")));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);

        // PBKDF2 is CPU-heavy; a pool keeps one slow login from freezing the whole API.
        server.setExecutor(Executors.newFixedThreadPool(8));

        // No static files are served. "/" only answers health checks (GET and HEAD).
        server.createContext("/", safe(exchange -> {
            if ("/".equals(exchange.getRequestURI().getPath())) {
                respond(exchange, 200, "OK");
            } else {
                respond(exchange, 404, "Not found");
            }
        }));
        server.createContext("/api/register", safe(AuthServer::register));
        server.createContext("/api/login", safe(AuthServer::login));

        // Periodically drop stale rate-limit entries so the map can't grow forever.
        ScheduledExecutorService cleaner = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(task, "limiter-cleanup");
            thread.setDaemon(true);
            return thread;
        });
        cleaner.scheduleAtFixedRate(() -> LIMITER.cleanup(2 * 60 * 60_000L), 10, 10, TimeUnit.MINUTES);

        // Open the port FIRST. Render's port scan fails the deploy (and users see 502s) if
        // the process never listens, e.g. because the database was slow or unreachable.
        // The schema is set up in the background, retrying until the database answers.
        server.start();
        System.out.println("Auth API listening on port " + port);

        Thread initializer = new Thread(AuthServer::initializeDatabaseWithRetry, "db-init");
        initializer.setDaemon(true);
        initializer.start();
    }

    /** Keeps trying to prepare the schema; failures are printed so they show up in the logs. */
    private static void initializeDatabaseWithRetry() {
        for (int attempt = 1; ; attempt++) {
            try {
                initializeDatabase();
                System.out.println("Database ready (attempt " + attempt + ")");
                return;
            } catch (Exception error) {
                System.err.println("Database init failed (attempt " + attempt + "): " + error);
                try {
                    Thread.sleep(Math.min(30_000L, 5_000L * attempt));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    /** Wraps a handler so no exception escapes and drops the connection. */
    private static HttpHandler safe(HttpHandler handler) {
        return exchange -> {
            try {
                handler.handle(exchange);
            } catch (BadRequest error) {
                respond(exchange, 400, error.getMessage());
            } catch (Busy error) {
                exchange.getResponseHeaders().set("Retry-After", "10");
                respond(exchange, 429, "Server is busy. Please try again shortly.");
            } catch (Exception error) {
                error.printStackTrace();
                try {
                    respond(exchange, 500, "Server error");
                } catch (Exception ignored) {
                    exchange.close();
                }
            }
        };
    }

    private static void register(HttpExchange exchange) throws IOException {
        if (!isPost(exchange)) return;
        if (!allowGlobalAttempt(exchange)) return;

        String ip = clientIp(exchange);
        String ipKey = "register:ip:" + ip;
        if (LIMITER.isLimited(ipKey, REGISTER_MAX_PER_IP, REGISTER_WINDOW_MS)) {
            respond(exchange, 429, "Too many attempts. Try again later.");
            return;
        }
        LIMITER.record(ipKey);

        Map<String, String> data = parseForm(exchange);
        String email = data.getOrDefault("email", "").trim().toLowerCase(Locale.ROOT);
        String password = data.getOrDefault("password", "");
        String firstName = data.getOrDefault("first_name", "").trim();
        String lastName = data.getOrDefault("last_name", "").trim();
        String dobRaw = data.getOrDefault("date_of_birth", "").trim();

        if (email.length() > 254 || !EMAIL.matcher(email).matches()
                || password.length() > PASSWORD_MAX_LENGTH) {
            respond(exchange, 400, "Invalid email or password");
            return;
        }
        String passwordProblem = passwordProblem(password, email);
        if (passwordProblem != null) {
            respond(exchange, 400, passwordProblem);
            return;
        }
        if (!validName(firstName) || !validName(lastName)) {
            respond(exchange, 400, "Names may contain only letters, spaces, apostrophes and hyphens (max 50)");
            return;
        }

        // Date of birth is optional; a missing/malformed/implausible value never blocks signup.
        java.sql.Date dob = null;
        if (!dobRaw.isEmpty()) {
            try {
                LocalDate parsed = LocalDate.parse(dobRaw); // yyyy-MM-dd
                if (!parsed.isAfter(LocalDate.now()) && parsed.getYear() >= 1900) {
                    dob = java.sql.Date.valueOf(parsed);
                }
            } catch (RuntimeException ignored) {
                dob = null;
            }
        }

        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        try (Connection connection = database();
             PreparedStatement statement = connection.prepareStatement(
                     "INSERT INTO users (email, password_hash, password_salt, password_iterations, first_name, last_name, date_of_birth) "
                             + "VALUES (?, ?, ?, ?, ?, ?, ?)")) {
            statement.setString(1, email);
            statement.setString(2, hashLimited(password, salt, ITERATIONS));
            statement.setBytes(3, salt);
            statement.setInt(4, ITERATIONS);
            statement.setString(5, firstName);
            statement.setString(6, lastName);
            if (dob != null) {
                statement.setDate(7, dob);
            } else {
                statement.setNull(7, java.sql.Types.DATE);
            }
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
        if (!allowGlobalAttempt(exchange)) return;

        Map<String, String> data = parseForm(exchange);
        String email = data.getOrDefault("email", "").trim().toLowerCase(Locale.ROOT);
        String password = data.getOrDefault("password", "");
        String ip = clientIp(exchange);
        String emailKey = "login:email:" + email;
        String ipKey = "login:ip:" + ip;

        if (LIMITER.isLimited(emailKey, LOGIN_MAX_FAILS_PER_EMAIL, LOGIN_WINDOW_MS)
                || LIMITER.isLimited(ipKey, LOGIN_MAX_FAILS_PER_IP, LOGIN_WINDOW_MS)) {
            respond(exchange, 429, "Too many attempts. Try again later.");
            return;
        }

        // Reject junk before doing expensive hashing or touching the database.
        if (email.length() > 254 || !EMAIL.matcher(email).matches()
                || password.isEmpty() || password.length() > 128) {
            LIMITER.record(ipKey);
            respond(exchange, 401, "Invalid email or password");
            return;
        }

        try (Connection connection = database();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT password_hash, password_salt, password_iterations, first_name FROM users WHERE email = ?")) {
            statement.setString(1, email);

            boolean authenticated = false;
            boolean needsUpgrade = false;
            String firstName = null;

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    int iterations = result.getInt("password_iterations");
                    if (iterations <= 0) iterations = LEGACY_ITERATIONS;
                    String computed = hashLimited(password, result.getBytes("password_salt"), iterations);
                    authenticated = MessageDigest.isEqual(
                            computed.getBytes(StandardCharsets.UTF_8),
                            result.getString("password_hash").getBytes(StandardCharsets.UTF_8));
                    if (authenticated) {
                        needsUpgrade = iterations < ITERATIONS;
                        firstName = result.getString("first_name");
                    }
                } else {
                    // Unknown email: do equivalent work so response time doesn't reveal it.
                    hashLimited(password, DUMMY_SALT, ITERATIONS);
                }
            }

            if (!authenticated) {
                LIMITER.record(emailKey);
                LIMITER.record(ipKey);
                respond(exchange, 401, "Invalid email or password");
                return;
            }

            LIMITER.clear(emailKey);

            if (needsUpgrade) {
                // Transparently re-hash with the stronger iteration count and a fresh salt.
                try {
                    byte[] newSalt = new byte[16];
                    RANDOM.nextBytes(newSalt);
                    try (PreparedStatement upgrade = connection.prepareStatement(
                            "UPDATE users SET password_hash = ?, password_salt = ?, password_iterations = ? WHERE email = ?")) {
                        upgrade.setString(1, hashLimited(password, newSalt, ITERATIONS));
                        upgrade.setBytes(2, newSalt);
                        upgrade.setInt(3, ITERATIONS);
                        upgrade.setString(4, email);
                        upgrade.executeUpdate();
                    }
                } catch (SQLException upgradeError) {
                    upgradeError.printStackTrace(); // login still succeeds
                } catch (Busy skipped) {
                    // Server is busy hashing; the upgrade simply happens on the next login.
                }
            }

            // Legacy rows may hold unvalidated names; only return safe values.
            if (firstName == null || firstName.isBlank() || !validName(firstName.trim())) {
                String localPart = email.substring(0, email.indexOf('@')); // EMAIL regex guarantees '@'
                firstName = Character.toUpperCase(localPart.charAt(0)) + localPart.substring(1);
            } else {
                firstName = firstName.trim();
            }

            String json = "{\"message\":\"Signed in\",\"first_name\":\"" + jsonEscape(firstName) + "\"}";
            respondJson(exchange, 200, json);
        } catch (SQLException error) {
            error.printStackTrace();
            respond(exchange, 500, "Database error");
        }
    }

    private static boolean validName(String value) {
        return value.length() >= 1 && value.length() <= 50 && NAME.matcher(value).matches();
    }

    /**
     * Works out which visitor a request belongs to, for rate limiting. Sources, in order:
     * 1. The IP the Streamlit frontend forwards, but only if it proves who it is with the
     *    shared secret (so nobody else can claim an IP).
     * 2. The header the edge sets itself (CF-Connecting-IP on Render); clients cannot forge it.
     * 3. The socket address (behind Render this is the proxy, so unknown callers share one bucket).
     * X-Forwarded-For is never used because a client can send any value in it.
     */
    private static String clientIp(HttpExchange exchange) {
        Headers headers = exchange.getRequestHeaders();

        String key = headers.getFirst("X-Api-Key");
        if (API_SECRET != null && !API_SECRET.isBlank() && key != null
                && MessageDigest.isEqual(key.getBytes(StandardCharsets.UTF_8),
                                         API_SECRET.getBytes(StandardCharsets.UTF_8))) {
            String forwarded = normalizeIp(headers.getFirst("X-Client-IP"));
            if (forwarded != null) return forwarded;
        }

        if (CLIENT_IP_HEADER != null) {
            String edge = normalizeIp(headers.getFirst(CLIENT_IP_HEADER));
            if (edge != null) return edge;
        }

        InetSocketAddress remote = exchange.getRemoteAddress();
        String socket = remote == null ? null : normalizeIp(remote.getAddress().getHostAddress());
        return socket != null ? socket : "unknown";
    }

    /**
     * Returns a canonical rate-limit key for an IP address, or null if the text is not a valid
     * IP. IPv6 addresses are grouped by their /64 prefix so one connection cannot rotate through
     * billions of addresses to dodge the limits. Never performs a DNS lookup.
     */
    static String normalizeIp(String raw) {
        if (raw == null) return null;
        String value = raw.trim();
        if (value.length() < 3 || value.length() > 45) return null;
        if (IPV4.matcher(value).matches()) return value;
        if (value.indexOf(':') >= 0 && IP_LIKE.matcher(value).matches()) {
            try {
                // Contains ':' so Java parses it as an IPv6 literal and never queries DNS.
                InetAddress address = InetAddress.getByName(value);
                byte[] bytes = address.getAddress();
                if (bytes.length == 4) return address.getHostAddress(); // IPv4-mapped IPv6
                return String.format("%02x%02x:%02x%02x:%02x%02x:%02x%02x::/64",
                        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7]);
            } catch (UnknownHostException invalid) {
                return null;
            }
        }
        return null;
    }

    private static String clientIpHeaderName() {
        String configured = System.getenv("CLIENT_IP_HEADER");
        if (configured == null) return "CF-Connecting-IP";
        configured = configured.trim();
        if (configured.isEmpty() || "none".equalsIgnoreCase(configured)) return null;
        return configured;
    }

    /** Reads an integer environment variable, falling back to a default if missing or invalid. */
    private static int envInt(String name, int fallback, int min, int max) {
        try {
            String raw = System.getenv(name);
            if (raw == null || raw.isBlank()) return fallback;
            int value = Integer.parseInt(raw.trim());
            return Math.max(min, Math.min(max, value));
        } catch (NumberFormatException invalid) {
            return fallback;
        }
    }

    /** Returns a user-facing reason if the password is not acceptable for a new account, else null. */
    static String passwordProblem(String password, String email) {
        if (password.length() < PASSWORD_MIN_LENGTH) {
            return "Password must be at least " + PASSWORD_MIN_LENGTH + " characters.";
        }
        String lower = password.toLowerCase(Locale.ROOT);
        String localPart = email.contains("@") ? email.substring(0, email.indexOf('@')) : email;
        if (lower.equals(email) || lower.equals(localPart)) {
            return "Password can't be the same as your email address.";
        }
        if (COMMON_PASSWORDS.contains(lower)) {
            return "That password is too common. Please choose a less predictable one.";
        }
        if (password.chars().distinct().count() < 4) {
            return "That password is too repetitive. Please choose a less predictable one.";
        }
        return null;
    }

    /** Backstop for the whole API: caps login+register attempts per minute across all clients. */
    private static boolean allowGlobalAttempt(HttpExchange exchange) throws IOException {
        if (LIMITER.isLimited("global:auth", GLOBAL_AUTH_PER_MINUTE, 60_000L)) {
            exchange.getResponseHeaders().set("Retry-After", "30");
            respond(exchange, 429, "Server is busy. Please try again shortly.");
            return false;
        }
        LIMITER.record("global:auth");
        return true;
    }

    /** Like hash(), but at most HASH_CONCURRENCY run at once; others wait briefly, then give up. */
    static String hashLimited(String password, byte[] salt, int iterations) {
        boolean acquired;
        try {
            acquired = HASH_SLOTS.tryAcquire(HASH_WAIT_MS, TimeUnit.MILLISECONDS);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new Busy();
        }
        if (!acquired) throw new Busy();
        try {
            return hash(password, salt, iterations);
        } finally {
            HASH_SLOTS.release();
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
        try (Connection connection = database()) {
            try (PreparedStatement statement = connection.prepareStatement(
                    "CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL, password_hash TEXT NOT NULL, password_salt BYTEA NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")) {
                statement.executeUpdate();
            }
            // Idempotent migration (safe on every startup). Existing rows get
            // password_iterations = 210000, which matches how they were hashed.
            try (PreparedStatement statement = connection.prepareStatement(
                    "ALTER TABLE users "
                            + "ADD COLUMN IF NOT EXISTS first_name VARCHAR(100), "
                            + "ADD COLUMN IF NOT EXISTS last_name VARCHAR(100), "
                            + "ADD COLUMN IF NOT EXISTS date_of_birth DATE, "
                            + "ADD COLUMN IF NOT EXISTS password_iterations INTEGER NOT NULL DEFAULT 210000")) {
                statement.executeUpdate();
            }
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalStateException(name + " is not configured");
        return value;
    }

    private static String hash(String password, byte[] salt, int iterations) {
        try {
            KeySpec spec = new PBEKeySpec(password.toCharArray(), salt, iterations, KEY_LENGTH);
            byte[] encoded = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            return Base64.getEncoder().encodeToString(encoded);
        } catch (NoSuchAlgorithmException | InvalidKeySpecException error) {
            throw new IllegalStateException("Password hashing is unavailable", error);
        }
    }

    private static Map<String, String> parseForm(HttpExchange exchange) throws IOException {
        try (InputStream input = exchange.getRequestBody()) {
            byte[] bytes = input.readNBytes(MAX_BODY + 1);
            if (bytes.length > MAX_BODY) throw new BadRequest("Request too large");
            Map<String, String> values = new HashMap<>();
            try {
                for (String pair : new String(bytes, StandardCharsets.UTF_8).split("&")) {
                    String[] parts = pair.split("=", 2);
                    if (parts.length == 2) {
                        values.put(URLDecoder.decode(parts[0], StandardCharsets.UTF_8),
                                   URLDecoder.decode(parts[1], StandardCharsets.UTF_8));
                    }
                }
            } catch (IllegalArgumentException error) {
                throw new BadRequest("Malformed request");
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
        writeResponse(exchange, status, "text/plain; charset=UTF-8", message.getBytes(StandardCharsets.UTF_8));
    }

    private static void respondJson(HttpExchange exchange, int status, String json) throws IOException {
        writeResponse(exchange, status, "application/json; charset=UTF-8", json.getBytes(StandardCharsets.UTF_8));
    }

    private static void writeResponse(HttpExchange exchange, int status, String contentType, byte[] body) throws IOException {
        // No CORS headers: Streamlit calls this API server-to-server, so browsers never need access.
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");

        // HEAD (e.g. Render's health check) gets the same Content-Length a GET would, but no body.
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

    /** JSON string escaping, including all control characters below 0x20. */
    private static String jsonEscape(String value) {
        StringBuilder out = new StringBuilder(value.length() + 8);
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\': out.append("\\\\"); break;
                case '"':  out.append("\\\""); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
            }
        }
        return out.toString();
    }
}