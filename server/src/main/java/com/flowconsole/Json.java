package com.flowconsole;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

public final class Json {
  private static final ObjectMapper MAPPER =
      new ObjectMapper()
          .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
          .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

  private Json() {}

  public static String write(Object value) {
    try {
      return MAPPER.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalArgumentException("Invalid JSON", e);
    }
  }

  public static Map<String, Object> map(Object value) {
    if (value == null) return new LinkedHashMap<>();
    try {
      return MAPPER.readValue(
          value.toString(), new TypeReference<LinkedHashMap<String, Object>>() {});
    } catch (Exception e) {
      throw new IllegalArgumentException("Invalid JSON object", e);
    }
  }

  public static List<Object> list(Object value) {
    if (value == null) return new ArrayList<>();
    try {
      return MAPPER.readValue(value.toString(), new TypeReference<ArrayList<Object>>() {});
    } catch (Exception e) {
      throw new IllegalArgumentException("Invalid JSON array", e);
    }
  }

  public static String hash(Object value) {
    return sha(write(value).getBytes(StandardCharsets.UTF_8));
  }

  public static String sha(byte[] value) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  public static long id(Object value) {
    return Long.parseLong(String.valueOf(value));
  }

  public static String text(Map<String, Object> value, String key) {
    return Objects.toString(value.get(key), "").trim();
  }

  public static void rejectCredentials(Object value) {
    if (value instanceof Map<?, ?> map)
      for (var entry : map.entrySet()) {
        String key = entry.getKey().toString();
        String normalized = key.toLowerCase(Locale.ROOT).replace("_", "").replace("-", "");
        if (normalized.matches(
            ".*(secret|password|token|apikey|appkey|authorization|cookie|signature).*|sign|xsign"))
          throw ApiException.invalid(key, "密钥与认证信息只能放在受保护的服务端配置");
        rejectCredentials(entry.getValue());
      }
    else if (value instanceof List<?> list) list.forEach(Json::rejectCredentials);
  }
}
