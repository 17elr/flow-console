package com.flowconsole;

import java.util.Map;

public class ApiException extends RuntimeException {
  public final int status;
  public final String code;
  public final Map<String, String> fields;

  public ApiException(int status, String code, String message) {
    this(status, code, message, Map.of());
  }

  public ApiException(int status, String code, String message, Map<String, String> fields) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  public static ApiException invalid(String field, String message) {
    return new ApiException(422, "VALIDATION", message, Map.of(field, message));
  }
}
