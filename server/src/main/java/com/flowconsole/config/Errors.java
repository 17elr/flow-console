package com.flowconsole.config;

import com.flowconsole.ApiException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class Errors {
  @ExceptionHandler(ApiException.class)
  ResponseEntity<?> api(ApiException e, HttpServletRequest r) {
    return error(e.status, e.code, e.getMessage(), e.fields, r);
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  ResponseEntity<?> conflict(Exception e, HttpServletRequest r) {
    return error(409, "CONFLICT", "编码或请求键冲突，请刷新后检查", Map.of(), r);
  }

  @ExceptionHandler(org.springframework.web.servlet.resource.NoResourceFoundException.class)
  ResponseEntity<?> missing(Exception e, HttpServletRequest r) {
    return error(404, "NOT_FOUND", "接口或资源不存在", Map.of(), r);
  }

  @ExceptionHandler({
    org.springframework.web.bind.MissingServletRequestParameterException.class,
    org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class
  })
  ResponseEntity<?> parameter(Exception e, HttpServletRequest r) {
    return error(400, "BAD_REQUEST", "缺少参数或参数类型无效", Map.of(), r);
  }

  @ExceptionHandler({HttpMessageNotReadableException.class, IllegalArgumentException.class})
  ResponseEntity<?> invalid(Exception e, HttpServletRequest r) {
    return error(400, "BAD_REQUEST", "请求格式或参数无效", Map.of(), r);
  }

  @ExceptionHandler(MaxUploadSizeExceededException.class)
  ResponseEntity<?> upload(Exception e, HttpServletRequest r) {
    return error(422, "FILE_TOO_LARGE", "上传内容超过限制", Map.of("file", "单文件最多30MB，总计160MB"), r);
  }

  @ExceptionHandler(Exception.class)
  ResponseEntity<?> unexpected(Exception e, HttpServletRequest r) {
    org.slf4j.LoggerFactory.getLogger(Errors.class)
        .error("request={} type={}", r.getAttribute("requestId"), e.getClass().getSimpleName());
    return error(503, "UNAVAILABLE", "服务暂不可用，请保留表单并重试", Map.of(), r);
  }

  static ResponseEntity<?> error(
      int status, String code, String message, Map<String, String> fields, HttpServletRequest r) {
    return ResponseEntity.status(status)
        .body(
            Map.of(
                "code",
                code,
                "message",
                message,
                "fieldErrors",
                fields,
                "requestId",
                String.valueOf(r.getAttribute("requestId"))));
  }
}
