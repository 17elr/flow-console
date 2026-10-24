package com.flowconsole.auth;

import com.flowconsole.*;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class AuthFilter extends OncePerRequestFilter {
  private final AuthService auth;

  public AuthFilter(AuthService auth) {
    this.auth = auth;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    request.setAttribute("requestId", UUID.randomUUID().toString());
    response.setHeader("X-Request-Id", request.getAttribute("requestId").toString());
    response.setHeader("X-Content-Type-Options", "nosniff");
    response.setHeader("X-Frame-Options", "DENY");
    response.setHeader("Referrer-Policy", "same-origin");
    response.setHeader("Cache-Control", "no-store");
    String path = request.getRequestURI();
    try {
      if (!Set.of("GET", "HEAD", "OPTIONS").contains(request.getMethod())) {
        var s = request.getSession(false);
        String expected = s == null ? null : (String) s.getAttribute("csrf");
        String provided = request.getHeader("X-CSRF-Token");
        if (expected == null
            || provided == null
            || !MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8),
                provided.getBytes(StandardCharsets.UTF_8)))
          throw new ApiException(403, "CSRF", "请求验证已失效，请刷新后重试");
      }
      boolean publicPath =
          (request.getMethod().equals("GET") && Set.of("/health", "/api/auth/csrf").contains(path))
              || (request.getMethod().equals("POST") && path.equals("/api/auth/login"));
      if (!publicPath) request.setAttribute("user", auth.current(request));
      chain.doFilter(request, response);
    } catch (ApiException e) {
      response.setStatus(e.status);
      response.setContentType("application/json;charset=UTF-8");
      response
          .getWriter()
          .write(
              Json.write(
                  Map.of(
                      "code",
                      e.code,
                      "message",
                      e.getMessage(),
                      "fieldErrors",
                      e.fields,
                      "requestId",
                      request.getAttribute("requestId"))));
    }
  }

  @SuppressWarnings("unchecked")
  public static Map<String, Object> user(HttpServletRequest r) {
    return (Map<String, Object>) r.getAttribute("user");
  }

  public static long userId(HttpServletRequest r) {
    return Json.id(user(r).get("id"));
  }
}
