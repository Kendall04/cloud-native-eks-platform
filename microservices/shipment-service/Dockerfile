FROM mcr.microsoft.com/dotnet/sdk:10.0.403-noble@sha256:9c7b6b263d9d4c2e4718e16dae6d75cd8f4b5ccf206f1e7d48a98eb429981b03 AS build
WORKDIR /src

COPY ["Directory.Build.props", "."]
COPY ["ShipmentService.sln", "."]
COPY ["src/ShipmentService.Api/ShipmentService.Api.csproj", "src/ShipmentService.Api/"]
COPY ["src/ShipmentService.Api/packages.lock.json", "src/ShipmentService.Api/"]
COPY ["src/ShipmentService.Application/ShipmentService.Application.csproj", "src/ShipmentService.Application/"]
COPY ["src/ShipmentService.Application/packages.lock.json", "src/ShipmentService.Application/"]
COPY ["src/ShipmentService.Domain/ShipmentService.Domain.csproj", "src/ShipmentService.Domain/"]
COPY ["src/ShipmentService.Domain/packages.lock.json", "src/ShipmentService.Domain/"]
COPY ["src/ShipmentService.Infrastructure/ShipmentService.Infrastructure.csproj", "src/ShipmentService.Infrastructure/"]
COPY ["src/ShipmentService.Infrastructure/packages.lock.json", "src/ShipmentService.Infrastructure/"]
COPY ["tests/ShipmentService.Tests/ShipmentService.Tests.csproj", "tests/ShipmentService.Tests/"]
COPY ["tests/ShipmentService.Tests/packages.lock.json", "tests/ShipmentService.Tests/"]

RUN dotnet restore --locked-mode "ShipmentService.sln"

COPY . .

ARG SOURCE_COMMIT=unversioned
RUN dotnet publish "src/ShipmentService.Api/ShipmentService.Api.csproj" \
    --configuration Release \
    --no-restore \
    --output /app/publish \
    /p:UseAppHost=false \
    /p:SourceRevisionId=${SOURCE_COMMIT}

FROM mcr.microsoft.com/dotnet/aspnet:10.0.14-noble-chiseled-extra@sha256:1b996b356531e88e7731ba694bc0ec13e2f05d25cf833e772363db84e75e467f AS final
WORKDIR /app

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

COPY --from=build --chown=app:app /app/publish .

USER $APP_UID

ENTRYPOINT ["dotnet", "ShipmentService.Api.dll"]
