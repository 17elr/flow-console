package com.flowconsole.task;

import com.flowconsole.*;
import com.flowconsole.config.QueueConfig;
import com.flowconsole.mapper.*;
import com.rabbitmq.client.Channel;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("worker")
@ConditionalOnProperty(name = "flow.schedulers", havingValue = "true", matchIfMissing = true)
public class Worker {
  private final TaskExecutor executor;
  private final TaskMapper tasks;
  private final TaskService service;
  private final CatalogMapper db;
  private final TransactionTemplate tx;

  public Worker(
      TaskExecutor executor,
      TaskMapper tasks,
      TaskService service,
      CatalogMapper db,
      TransactionTemplate tx) {
    this.executor = executor;
    this.tasks = tasks;
    this.service = service;
    this.db = db;
    this.tx = tx;
  }

  @RabbitListener(queues = QueueConfig.QUEUE)
  public void consume(Message message, Channel channel) throws Exception {
    long tag = message.getMessageProperties().getDeliveryTag();
    try {
      var body = Json.map(new String(message.getBody(), StandardCharsets.UTF_8));
      if (body.size() != 3 || !body.containsKey("eventId"))
        throw new IllegalArgumentException("Invalid event");
      executor.execute(Json.id(body.get("taskId")), Json.id(body.get("approvedVersion")));
      channel.basicAck(tag, false);
    } catch (IllegalArgumentException e) {
      channel.basicReject(tag, false);
    } catch (Exception e) {
      channel.basicReject(tag, false);
    }
  }

  @Scheduled(fixedDelay = 30000)
  public void recover() {
    for (long id : tasks.expired())
      tx.executeWithoutResult(
          s -> {
            if (tasks.recover(id) == 1) {
              var t = db.one(CatalogMapper.Table.publish_task, id);
              service.enqueue(id, Json.id(t.get("approved_version")));
            }
          });
    for (var t : tasks.due())
      tx.executeWithoutResult(
          s -> {
            tasks.lock(Json.id(t.get("id")));
            if (tasks.needsEvent(Json.id(t.get("id"))))
              service.enqueue(Json.id(t.get("id")), Json.id(t.get("approved_version")));
          });
  }
}
