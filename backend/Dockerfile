# Step 1: Build stage using Maven and Microsoft OpenJDK 17
FROM ://microsoft.com AS build
WORKDIR /app

# Copy the standardized pom.xml first to lock down dependency layers
COPY pom.xml .
RUN mvn dependency:go-offline

# Copy the standard src folder architecture into the build instance
COPY src src
RUN mvn clean package -DskipTests

# Step 2: Production runtime stage
FROM ://microsoft.com
WORKDIR /app

# Pull the compiled app jar from the build environment
COPY --from=build /app/target/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
