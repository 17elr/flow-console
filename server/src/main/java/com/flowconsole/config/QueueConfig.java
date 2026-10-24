package com.flowconsole.config;

import jakarta.annotation.PostConstruct;
import java.util.*;
import org.springframework.amqp.core.*;
import org.springframework.context.annotation.*;
import org.springframework.core.env.Environment;

@Configuration
public class QueueConfig {
  public static final String EXCHANGE = "flow.publish",
      QUEUE = "flow.publish.tasks",
      ROUTE = "publish";
  private final Environment environment;

  public QueueConfig(Environment environment) {
    this.environment = environment;
  }

  @PostConstruct
  void validateProfiles() {
    var profiles = Arrays.asList(environment.getActiveProfiles());
    if (profiles.contains("api") && profiles.contains("worker"))
      throw new IllegalStateException("Run api and worker in separate processes");
  }

  @Bean
  Declarables queues() {
    var exchange = new DirectExchange(EXCHANGE, true, false);
    var dead = new DirectExchange("flow.dead", true, false);
    var queue =
        QueueBuilder.durable(QUEUE)
            .deadLetterExchange("flow.dead")
            .deadLetterRoutingKey("failed")
            .build();
    var dlq = QueueBuilder.durable("flow.publish.diagnostics").build();
    return new Declarables(
        exchange,
        dead,
        queue,
        dlq,
        BindingBuilder.bind(queue).to(exchange).with(ROUTE),
        BindingBuilder.bind(dlq).to(dead).with("failed"));
  }
}
