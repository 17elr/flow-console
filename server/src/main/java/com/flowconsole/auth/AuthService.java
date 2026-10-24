package com.flowconsole.auth;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService implements ApplicationRunner {
  private final AuthMapper auth;
  private final CatalogMapper db;
  private final String bootstrap;
  private final BCryptPasswordEncoder passwords = new BCryptPasswordEncoder(12);
  private final String dummyHash = passwords.encode(UUID.randomUUID().toString());

  public AuthService(
      AuthMapper auth, CatalogMapper db, @Value("${flow.bootstrap-password}") String bootstrap) {
    this.auth = auth;
    this.db = db;
    this.bootstrap = bootstrap;
  }

  @Override
  public void run(ApplicationArguments args) {
    if (auth.count() == 0 && !bootstrap.isBlank()) {
      try {
        create("admin", bootstrap, "ADMIN");
      } catch (org.springframework.dao.DuplicateKeyException e) {
        if (auth.username("admin") == null) throw e;
      }
    }
  }

  public Map<String, Object> login(String name, String password, HttpServletRequest request) {
    var session = request.getSession();
    Long until = (Long) session.getAttribute("loginUntil");
    if (until != null && until > System.currentTimeMillis())
      throw new ApiException(403, "LOGIN_PAUSED", "尝试过多，请一分钟后重试");
    var user = auth.username(name);
    boolean matches =
        passwords.matches(password, user == null ? dummyHash : (String) user.get("password_hash"));
    if (user == null || !matches || !Boolean.TRUE.equals(user.get("active"))) {
      int failures =
          Optional.ofNullable((Integer) session.getAttribute("loginFailures")).orElse(0) + 1;
      session.setAttribute("loginFailures", failures);
      if (failures >= 5) {
        session.setAttribute("loginUntil", System.currentTimeMillis() + 60000);
        session.setAttribute("loginFailures", 0);
      }
      throw new ApiException(401, "LOGIN_FAILED", "用户名或密码错误");
    }
    request.changeSessionId();
    session.setAttribute("userId", Json.id(user.get("id")));
    session.setAttribute("authVersion", user.get("auth_version"));
    session.removeAttribute("loginFailures");
    db.audit(Json.id(user.get("id")), "LOGIN", null, "");
    return publicUser(user);
  }

  public Map<String, Object> current(HttpServletRequest request) {
    var session = request.getSession(false);
    if (session == null || session.getAttribute("userId") == null)
      throw new ApiException(401, "LOGIN_REQUIRED", "请先登录");
    var user = auth.user((Long) session.getAttribute("userId"));
    if (user == null
        || !Boolean.TRUE.equals(user.get("active"))
        || !Objects.equals(user.get("auth_version"), session.getAttribute("authVersion"))) {
      session.invalidate();
      throw new ApiException(401, "SESSION_EXPIRED", "登录已失效，请重新登录");
    }
    return publicUser(user);
  }

  public void require(Map<String, Object> user, String... roles) {
    if (!Arrays.asList(roles).contains(user.get("role")))
      throw new ApiException(403, "FORBIDDEN", "当前角色没有执行此操作的权限");
  }

  public Map<String, Object> create(String name, String password, String role) {
    if (!name.matches("[a-zA-Z0-9_.-]{3,80}"))
      throw ApiException.invalid("username", "用户名需3至80个字母、数字或 ._- ");
    validatePassword(password);
    validateRole(role);
    var row =
        new LinkedHashMap<String, Object>(
            Map.of("username", name, "password_hash", passwords.encode(password), "role", role));
    db.insert(CatalogMapper.Table.app_user, row);
    return publicUser(auth.user(Json.id(row.get("id"))));
  }

  public void change(long id, Map<String, Object> payload) {
    var old = auth.user(id);
    if (old == null) throw new ApiException(404, "NOT_FOUND", "用户不存在");
    String role =
        payload.containsKey("role") ? Json.text(payload, "role") : old.get("role").toString();
    validateRole(role);
    String password = Json.text(payload, "password");
    if (!password.isBlank()) validatePassword(password);
    boolean active =
        payload.containsKey("active")
            ? Boolean.TRUE.equals(payload.get("active"))
            : Boolean.TRUE.equals(old.get("active"));
    if (old.get("role").equals("ADMIN")
        && (!active || !role.equals("ADMIN"))
        && auth.users().stream()
                .filter(u -> u.get("role").equals("ADMIN") && Boolean.TRUE.equals(u.get("active")))
                .count()
            <= 1) throw new ApiException(409, "LAST_ADMIN", "至少保留一个有效管理员");
    auth.change(id, password.isBlank() ? null : passwords.encode(password), active, role);
  }

  private void validatePassword(String password) {
    if (password.length() < 12
        || password.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 72)
      throw ApiException.invalid("password", "密码需至少12字符，UTF-8编码最多72字节");
  }

  private void validateRole(String role) {
    if (!Set.of("ADMIN", "OPERATOR", "REVIEWER").contains(role))
      throw ApiException.invalid("role", "角色无效");
  }

  private Map<String, Object> publicUser(Map<String, Object> user) {
    return Map.of("id", user.get("id"), "username", user.get("username"), "role", user.get("role"));
  }
}
