package com.flowconsole.task;

import com.flowconsole.*;
import com.flowconsole.config.QueueConfig;
import com.flowconsole.mapper.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("api | default")
@ConditionalOnProperty(name = "flow.schedulers", havingValue = "true", matchIfMissing = true)
public class OutboxPublisher {
  private final TaskMapper tasks;
  private final CatalogMapper db;
  private final RabbitTemplate rabbit;

  public OutboxPublisher(TaskMapper tasks, CatalogMapper db, RabbitTemplate rabbit) {
    this.tasks = tasks;
    this.db = db;
    this.rabbit = rabbit;
  }

  @Scheduled(fixedDelay = 1000)
  public void scan() {
    for (long id : tasks.outboxDue()) publish(id);
  }

  public void publish(long id) {
    String owner = UUID.randomUUID().toString();
    if (tasks.claimOutbox(id, owner) != 1) return;
    try {
      var event = db.one(CatalogMapper.Table.outbox_event, id);
      var props = new MessageProperties();
      props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
      props.setContentType("application/json");
      props.setMessageId(event.get("event_id").toString());
      var body =
          Json.write(
                  Map.of(
                      "eventId",
                      event.get("event_id"),
                      "taskId",
                      event.get("task_id"),
                      "approvedVersion",
                      event.get("approved_version")))
              .getBytes(StandardCharsets.UTF_8);
      var correlation = new CorrelationData(event.get("event_id").toString());
      rabbit.send(QueueConfig.EXCHANGE, QueueConfig.ROUTE, new Message(body, props), correlation);
      boolean confirmed =
          correlation.getFuture().get(10, TimeUnit.SECONDS).isAck()
              && correlation.getReturned() == null;
      tasks.finishOutbox(id, owner, confirmed ? "SENT" : "PENDING");
    } catch (Exception e) {
      tasks.finishOutbox(id, owner, "PENDING");
    }
  }
}
