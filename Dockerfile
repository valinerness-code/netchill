FROM maven:3.9-eclipse-temurin-17 AS build

WORKDIR /build
COPY pom.xml AuthServer.java ./
RUN mvn -q dependency:copy-dependencies package

FROM nginx:1.27-alpine

RUN apk add --no-cache openjdk17-jre-headless

WORKDIR /app
COPY --from=build /build/target/classes/AuthServer.class /app/
COPY --from=build /build/target/dependency/postgresql-*.jar /app/postgresql.jar

WORKDIR /usr/share/nginx/html

COPY . /usr/share/nginx/html
COPY default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["sh", "-c", "java -cp /app:/app/postgresql.jar AuthServer & nginx -g 'daemon off;'"]
