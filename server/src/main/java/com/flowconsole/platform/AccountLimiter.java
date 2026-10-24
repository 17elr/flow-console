package com.flowconsole.platform;

import com.flowconsole.ApiException;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class AccountLimiter {
  // Redis TIME keeps reservations consistent when worker clocks differ.
  static final String LUA =
      "local t=redis.call('TIME'); local now=t[1]*1000+math.floor(t[2]/1000); local"
          + " next=math.max(now,tonumber(redis.call('GET',KEYS[1]) or '0')); local wait=next-now;"
          + " if wait>20000 then return -1 end;"
          + " redis.call('SET',KEYS[1],next+tonumber(ARGV[1]),'PX',60000); return wait";
  private final StringRedisTemplate redis;
  private final String prefix;
  private final long interval;

  public AccountLimiter(
      StringRedisTemplate redis,
      @Value("${flow.rate-prefix}") String prefix,
      @Value("${flow.interval-ms}") long interval) {
    this.redis = redis;
    this.prefix = prefix;
    this.interval = Math.max(1, Math.min(interval, 20000));
  }

  public void acquire(String account) {
    Long delay;
    try {
      delay =
          redis.execute(
              new DefaultRedisScript<>(LUA, Long.class),
              List.of(
                  prefix
                      + com.flowconsole.Json.sha(
                          account.getBytes(java.nio.charset.StandardCharsets.UTF_8))),
              Long.toString(interval));
    } catch (Exception e) {
      throw new ApiException(503, "RATE_LIMIT_UNAVAILABLE", "共享限流不可用，外部发送已暂停");
    }
    if (delay == null || delay < 0) throw new ApiException(503, "ACCOUNT_BUSY", "平台账号繁忙，任务稍后重试");
    try {
      if (delay > 0) Thread.sleep(delay);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new ApiException(503, "INTERRUPTED", "任务已暂停");
    }
  }
}
