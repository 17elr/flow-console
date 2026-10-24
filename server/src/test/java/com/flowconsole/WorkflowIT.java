package com.flowconsole;

import static com.flowconsole.mapper.CatalogMapper.Table.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.flowconsole.asset.*;
import com.flowconsole.auth.*;
import com.flowconsole.config.QueueConfig;
import com.flowconsole.importdata.*;
import com.flowconsole.mapper.*;
import com.flowconsole.platform.*;
import com.flowconsole.product.*;
import com.flowconsole.task.*;
import com.sun.net.httpserver.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.core.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest(
    properties = {
      "flow.schedulers=false",
      "flow.real-publishing=true",
      "flow.app-key=fixture-key",
      "flow.app-secret=fixture-secret",
      "flow.interval-ms=1",
      "flow.aliexpress-create-path=/open/fixture/aliexpress/create",
      "flow.aliexpress-query-path=/open/fixture/aliexpress/query",
      "flow.assets=target/it-assets",
      "flow.bootstrap-password=integration-admin-pass"
    })
@AutoConfigureMockMvc
@ActiveProfiles("integration")
@EnabledIfEnvironmentVariable(named = "RUN_INTEGRATION", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class WorkflowIT {
  static final HttpServer HTTP;
  static final AtomicInteger CREATES = new AtomicInteger();
  static final AtomicBoolean LOSE_RESPONSE = new AtomicBoolean();
  static final Map<String, Map<String, Object>> REMOTE = new ConcurrentHashMap<>();
  static final Set<String> PUBLISHED = ConcurrentHashMap.newKeySet();
  static final List<String> PATHS = new CopyOnWriteArrayList<>();

  static {
    try {
      HTTP = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
      HTTP.createContext("/", WorkflowIT::handle);
      HTTP.start();
    } catch (IOException e) {
      throw new ExceptionInInitializerError(e);
    }
  }

  @DynamicPropertySource
  static void properties(DynamicPropertyRegistry p) {
    String url =
        System.getenv()
            .getOrDefault(
                "IT_DB_URL", "jdbc:mysql://127.0.0.1:13316/flow_test_java?connectionTimeZone=UTC");
    if (!url.matches("jdbc:mysql://[^/]+/flow_test_[A-Za-z0-9_]+(\\?.*)?"))
      throw new IllegalArgumentException("Integration tests only use flow_test_* databases");
    p.add("spring.datasource.url", () -> url);
    p.add("spring.datasource.username", () -> System.getenv().getOrDefault("IT_DB_USER", "root"));
    p.add("spring.datasource.password", () -> System.getenv().getOrDefault("IT_DB_PASSWORD", ""));
    p.add(
        "spring.rabbitmq.username", () -> System.getenv().getOrDefault("IT_RABBIT_USER", "guest"));
    p.add(
        "spring.rabbitmq.password",
        () -> System.getenv().getOrDefault("IT_RABBIT_PASSWORD", "guest"));
    p.add("flow.platform-base", () -> "http://127.0.0.1:" + HTTP.getAddress().getPort());
    p.add("flow.rate-prefix", () -> "flow-test:" + UUID.randomUUID() + ":");
  }

  @Autowired CatalogService catalog;
  @Autowired CatalogMapper db;
  @Autowired TaskMapper mapper;
  @Autowired TaskService tasks;
  @Autowired TaskExecutor executor;
  @Autowired AssetService assets;
  @Autowired ImportService imports;
  @Autowired AuthService auth;
  @Autowired AuthMapper users;
  @Autowired JdbcTemplate jdbc;
  @Autowired MockMvc mvc;
  @Autowired RabbitTemplate rabbit;
  @Autowired AmqpAdmin admin;
  @Autowired StringRedisTemplate redis;
  @Autowired TransactionTemplate tx;
  @Autowired PlatformGateway platform;
  long operator, reviewer;
  String operatorName, reviewerName;

  @BeforeAll
  void users() {
    String suffix = UUID.randomUUID().toString().substring(0, 8);
    operatorName = "op-" + suffix;
    reviewerName = "review-" + suffix;
    operator = Json.id(auth.create(operatorName, "operator-password-123", "OPERATOR").get("id"));
    reviewer = Json.id(auth.create(reviewerName, "reviewer-password-123", "REVIEWER").get("id"));
    admin.initialize();
  }

  record Fixture(long product, long store, long version, String code) {}

  Fixture fixture(String platform) {
    String code = "IT-" + UUID.randomUUID().toString().substring(0, 8);
    @SuppressWarnings("unchecked")
    var st =
        (Map<String, Object>)
            catalog.saveStore(
                null,
                Map.of(
                    "name",
                    code + " store",
                    "platform",
                    platform,
                    "mode",
                    platform.equals("TEMU") ? "SEMI" : "ALIEXPRESS",
                    "external_shop_id",
                    "10",
                    "account_key",
                    "fixture-account"),
                operator);
    var data =
        new LinkedHashMap<String, Object>(
            Map.of(
                "spu_code",
                code,
                "title",
                "Fixture necklace",
                "material",
                "Stainless steel",
                "dimensions",
                "45 cm",
                "weight_g",
                "12.5",
                "price",
                "9.12345678",
                "currency",
                "USD",
                "image_rights",
                "OWNED",
                "skus",
                List.of(
                    Map.of(
                        "sku_code",
                        code + "-S",
                        "quantity",
                        1,
                        "price",
                        "9.12345678",
                        "stock",
                        5,
                        "size",
                        "45 cm"))));
    data.put(
        "platform_payload",
        Map.of(
            "cid",
            "123",
            "imgUrls",
            List.of(
                "https://assets.example.test/1.png",
                "https://assets.example.test/2.png",
                "https://assets.example.test/3.png",
                "https://assets.example.test/4.png",
                "https://assets.example.test/5.png",
                "https://assets.example.test/6.png"),
            "skuMap",
            Map.of(
                code + "-S", Map.of("itemNum", code + "-S", "stock", 5, "price", "9.12345678"))));
    var p = catalog.save(null, data, operator);
    long id = Json.id(p.get("id"));
    long skuId = Json.id(db.children(sku, "product_id", id).get(0).get("id"));
    byte[] png = AssetService.png(new BufferedImage(100, 100, BufferedImage.TYPE_INT_RGB));
    for (String role : CatalogService.MAIN_ROLES)
      assets.save(
          id, null, role, "FINISHED", "fixture.png", png, Map.of("fixture", true), operator);
    assets.save(id, skuId, "SKU_IMAGE", "FINISHED", "fixture-sku.png", png, Map.of(), operator);
    catalog.copy(
        id,
        Map.of("platform", "TEMU", "title", "Fixture necklace", "description", "Fixture facts"),
        operator);
    catalog.copy(
        id,
        Map.of(
            "platform", "ALIEXPRESS", "title", "Fixture necklace", "description", "Fixture facts"),
        operator);
    long version = Json.id(catalog.require(product, id).get("content_version"));
    catalog.decide(id, Map.of("decision", "APPROVED", "content_version", version), reviewer);
    return new Fixture(id, Json.id(st.get("id")), version, code);
  }

  long create(Fixture f, String key, String action) {
    var b =
        tasks.create(
            Map.of(
                "productIds",
                List.of(f.product),
                "storeIds",
                List.of(f.store),
                "targetAction",
                action,
                "requestKey",
                key),
            operator);
    return Json.id(((List<?>) b.get("taskIds")).get(0));
  }

  @Test
  void concurrentRequestsAndDuplicateMessagesCreateOneExternalDraft() throws Exception {
    var f = fixture("TEMU");
    String key = "concurrent-" + UUID.randomUUID();
    var pool = Executors.newFixedThreadPool(20);
    try {
      var futures = new ArrayList<Future<Long>>();
      for (int n = 0; n < 20; n++) futures.add(pool.submit(() -> create(f, key, "CREATE_DRAFT")));
      var ids = new HashSet<Long>();
      for (var future : futures) ids.add(future.get(40, TimeUnit.SECONDS));
      assertEquals(1, ids.size());
      long id = ids.iterator().next();
      int before = CREATES.get();
      executor.execute(id, f.version);
      executor.execute(id, f.version);
      assertEquals(before + 1, CREATES.get());
      assertEquals("DRAFT_CREATED", db.one(publish_task, id).get("status"));
    } finally {
      pool.shutdownNow();
    }
    assertEquals(
        1,
        jdbc.queryForObject(
            "SELECT COUNT(*) FROM publish_task WHERE product_id=?", Integer.class, f.product));
    assertEquals(
        "REQUEST_KEY_CONFLICT",
        assertThrows(ApiException.class, () -> create(f, key, "PUBLISH")).code);
  }

  @Test
  void changedVersionInvalidatesApprovalAndUnsentTask() {
    var f = fixture("TEMU");
    long id = create(f, "invalidate-" + UUID.randomUUID(), "CREATE_DRAFT");
    int before = CREATES.get();
    catalog.save(f.product, Map.of("title", "Updated title"), operator);
    executor.execute(id, f.version);
    assertEquals("NEEDS_REVIEW", db.one(publish_task, id).get("status"));
    assertEquals(before, CREATES.get());
    assertEquals("NEEDS_REVIEW", catalog.reviewState(f.product).get("status"));
  }

  @Test
  void sameBatchKeyCannotChangeProductSet() {
    var first = fixture("TEMU");
    var second = fixture("TEMU");
    for (var f : List.of(first, second)) {
      long version = Json.id(catalog.require(product, f.product).get("content_version"));
      catalog.decide(
          f.product, Map.of("decision", "APPROVED", "content_version", version), reviewer);
    }
    String key = "batch-set-" + UUID.randomUUID();
    var request =
        Map.<String, Object>of(
            "productIds",
            List.of(first.product, second.product),
            "storeIds",
            List.of(first.store),
            "targetAction",
            "CREATE_DRAFT",
            "requestKey",
            key);
    var original = tasks.create(request, operator);
    assertEquals(original.get("id"), tasks.create(request, operator).get("id"));
    assertEquals(
        "REQUEST_KEY_CONFLICT",
        assertThrows(
                ApiException.class,
                () ->
                    tasks.create(
                        Map.of(
                            "productIds",
                            List.of(first.product),
                            "storeIds",
                            List.of(first.store),
                            "targetAction",
                            "CREATE_DRAFT",
                            "requestKey",
                            key),
                        operator))
            .code);
  }

  @Test
  void javaImageModelKeepsActualOutputEvidenceAndRejectsUrlOnlyResponses() throws Exception {
    var f = fixture("TEMU");
    var input = db.children(asset, "product_id", f.product).get(0);
    long inputId = Json.id(input.get("id"));
    var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    AtomicInteger calls = new AtomicInteger();
    AtomicBoolean urlOnly = new AtomicBoolean();
    byte[] output = AssetService.png(new BufferedImage(30, 40, BufferedImage.TYPE_INT_RGB));
    server.createContext(
        "/edit",
        exchange -> {
          calls.incrementAndGet();
          exchange.getRequestBody().readAllBytes();
          var data =
              urlOnly.get()
                  ? Map.of("url", "http://127.0.0.1/private")
                  : Map.of("b64_json", Base64.getEncoder().encodeToString(output));
          var bytes =
              Json.write(Map.of("data", List.of(data)))
                  .getBytes(java.nio.charset.StandardCharsets.UTF_8);
          exchange.getResponseHeaders().add("x-request-id", "image-fixture-request");
          exchange.sendResponseHeaders(200, bytes.length);
          exchange.getResponseBody().write(bytes);
          exchange.close();
        });
    server.start();
    try {
      var environment =
          new org.springframework.mock.env.MockEnvironment()
              .withProperty("IMAGE_MODEL_ENABLED", "true")
              .withProperty(
                  "IMAGE_MODEL_URL", "http://127.0.0.1:" + server.getAddress().getPort() + "/edit")
              .withProperty("IMAGE_MODEL_TEST_LOCAL", "true")
              .withProperty("IMAGE_MODEL_API_KEY", "fake-image-key")
              .withProperty("IMAGE_MODEL", "fixture-model");
      var operations = new ImageOperations(environment, db, catalog, assets, tx);
      String job = "image-fixture-" + UUID.randomUUID();
      var parameters =
          Map.<String, Object>of(
              "operation",
              "MODEL",
              "prompt",
              "Retain actual product dimensions",
              "role",
              "SCENE_LIFESTYLE");
      @SuppressWarnings("unchecked")
      var result = (Map<String, Object>) operations.execute(inputId, job, parameters, operator);
      assertEquals("SUCCEEDED", result.get("status"));
      var saved = catalog.require(asset, Json.id(result.get("result_asset_id")));
      assertEquals(30, ((Number) saved.get("width")).intValue());
      assertEquals(
          "image-fixture-request", Json.map(saved.get("metadata_json")).get("provider_request_id"));
      operations.execute(inputId, job, parameters, operator);
      assertEquals(1, calls.get());
      assertEquals(
          "JOB_INPUT_CONFLICT",
          assertThrows(
                  ApiException.class,
                  () ->
                      operations.execute(
                          inputId,
                          job,
                          Map.of("operation", "MODEL", "prompt", "Changed"),
                          operator))
              .code);
      urlOnly.set(true);
      assertEquals(
          "INLINE_IMAGE_REQUIRED",
          assertThrows(
                  ApiException.class,
                  () ->
                      operations.execute(
                          inputId, "image-url-" + UUID.randomUUID(), parameters, operator))
              .code);
      assertEquals(2, calls.get());
    } finally {
      server.stop(0);
    }
  }

  @Test
  void rejectedImageBlocksOverallApproval() throws Exception {
    var f = fixture("TEMU");
    long image = Json.id(db.children(asset, "product_id", f.product).get(0).get("id"));
    var session = new MockHttpSession();
    session.setAttribute("csrf", "image-review-csrf");
    session.setAttribute("userId", reviewer);
    session.setAttribute("authVersion", users.user(reviewer).get("auth_version"));
    mvc.perform(
            put("/api/reviews/images/" + image)
                .session(session)
                .header("X-CSRF-Token", "image-review-csrf")
                .contentType("application/json")
                .content("{\"decision\":\"REJECTED\",\"note\":\"image fixture rejected\"}"))
        .andExpect(status().isOk());
    assertEquals("NEEDS_REVIEW", catalog.reviewState(f.product).get("status"));
    assertTrue(catalog.blockers(f.product).stream().anyMatch(e -> e.contains("图片审核拒绝")));
  }

  @Test
  void lostExternalResponseNeverBlindlyRecreates() {
    var f = fixture("TEMU");
    long id = create(f, "lost-" + UUID.randomUUID(), "CREATE_DRAFT");
    int before = CREATES.get();
    LOSE_RESPONSE.set(true);
    executor.execute(id, f.version);
    LOSE_RESPONSE.set(false);
    assertEquals("VERIFYING", db.one(publish_task, id).get("status"));
    assertEquals(before + 1, CREATES.get());
    jdbc.update("UPDATE publish_task SET next_run_at=CURRENT_TIMESTAMP(6) WHERE id=?", id);
    executor.execute(id, f.version);
    assertEquals(before + 1, CREATES.get());
    assertThrows(
        ApiException.class, () -> tasks.manual(id, "retry", "must verify first", reviewer));
  }

  @Test
  void mysqlOutboxSurvivesUnavailableMqAndChecksRealConfirm() {
    var f = fixture("TEMU");
    long id = create(f, "outbox-" + UUID.randomUUID(), "CREATE_DRAFT");
    var event = db.children(outbox_event, "task_id", id).get(0);
    long eventId = Json.id(event.get("id"));
    var unavailable = mock(RabbitTemplate.class);
    doThrow(new org.springframework.amqp.AmqpException("offline"))
        .when(unavailable)
        .send(
            anyString(),
            anyString(),
            any(Message.class),
            any(org.springframework.amqp.rabbit.connection.CorrelationData.class));
    new OutboxPublisher(mapper, db, unavailable).publish(eventId);
    assertEquals("PENDING", db.one(outbox_event, eventId).get("status"));
    jdbc.update("UPDATE outbox_event SET next_run_at=CURRENT_TIMESTAMP(6) WHERE id=?", eventId);
    new OutboxPublisher(mapper, db, rabbit).publish(eventId);
    assertEquals("SENT", db.one(outbox_event, eventId).get("status"));
    assertNotNull(rabbit.receive(QueueConfig.QUEUE, 5000));
    admin.declareExchange(new DirectExchange("fixture.unrouted", true, false));
    var props = new MessageProperties();
    var correlation =
        new org.springframework.amqp.rabbit.connection.CorrelationData(
            UUID.randomUUID().toString());
    rabbit.send("fixture.unrouted", "missing", new Message("{}".getBytes(), props), correlation);
    try {
      assertTrue(correlation.getFuture().get(5, TimeUnit.SECONDS).isAck());
      assertNotNull(correlation.getReturned());
    } catch (Exception e) {
      fail(e);
    }
  }

  @Test
  void redisIsSharedAndOfflineStopsAllExternalSending() {
    var a = new AccountLimiter(redis, "flow-test:shared:", 100);
    var b = new AccountLimiter(redis, "flow-test:shared:", 100);
    String account = UUID.randomUUID().toString();
    a.acquire(account);
    long start = System.nanoTime();
    b.acquire(account);
    assertTrue(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start) >= 60);
    var offline = mock(AccountLimiter.class);
    doThrow(new ApiException(503, "RATE_LIMIT_UNAVAILABLE", "paused"))
        .when(offline)
        .acquire(anyString());
    var env =
        new org.springframework.mock.env.MockEnvironment()
            .withProperty("flow.app-key", "test")
            .withProperty("flow.app-secret", "test")
            .withProperty("flow.platform-base", "http://127.0.0.1:" + HTTP.getAddress().getPort());
    AtomicBoolean sent = new AtomicBoolean();
    assertThrows(
        ApiException.class,
        () ->
            new PlatformGateway(env, offline)
                .request("/open/test", Map.of(), "account", () -> sent.set(true)));
    assertFalse(sent.get());
  }

  @Test
  void expiredLeaseRejectsOldOwnerAndRecoversToVerification() {
    var f = fixture("TEMU");
    long id = create(f, "lease-" + UUID.randomUUID(), "CREATE_DRAFT");
    assertEquals(1, mapper.claim(id, "old-owner"));
    assertEquals(1, mapper.sent(id, "old-owner"));
    jdbc.update(
        "UPDATE publish_task SET lease_until=TIMESTAMPADD(SECOND,-1,CURRENT_TIMESTAMP(6)) WHERE"
            + " id=?",
        id);
    assertEquals(1, mapper.recover(id));
    assertEquals("VERIFYING", db.one(publish_task, id).get("status"));
    assertEquals(
        0,
        mapper.finish(
            id, "old-owner", "SUCCEEDED", "CREATE", "wrong", "PUBLISHED", 0, 0, false, null));
  }

  @Test
  void localCommitFailureAfterExternalSuccessRecoversWithoutRecreation() {
    var f = fixture("TEMU");
    long id = create(f, "commit-loss-" + UUID.randomUUID(), "CREATE_DRAFT");
    int before = CREATES.get();
    var failing = spy(db);
    doThrow(
            new org.springframework.dao.TransientDataAccessResourceException(
                "fixture persistence failure"))
        .when(failing)
        .update(eq(publish_attempt), anyMap());
    var execution = new TaskExecutor(mapper, failing, catalog, tasks, platform, tx);
    assertThrows(
        org.springframework.dao.DataAccessException.class, () -> execution.execute(id, f.version));
    assertEquals(before + 1, CREATES.get());
    assertEquals("RUNNING", db.one(publish_task, id).get("status"));
    jdbc.update(
        "UPDATE publish_task SET lease_until=TIMESTAMPADD(SECOND,-1,CURRENT_TIMESTAMP(6)) WHERE"
            + " id=?",
        id);
    assertEquals(1, mapper.recover(id));
    executor.execute(id, f.version);
    assertEquals(before + 1, CREATES.get());
  }

  @Test
  void publicationReusesApprovedDraftAndHistoricalUnknownBlocksCreation() {
    var f = fixture("TEMU");
    long draft = create(f, "reuse-draft-" + UUID.randomUUID(), "CREATE_DRAFT");
    int before = CREATES.get();
    executor.execute(draft, f.version);
    long publish = create(f, "reuse-publish-" + UUID.randomUUID(), "PUBLISH");
    assertEquals("CLAIM", db.one(publish_task, publish).get("stage"));
    assertEquals(
        db.one(publish_task, draft).get("external_id"),
        db.one(publish_task, publish).get("external_id"));
    assertEquals(before + 1, CREATES.get());
    var other = fixture("TEMU");
    db.insert(
        legacy_external,
        new LinkedHashMap<>(
            Map.of(
                "product_id",
                other.product,
                "store_id",
                other.store,
                "external_id",
                "historical-fixture",
                "original_status",
                "PUBLISHED",
                "record_json",
                "{}")));
    assertEquals(
        "HISTORICAL_RESULT_UNVERIFIED",
        assertThrows(
                ApiException.class,
                () -> create(other, "legacy-gate-" + UUID.randomUUID(), "CREATE_DRAFT"))
            .code);
  }

  @Test
  void temuPublicationChecksClaimStockAndAuthoritativeBucket() {
    var f = fixture("TEMU");
    long id = create(f, "publish-" + UUID.randomUUID(), "PUBLISH");
    for (int n = 0; n < 7; n++) {
      jdbc.update("UPDATE publish_task SET next_run_at=CURRENT_TIMESTAMP(6) WHERE id=?", id);
      executor.execute(id, f.version);
    }
    assertEquals("SUCCEEDED", db.one(publish_task, id).get("status"));
    assertTrue(PATHS.stream().anyMatch(p -> p.endsWith("save_shop_collect_item_info")));
    var counts =
        (Map<?, ?>) tasks.batch(Json.id(db.one(publish_task, id).get("batch_id"))).get("counts");
    assertEquals(1L, counts.get("published"));
    assertEquals(0L, counts.get("draft_created"));
  }

  @Test
  void aliexpressUsesSeparateEndpointAndNeverTemuPublish() {
    var f = fixture("ALIEXPRESS");
    int before = PATHS.size();
    long id = create(f, "ae-" + UUID.randomUUID(), "CREATE_DRAFT");
    executor.execute(id, f.version);
    assertEquals("DRAFT_CREATED", db.one(publish_task, id).get("status"));
    assertEquals(List.of("/open/fixture/aliexpress/create"), PATHS.subList(before, PATHS.size()));
    assertEquals(
        "UNSUPPORTED_ACTION",
        assertThrows(
                ApiException.class, () -> create(f, "ae-publish-" + UUID.randomUUID(), "PUBLISH"))
            .code);
  }

  @Test
  void storeSynchronizationAndCategoryLookupKeepActualIdentifiers() {
    var sync = new PlatformCatalogService(platform, db, catalog, tx);
    @SuppressWarnings("unchecked")
    var result = (Map<String, Object>) sync.synchronize("SEMI", operator);
    assertEquals(1, ((Number) result.get("count")).intValue());
    var saved =
        db.all(store).stream()
            .filter(s -> "fixture-synchronized-shop".equals(s.get("external_shop_id")))
            .findFirst()
            .orElseThrow();
    assertEquals("SEMI", saved.get("mode"));
    assertEquals("TEMU", saved.get("platform"));
    var response =
        platform.lookup(
            "/open/v1/product/collect_box/pddkj/collect_box/get_category_attribute_rules",
            Map.of("cid", "123"));
    assertTrue(Json.write(response).contains("fixture-attribute-id"));
  }

  @Test
  void csrfRolesAndRevokedSessionsAreEnforced() throws Exception {
    mvc.perform(get("/api/products")).andExpect(status().isUnauthorized());
    mvc.perform(post("/api/auth/login").contentType("application/json").content("{}"))
        .andExpect(status().isForbidden());
    MockHttpSession session = new MockHttpSession();
    String token =
        Json.map(
                mvc.perform(get("/api/auth/csrf").session(session))
                    .andReturn()
                    .getResponse()
                    .getContentAsString())
            .get("token")
            .toString();
    mvc.perform(
            post("/api/auth/login")
                .session(session)
                .header("X-CSRF-Token", token)
                .contentType("application/json")
                .content(
                    Json.write(
                        Map.of("username", operatorName, "password", "operator-password-123"))))
        .andExpect(status().isOk());
    mvc.perform(
            put("/api/products/999/review")
                .session(session)
                .header("X-CSRF-Token", token)
                .contentType("application/json")
                .content("{}"))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/assets/999/content")).andExpect(status().isUnauthorized());
    auth.change(operator, Map.of("password", "new-operator-password-123"));
    mvc.perform(get("/api/products").session(session)).andExpect(status().isUnauthorized());
    auth.change(operator, Map.of("password", "operator-password-123"));
  }

  @Test
  void importIsIdempotentAndCrossSpuSkuConflictRollsBackWholeSpu() throws Exception {
    String code = "IMPORT-" + UUID.randomUUID().toString().substring(0, 6);
    byte[] bytes;
    try (var workbook = new XSSFWorkbook();
        var out = new ByteArrayOutputStream()) {
      var sheet = workbook.createSheet("Products");
      var headers = List.of("spu_code", "sku_code", "title", "price", "stock", "quantity");
      var row = sheet.createRow(0);
      for (int n = 0; n < headers.size(); n++) row.createCell(n).setCellValue(headers.get(n));
      var values = List.of(code, code + "-S", "Imported", "9.12345678", "5", "1");
      row = sheet.createRow(1);
      for (int n = 0; n < values.size(); n++) row.createCell(n).setCellValue(values.get(n));
      workbook.write(out);
      bytes = out.toByteArray();
    }
    imports.run("test.xlsx", bytes, Map.of(), operator);
    imports.run("test.xlsx", bytes, Map.of(), operator);
    assertEquals(
        1,
        jdbc.queryForObject("SELECT COUNT(*) FROM product WHERE spu_code=?", Integer.class, code));
    assertEquals(
        1,
        jdbc.queryForObject(
            "SELECT COUNT(*) FROM sku WHERE sku_code=?", Integer.class, code + "-S"));
    assertThrows(
        ApiException.class,
        () ->
            catalog.save(
                null,
                Map.of(
                    "spu_code",
                    code + "-OTHER",
                    "title",
                    "Other",
                    "skus",
                    List.of(
                        Map.of("sku_code", code + "-S", "price", "2", "stock", 1, "quantity", 1))),
                operator));
    assertNull(db.bySpu(code + "-OTHER"));
    assertEquals(
        "NEEDS_REVIEW", catalog.reviewState(Json.id(db.bySpu(code).get("id"))).get("status"));
  }

  @AfterAll
  void closeServer() {
    db.all(store).stream()
        .filter(s -> "合成验收店铺".equals(s.get("name")))
        .findFirst()
        .ifPresent(
            s ->
                catalog.saveStore(
                    Json.id(s.get("id")), Map.of("name", "合成验收店铺 历史" + s.get("id")), operator));
    var f = fixture("TEMU");
    catalog.saveStore(f.store, Map.of("name", "合成验收店铺"), operator);
    catalog.save(f.product, Map.of("title", "合成失败重试验收商品"), operator);
    long version = Json.id(catalog.require(product, f.product).get("content_version"));
    catalog.decide(f.product, Map.of("decision", "APPROVED", "content_version", version), reviewer);
    var current = new Fixture(f.product, f.store, version, f.code);
    long id = create(current, "browser-retry-" + UUID.randomUUID(), "CREATE_DRAFT");
    var offline = mock(PlatformGateway.class);
    when(offline.execute(anyMap(), anyBoolean(), any(Runnable.class)))
        .thenThrow(new PlatformGateway.Failure("合成验收：外部发送前暂不可用", false, true, 503));
    var execution = new TaskExecutor(mapper, db, catalog, tasks, offline, tx);
    for (int n = 0; n < 4; n++) {
      jdbc.update("UPDATE publish_task SET next_run_at=CURRENT_TIMESTAMP(6) WHERE id=?", id);
      execution.execute(id, version);
    }
    assertEquals("FAILED", db.one(publish_task, id).get("status"));
    HTTP.stop(0);
  }

  @SuppressWarnings("unchecked")
  static void handle(HttpExchange exchange) throws IOException {
    String path = exchange.getRequestURI().getPath();
    PATHS.add(path);
    var payload =
        Json.map(
            new String(
                exchange.getRequestBody().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
    Map<String, Object> data = Map.of();
    if (path.endsWith("create_collect_box_item") || path.endsWith("aliexpress/create")) {
      String id = Integer.toString(1000 + CREATES.incrementAndGet());
      var product =
          payload.get("siteCollectItemInfo") instanceof Map<?, ?> m
              ? (Map<String, Object>) m
              : payload;
      REMOTE.put(id, product);
      data = LOSE_RESPONSE.get() ? Map.of() : Map.of("collectBoxDetailId", id);
    } else if (path.endsWith("get_shop_list"))
      data =
          Map.of(
              "list",
              List.of(
                  Map.of(
                      "shopId",
                      "fixture-synchronized-shop",
                      "shopName",
                      "Fixture synchronized shop",
                      "platform",
                      "pddkjChoice")));
    else if (path.endsWith("get_category_attribute_rules"))
      data =
          Map.of(
              "productAttributeRules",
              List.of(Map.of("pid", "fixture-attribute-id", "name", "Actual fixture rule")));
    else if (path.endsWith("get_shop_collect_item_info"))
      data = Map.of("shopCollectItemInfo", REMOTE.get(payload.get("detailId").toString()));
    else if (path.endsWith("save_move_collect_task")) {
      for (Object id : (List<?>) payload.get("detailIds")) PUBLISHED.add(id.toString());
    } else if (path.endsWith("search_collect_box_detail_list"))
      data =
          Map.of(
              "detailList",
              PUBLISHED.stream().map(id -> Map.of("collectBoxDetailId", id)).toList());
    var body =
        Json.write(Map.of("code", "success", "data", data))
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
    exchange.getResponseHeaders().add("Content-Type", "application/json");
    exchange.sendResponseHeaders(200, body.length);
    exchange.getResponseBody().write(body);
    exchange.close();
  }
}
