package com.flowconsole.asset;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import com.flowconsole.platform.BoundedHttp;
import com.flowconsole.product.CatalogService;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.zip.*;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ImageOperations {
  private final Environment env;
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final AssetService files;
  private final TransactionTemplate tx;
  private final HttpClient http =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(10))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();

  public ImageOperations(
      Environment env,
      CatalogMapper db,
      CatalogService catalog,
      AssetService files,
      TransactionTemplate tx) {
    this.env = env;
    this.db = db;
    this.catalog = catalog;
    this.files = files;
    this.tx = tx;
  }

  public Map<String, Object> status() {
    return Map.of(
        "configured",
        modelConfigured(),
        "compute_configured",
        !env.getProperty("flow.compute-url", "").isBlank(),
        "model",
        env.getProperty("IMAGE_MODEL", ""),
        "deterministic_operations",
        List.of("RESIZE", "CROP", "SIZE_CARD"));
  }

  private boolean modelConfigured() {
    return env.getProperty("IMAGE_MODEL_ENABLED", Boolean.class, false)
        && !env.getProperty("IMAGE_MODEL_URL", "").isBlank()
        && !env.getProperty("IMAGE_MODEL_API_KEY", "").isBlank();
  }

  public Object execute(long assetId, String jobId, Map<String, Object> parameters, long user) {
    if (!jobId.matches("[a-zA-Z0-9-]{8,80}")) throw ApiException.invalid("jobId", "任务ID格式错误");
    String operation = Json.text(parameters, "operation");
    boolean model = operation.equals("MODEL");
    if (!Set.of("MODEL", "OCR", "REMOVE_BACKGROUND", "RESIZE").contains(operation))
      throw ApiException.invalid("operation", "操作不支持");
    if (model && !modelConfigured())
      throw new ApiException(409, "MODEL_NOT_CONFIGURED", "图像模型未配置或调用未启用");
    if (!model
        && (env.getProperty("flow.compute-url", "").isBlank()
            || env.getProperty("flow.compute-token", "").isBlank()))
      throw new ApiException(409, "COMPUTE_NOT_CONFIGURED", "可选算法适配器未配置");
    var input = catalog.require(asset, assetId);
    byte[] bytes = files.read(input);
    AssetService.decode(bytes);
    String paramsHash = Json.hash(parameters);
    var known = db.imageJob(jobId);
    if (known != null) {
      if (!known.get("input_hash").equals(input.get("sha256"))
          || !known.get("params_hash").equals(paramsHash))
        throw new ApiException(409, "JOB_INPUT_CONFLICT", "同任务ID的输入不能变化");
      if (known.get("status").equals("SUCCEEDED")) return known;
      throw new ApiException(409, "JOB_ALREADY_ATTEMPTED", "该任务已尝试，先检查记录；结果不明确时禁止自动重复收费请求");
    }
    var job =
        new LinkedHashMap<String, Object>(
            Map.of(
                "job_id",
                jobId,
                "input_asset_id",
                assetId,
                "input_hash",
                input.get("sha256"),
                "params_hash",
                paramsHash,
                "operation",
                operation,
                "status",
                "RUNNING",
                "evidence_json",
                "{}",
                "created_by",
                user));
    db.insert(image_operation, job);
    try {
      String boundary = "flow-" + UUID.randomUUID();
      var body = new ByteArrayOutputStream();
      var meta = new LinkedHashMap<String, Object>();
      meta.put("input_sha256", input.get("sha256"));
      meta.put("job_id", jobId);
      meta.put("operation", operation);
      URI url;
      HttpRequest.Builder request;
      if (model) {
        url = URI.create(env.getProperty("IMAGE_MODEL_URL"));
        if (!url.getScheme().equals("https")
            && !env.getProperty("IMAGE_MODEL_TEST_LOCAL", Boolean.class, false))
          throw new ApiException(409, "MODEL_HTTPS_REQUIRED", "模型地址必须使用HTTPS");
        String prompt = Json.text(parameters, "prompt");
        if (prompt.isBlank() || prompt.length() > 6000)
          throw ApiException.invalid("prompt", "提示词必填且最多6000字");
        part(body, boundary, "model", env.getProperty("IMAGE_MODEL", "gpt-image-1"));
        part(body, boundary, "prompt", prompt);
        part(body, boundary, "response_format", "b64_json");
        part(body, boundary, "size", "1024x1024");
        meta.put("model", env.getProperty("IMAGE_MODEL", "gpt-image-1"));
        meta.put("prompt", prompt);
        meta.put("prompt_version", "manual-v1");
        request =
            HttpRequest.newBuilder(url)
                .header("Authorization", "Bearer " + env.getProperty("IMAGE_MODEL_API_KEY"));
      } else {
        url = URI.create(env.getProperty("flow.compute-url") + "/internal/compute/" + jobId);
        var safe = new LinkedHashMap<String, Object>();
        for (String key :
            List.of("operation", "size", "skuFacts", "dimensions", "inputFingerprint"))
          if (parameters.containsKey(key)) safe.put(key, parameters.get(key));
        part(body, boundary, "params", Json.write(safe));
        request =
            HttpRequest.newBuilder(url)
                .header("X-Internal-Token", env.getProperty("flow.compute-token"));
      }
      body.write(
          ("--"
                  + boundary
                  + "\r\nContent-Disposition: form-data; name=\""
                  + (model ? "image" : "file")
                  + "\"; filename=\"input.png\"\r\nContent-Type: image/png\r\n\r\n")
              .getBytes(StandardCharsets.UTF_8));
      body.write(AssetService.png(AssetService.decode(bytes)));
      body.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
      var response =
          BoundedHttp.send(
              http,
              request
                  .timeout(Duration.ofSeconds(180))
                  .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                  .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray()))
                  .build(),
              48 * 1024 * 1024,
              180);
      if (response.statusCode() < 200 || response.statusCode() >= 300)
        throw new ApiException(
            response.statusCode() == 503 ? 503 : 422,
            "COMPUTE_REJECTED",
            "图像服务未完成处理，HTTP " + response.statusCode());
      byte[] output = null;
      if (model) {
        var json = Json.map(new String(response.body(), StandardCharsets.UTF_8));
        var data = Json.list(Json.write(json.getOrDefault("data", List.of())));
        if (data.isEmpty()
            || !(data.get(0) instanceof Map<?, ?> first)
            || !(first.get("b64_json") instanceof String encoded))
          throw new ApiException(422, "INLINE_IMAGE_REQUIRED", "模型未返回可验证的内嵌图片；不会抓取任意响应URL");
        output = Base64.getDecoder().decode(encoded);
        meta.put("provider_request_id", response.headers().firstValue("x-request-id").orElse(""));
      } else {
        try (var zip = new ZipInputStream(new ByteArrayInputStream(response.body()))) {
          ZipEntry entry;
          int entries = 0;
          while ((entry = zip.getNextEntry()) != null) {
            if (++entries > 2 || !Set.of("manifest.json", "output.png").contains(entry.getName()))
              throw new ApiException(422, "INVALID_COMPUTE_RESULT", "算法结果结构无效");
            byte[] content = zip.readNBytes(30 * 1024 * 1024 + 1);
            if (content.length > 30 * 1024 * 1024)
              throw new ApiException(422, "COMPUTE_RESULT_TOO_LARGE", "算法结果过大");
            if (entry.getName().equals("output.png")) output = content;
            else meta.putAll(Json.map(new String(content, StandardCharsets.UTF_8)));
          }
        }
        if (!jobId.equals(meta.get("jobId")))
          throw new ApiException(422, "JOB_RESULT_MISMATCH", "算法返回任务ID不匹配");
      }
      Map<String, Object> result;
      if (operation.equals("OCR")) {
        if (!meta.containsKey("text"))
          throw new ApiException(422, "OCR_RESULT_MISSING", "算法未返回实际识别文本");
        tx.executeWithoutResult(
            s -> {
              catalog.lock(Json.id(input.get("product_id")));
              var old = Json.map(input.get("metadata_json"));
              old.put("ocr", meta);
              db.update(
                  asset,
                  new LinkedHashMap<>(Map.of("id", assetId, "metadata_json", Json.write(old))));
              catalog.bump(Json.id(input.get("product_id")), user);
            });
        result = input;
      } else {
        if (output == null) throw new ApiException(422, "IMAGE_RESULT_MISSING", "图像服务没有返回实际图片");
        result =
            files.save(
                Json.id(input.get("product_id")),
                input.get("sku_id") == null ? null : Json.id(input.get("sku_id")),
                parameters.getOrDefault("role", input.get("role")).toString(),
                "GENERATED",
                jobId + ".png",
                output,
                meta,
                user);
      }
      db.update(
          image_operation,
          new LinkedHashMap<>(
              Map.of(
                  "id",
                  job.get("id"),
                  "status",
                  "SUCCEEDED",
                  "result_asset_id",
                  result.get("id"),
                  "evidence_json",
                  Json.write(meta))));
      db.audit(user, "IMAGE_" + operation, Json.id(job.get("id")), jobId);
      return db.imageJob(jobId);
    } catch (Exception e) {
      db.update(
          image_operation,
          new LinkedHashMap<>(
              Map.of(
                  "id",
                  job.get("id"),
                  "status",
                  model ? "NEEDS_REVIEW" : "FAILED",
                  "evidence_json",
                  Json.write(
                      Map.of(
                          "error",
                          e instanceof ApiException a ? a.code : e.getClass().getSimpleName())))));
      if (e instanceof ApiException a) throw a;
      throw new ApiException(503, "IMAGE_OPERATION_FAILED", "图像服务中断，已保存任务记录；未生成替代素材");
    }
  }

  private static void part(ByteArrayOutputStream out, String boundary, String name, String value)
      throws IOException {
    out.write(
        ("--"
                + boundary
                + "\r\nContent-Disposition: form-data; name=\""
                + name
                + "\"\r\n\r\n"
                + value
                + "\r\n")
            .getBytes(StandardCharsets.UTF_8));
  }
}
