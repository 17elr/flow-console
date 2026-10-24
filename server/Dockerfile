FROM maven:3.10.0-eclipse-temurin-17 AS build
WORKDIR /build
COPY server/pom.xml pom.xml
RUN mvn -B dependency:go-offline
COPY server/src src
RUN mvn -B -DskipTests package
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
RUN groupadd -g 10001 flow && useradd -u 10001 -g flow flow && mkdir -p /app/data/assets && chown -R flow:flow /app
COPY --from=build /build/target/flow-console-2.0.0.jar app.jar
USER flow
ENTRYPOINT ["java","-jar","/app/app.jar"]
