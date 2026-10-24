package com.flowconsole;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.flowconsole.asset.*;
import com.flowconsole.mapper.*;
import com.flowconsole.platform.BoundedHttp;
import com.flowconsole.product.*;
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class HttpSafetyTest {
  @Test
  void responseSizeLimitIsEnforcedBeforeReturningBytes() throws Exception {
    var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext(
        "/",
        exchange -> {
          var bytes = new byte[1000];
          exchange.sendResponseHeaders(200, bytes.length);
          exchange.getResponseBody().write(bytes);
          exchange.close();
        });
    server.start();
    try {
      var request =
          HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getAddress().getPort()))
              .timeout(Duration.ofSeconds(2))
              .GET()
              .build();
      assertThrows(
          Exception.class, () -> BoundedHttp.send(HttpClient.newHttpClient(), request, 100, 2));
    } finally {
      server.stop(0);
    }
  }

  @Test
  void unavailableModelsCannotCallProvidersOrInventAnImage() {
    var files = mock(AssetService.class);
    var db = mock(CatalogMapper.class);
    var catalog = mock(CatalogService.class);
    var service = new ImageOperations(new MockEnvironment(), db, catalog, files, null);
    assertEquals(
        "MODEL_NOT_CONFIGURED",
        assertThrows(
                ApiException.class,
                () ->
                    service.execute(
                        1, "fixture-job-123", java.util.Map.of("operation", "MODEL"), 1))
            .code);
    assertEquals(
        "COMPUTE_NOT_CONFIGURED",
        assertThrows(
                ApiException.class,
                () ->
                    service.execute(1, "fixture-job-123", java.util.Map.of("operation", "OCR"), 1))
            .code);
    verifyNoInteractions(files, db, catalog);
  }
}
