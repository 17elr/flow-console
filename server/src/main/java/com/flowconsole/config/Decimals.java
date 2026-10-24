package com.flowconsole.config;

import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import java.math.BigDecimal;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.*;

@Configuration
public class Decimals {
  @Bean
  Jackson2ObjectMapperBuilderCustomizer decimalStrings() {
    return builder -> builder.serializerByType(BigDecimal.class, ToStringSerializer.instance);
  }
}
