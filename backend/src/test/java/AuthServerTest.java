import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpPrincipal;
import org.junit.Test;
import org.junit.Assume;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.net.URI;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

public class AuthServerTest {
    @Test
    public void parseFormDecodesValuesAndKeepsEmbeddedEquals() throws Exception {
        TestExchange exchange = new TestExchange("POST", "/", "email=ada%40example.com&token=a%3Db&empty=&ignored");

        Map<?, ?> values = (Map<?, ?>) invoke("parseForm", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals("ada@example.com", values.get("email"));
        assertEquals("a=b", values.get("token"));
        assertEquals("", values.get("empty"));
        assertFalse(values.containsKey("ignored"));
    }

    @Test
    public void passwordHashIsStableAndUsesTheSuppliedSalt() throws Exception {
        byte[] firstSalt = new byte[16];
        Arrays.fill(firstSalt, (byte) 7);
        byte[] secondSalt = firstSalt.clone();
        secondSalt[0] = 8;

        String firstHash = (String) invoke("hash", new Class<?>[]{String.class, byte[].class}, "a strong password", firstSalt);
        String repeatedHash = (String) invoke("hash", new Class<?>[]{String.class, byte[].class}, "a strong password", firstSalt);
        String differentSaltHash = (String) invoke("hash", new Class<?>[]{String.class, byte[].class}, "a strong password", secondSalt);

        assertEquals(firstHash, repeatedHash);
        assertNotEquals(firstHash, differentSaltHash);
        assertEquals(32, Base64.getDecoder().decode(firstHash).length);
    }

    @Test
    public void jsonEscapeHandlesQuotesSlashesAndControlCharacters() throws Exception {
        String escaped = (String) invoke("jsonEscape", new Class<?>[]{String.class}, "\"\\\n\r\t");

        assertEquals("\\\"\\\\\\n\\r\\t", escaped);
    }

    @Test
    public void responseSetsSecurityHeadersAndWritesBody() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/", "");

        invoke("respond", new Class<?>[]{HttpExchange.class, int.class, String.class}, exchange, 202, "accepted");

        assertEquals(202, exchange.responseCode);
        assertEquals("text/plain; charset=UTF-8", exchange.responseHeaders.getFirst("Content-Type"));
        assertEquals("no-store", exchange.responseHeaders.getFirst("Cache-Control"));
        assertEquals("*", exchange.responseHeaders.getFirst("Access-Control-Allow-Origin"));
        assertEquals("accepted", exchange.responseBody.toString("UTF-8"));
        assertEquals(8L, exchange.responseLength);
    }

    @Test
    public void headResponseSetsContentLengthWithoutWritingBody() throws Exception {
        TestExchange exchange = new TestExchange("HEAD", "/", "");

        invoke("respond", new Class<?>[]{HttpExchange.class, int.class, String.class}, exchange, 200, "ready");

        assertEquals(200, exchange.responseCode);
        assertEquals("5", exchange.responseHeaders.getFirst("Content-Length"));
        assertEquals(-1L, exchange.responseLength);
        assertEquals(0, exchange.responseBody.size());
    }

    @Test
    public void nonPostRequestIsRejected() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/api/register", "");

        boolean accepted = (boolean) invoke("isPost", new Class<?>[]{HttpExchange.class}, exchange);

        assertFalse(accepted);
        assertEquals("POST", exchange.responseHeaders.getFirst("Allow"));
        assertEquals(405, exchange.responseCode);
        assertEquals("Method not allowed", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void headRequestForMissingRootFileReturnsHealthyEmptyResponse() throws Exception {
        TestExchange exchange = new TestExchange("HEAD", "/", "");

        invoke("staticFile", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(200, exchange.responseCode);
        assertEquals("0", exchange.responseHeaders.getFirst("Content-Length"));
        assertEquals(-1L, exchange.responseLength);
        assertEquals(0, exchange.responseBody.size());
    }

    @Test
    public void staticFileHandlerRejectsPathsOutsideBackendRoot() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/../render.yaml", "");

        invoke("staticFile", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(404, exchange.responseCode);
        assertEquals("Not found", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void registerRejectsInvalidCredentialsBeforeDatabaseAccess() throws Exception {
        TestExchange exchange = new TestExchange("POST", "/api/register",
                "email=invalid&password=123456&first_name=Ada&last_name=Lovelace");

        invoke("register", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(400, exchange.responseCode);
        assertEquals("Invalid email or password", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void registerRejectsPasswordShorterThanSixCharacters() throws Exception {
        TestExchange exchange = new TestExchange("POST", "/api/register",
                "email=ada%40example.com&password=12345&first_name=Ada&last_name=Lovelace");

        invoke("register", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(400, exchange.responseCode);
        assertEquals("Invalid email or password", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void registerRejectsPasswordLongerThan128Characters() throws Exception {
        String password = "a".repeat(129);
        TestExchange exchange = new TestExchange("POST", "/api/register",
                "email=ada%40example.com&password=" + password + "&first_name=Ada&last_name=Lovelace");

        invoke("register", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(400, exchange.responseCode);
        assertEquals("Invalid email or password", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void registerRequiresFirstAndLastNameBeforeDatabaseAccess() throws Exception {
        TestExchange exchange = new TestExchange("POST", "/api/register",
                "email=ada%40example.com&password=correct-horse");

        invoke("register", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(400, exchange.responseCode);
        assertEquals("First and last name are required", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void registerRequiresFirstNameWhenLastNameIsPresent() throws Exception {
        TestExchange exchange = new TestExchange("POST", "/api/register",
                "email=ada%40example.com&password=correct-horse&last_name=Lovelace");

        invoke("register", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(400, exchange.responseCode);
        assertEquals("First and last name are required", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void registerRequiresLastNameWhenFirstNameIsPresent() throws Exception {
        TestExchange exchange = new TestExchange("POST", "/api/register",
                "email=ada%40example.com&password=correct-horse&first_name=Ada");

        invoke("register", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(400, exchange.responseCode);
        assertEquals("First and last name are required", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void loginRejectsNonPostRequestBeforeDatabaseAccess() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/api/login", "");

        invoke("login", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(405, exchange.responseCode);
        assertEquals("POST", exchange.responseHeaders.getFirst("Allow"));
    }

    @Test
    public void postMethodCheckIsCaseInsensitive() throws Exception {
        TestExchange exchange = new TestExchange("pOsT", "/api/register", "");

        boolean accepted = (boolean) invoke("isPost", new Class<?>[]{HttpExchange.class}, exchange);

        assertTrue(accepted);
        assertEquals(-1, exchange.responseCode);
    }

    @Test
    public void staticFileRejectsUnsupportedMethod() throws Exception {
        TestExchange exchange = new TestExchange("PUT", "/", "");

        invoke("staticFile", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(405, exchange.responseCode);
        assertEquals("GET, HEAD", exchange.responseHeaders.getFirst("Allow"));
    }

    @Test
    public void staticFileReturnsNotFoundForMissingPath() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/missing-test-resource.txt", "");

        invoke("staticFile", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(404, exchange.responseCode);
        assertEquals("Not found", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void staticFileServesFileInsideBackendRoot() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/pom.xml", "");

        invoke("staticFile", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(200, exchange.responseCode);
        assertTrue(exchange.responseHeaders.getFirst("Content-Type") != null);
        assertEquals("nosniff", exchange.responseHeaders.getFirst("X-Content-Type-Options"));
        assertTrue(exchange.responseBody.size() > 0);
    }

    @Test
    public void staticFileHeadForExistingFileSendsLengthWithoutBody() throws Exception {
        TestExchange exchange = new TestExchange("HEAD", "/pom.xml", "");

        invoke("staticFile", new Class<?>[]{HttpExchange.class}, exchange);

        assertEquals(200, exchange.responseCode);
        assertTrue(Integer.parseInt(exchange.responseHeaders.getFirst("Content-Length")) > 0);
        assertEquals(-1L, exchange.responseLength);
        assertEquals(0, exchange.responseBody.size());
    }

    @Test
    public void jsonResponseUsesJsonContentType() throws Exception {
        TestExchange exchange = new TestExchange("GET", "/api/login", "");

        invoke("respondJson", new Class<?>[]{HttpExchange.class, int.class, String.class},
                exchange, 200, "{\"message\":\"Signed in\"}");

        assertEquals(200, exchange.responseCode);
        assertEquals("application/json; charset=UTF-8", exchange.responseHeaders.getFirst("Content-Type"));
        assertEquals("{\"message\":\"Signed in\"}", exchange.responseBody.toString("UTF-8"));
    }

    @Test
    public void configuredDatabaseCanReadUsersTable() throws Exception {
        String databaseUrl = System.getenv("DATABASE_URL");
        Assume.assumeTrue(databaseUrl != null && !databaseUrl.isBlank());

        boolean usersTableExists;
        try (Connection connection = (Connection) invoke("database", new Class<?>[0]);
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                     "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                             + "WHERE table_schema = 'public' AND table_name = 'users')")) {
            usersTableExists = result.next() && result.getBoolean(1);
        } catch (Exception error) {
            throw new AssertionError("Read-only database check failed (" + error.getClass().getSimpleName() + ").");
        }
        assertTrue("The public.users table was not found.", usersTableExists);
    }

    private static Object invoke(String methodName, Class<?>[] parameterTypes, Object... arguments) throws Exception {
        Method method = AuthServer.class.getDeclaredMethod(methodName, parameterTypes);
        method.setAccessible(true);
        try {
            return method.invoke(null, arguments);
        } catch (InvocationTargetException error) {
            Throwable cause = error.getCause();
            if (cause instanceof Exception) {
                throw (Exception) cause;
            }
            if (cause instanceof Error) {
                throw (Error) cause;
            }
            throw error;
        }
    }

    private static final class TestExchange extends HttpExchange {
        private final String requestMethod;
        private final URI requestUri;
        private final Headers requestHeaders = new Headers();
        private final Headers responseHeaders = new Headers();
        private final ByteArrayInputStream requestBody;
        private final ByteArrayOutputStream responseBody = new ByteArrayOutputStream();
        private int responseCode = -1;
        private long responseLength = -1;

        private TestExchange(String requestMethod, String requestUri, String requestBody) {
            this.requestMethod = requestMethod;
            this.requestUri = URI.create(requestUri);
            this.requestBody = new ByteArrayInputStream(requestBody.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }

        @Override
        public Headers getRequestHeaders() {
            return requestHeaders;
        }

        @Override
        public Headers getResponseHeaders() {
            return responseHeaders;
        }

        @Override
        public URI getRequestURI() {
            return requestUri;
        }

        @Override
        public String getRequestMethod() {
            return requestMethod;
        }

        @Override
        public HttpContext getHttpContext() {
            return null;
        }

        @Override
        public void close() {
        }

        @Override
        public InputStream getRequestBody() {
            return requestBody;
        }

        @Override
        public OutputStream getResponseBody() {
            return responseBody;
        }

        @Override
        public void sendResponseHeaders(int status, long responseLength) {
            this.responseCode = status;
            this.responseLength = responseLength;
        }

        @Override
        public InetSocketAddress getRemoteAddress() {
            return null;
        }

        @Override
        public int getResponseCode() {
            return responseCode;
        }

        @Override
        public InetSocketAddress getLocalAddress() {
            return null;
        }

        @Override
        public String getProtocol() {
            return "HTTP/1.1";
        }

        @Override
        public Object getAttribute(String name) {
            return null;
        }

        @Override
        public void setAttribute(String name, Object value) {
        }

        @Override
        public void setStreams(InputStream input, OutputStream output) {
        }

        @Override
        public HttpPrincipal getPrincipal() {
            return null;
        }
    }
}