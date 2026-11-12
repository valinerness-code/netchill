# Step 1: Build stage using Maven and Microsoft OpenJDK 25
FROM mcr.microsoft.com/openjdk/jdk:25-ubuntu AS build
WORKDIR /app

RUN apt-get update && apt-get install -y maven

COPY pom.xml .
RUN mvn dependency:go-offline

COPY src src
RUN mvn clean package -DskipTests

FROM mcr.microsoft.com/openjdk/jdk:25-ubuntu
WORKDIR /app

# Run as an unprivileged user instead of root, so a bug in the app can't touch the container
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser

# Pull the compiled app jar with dependencies from the build environment
COPY --from=build --chown=appuser:appuser /app/target/*-jar-with-dependencies.jar app.jar

USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
