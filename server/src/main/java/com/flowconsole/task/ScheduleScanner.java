package com.flowconsole.task;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("api | default")
@ConditionalOnProperty(name = "flow.schedulers", havingValue = "true", matchIfMissing = true)
public class ScheduleScanner {
  private final ScheduleService service;

  public ScheduleScanner(ScheduleService service) {
    this.service = service;
  }

  @Scheduled(fixedDelay = 30000)
  public void scan() {
    service.scan();
  }
}
