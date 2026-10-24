package com.flowconsole;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
@MapperScan("com.flowconsole.mapper")
@EnableScheduling
public class Application {
  public static void main(String[] args) {
    var context = SpringApplication.run(Application.class, args);
    if (java.util.Arrays.asList(context.getEnvironment().getActiveProfiles()).contains("migration"))
      SpringApplication.exit(context);
  }

  @Bean
  TransactionTemplate transactions(PlatformTransactionManager manager) {
    return new TransactionTemplate(manager);
  }
}
