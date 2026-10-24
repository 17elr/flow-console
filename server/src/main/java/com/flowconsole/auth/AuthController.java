package com.flowconsole.auth;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class AuthController {
  private final AuthService auth;
  private final AuthMapper users;
  private final CatalogMapper db;

  public AuthController(AuthService auth, AuthMapper users, CatalogMapper db) {
    this.auth = auth;
    this.users = users;
    this.db = db;
  }

  @GetMapping("/api/auth/csrf")
  Map<String, Object> csrf(HttpServletRequest r) {
    var s = r.getSession();
    if (s.getAttribute("csrf") == null) s.setAttribute("csrf", UUID.randomUUID().toString());
    return Map.of("token", s.getAttribute("csrf"));
  }

  @PostMapping("/api/auth/login")
  Map<String, Object> login(@RequestBody Map<String, Object> p, HttpServletRequest r) {
    return auth.login(Json.text(p, "username"), Json.text(p, "password"), r);
  }

  @GetMapping("/api/auth/me")
  Map<String, Object> me(HttpServletRequest r) {
    return auth.current(r);
  }

  @PostMapping("/api/auth/logout")
  @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
  void logout(HttpServletRequest r) {
    r.getSession().invalidate();
  }

  @GetMapping("/api/users")
  Object list(HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return users.users();
  }

  @PostMapping("/api/users")
  Object create(@RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    var user =
        auth.create(Json.text(p, "username"), Json.text(p, "password"), Json.text(p, "role"));
    db.audit(
        AuthFilter.userId(r), "CREATE_USER", Json.id(user.get("id")), user.get("role").toString());
    return user;
  }

  @PatchMapping("/api/users/{id}")
  @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
  void change(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    auth.change(id, p);
    db.audit(AuthFilter.userId(r), "CHANGE_USER", id, "");
  }
}
