FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY . .
RUN mvn -B package dependency:copy-dependencies -DincludeScope=runtime

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/classes ./target/classes
COPY --from=build /app/target/dependency ./target/dependency
COPY --from=build /app/*.html ./
COPY --from=build /app/*.css ./
COPY --from=build /app/*.js ./
EXPOSE 10000
CMD ["sh", "-c", "exec java -cp 'target/classes:target/dependency/*' AuthServer"]
