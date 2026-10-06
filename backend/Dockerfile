# Step 1: Build stage using Maven and Microsoft OpenJDK 25
FROM mcr.microsoft.com/openjdk/jdk:25-ubuntu AS build
WORKDIR /app

# Install Maven natively to handle dependencies
RUN apt-get update && apt-get install -y maven

# Copy pom.xml first to cache your dependency layers
COPY pom.xml .
RUN mvn dependency:go-offline

# Copy your Java source files and compile into a Fat JAR
COPY src src
RUN mvn clean package -DskipTests

# Step 2: Production runtime stage
FROM mcr.microsoft.com/openjdk/jdk:25-ubuntu
WORKDIR /app

# Run as an unprivileged user instead of root, so a bug in the app can't touch the container
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser

# Pull the compiled app jar with dependencies from the build environment
COPY --from=build --chown=appuser:appuser /app/target/*-jar-with-dependencies.jar app.jar

USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
