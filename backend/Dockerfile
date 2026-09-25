# Step 1: Build stage using Maven and Microsoft OpenJDK 17
FROM mcr.microsoft.com/openjdk/jdk:17-ubuntu AS build
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
FROM mcr.microsoft.com/openjdk/jdk:17-ubuntu
WORKDIR /app

# Pull the compiled app jar with dependencies from the build environment
COPY --from=build /app/target/*-jar-with-dependencies.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
